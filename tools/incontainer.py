#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run one lab program inside the ASE container.

Executed *inside* the image (``--entrypoint python3``), never on the host, so it
may only use the standard library: the image ships Python 3.10 and nothing else.

Two modes:

``build``
    Compile only. Produces ``main.elf`` / ``main.dump``.

``run``
    Simulate with gem5 and keep the raw build/simulation logs.  With ``--elf``
    a prebuilt ELF is simulated instead of compiling one; ``--report`` also
    dumps the pipeline trace and the architectural summary.

Everything is written under ``--out``, which lives on the mounted tree, then
chowned to ``ASE_OUT_OWNER`` so the host user owns their own artifacts even
though the container runs as root.

The pipeline, register and memory facts come from ``ase_studio/backend.py``
itself -- the same code the web UI renders -- so the lab output cannot drift
from the GUI.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

STAGE_LEGEND_MINOR = {
    "F": "fetch",
    "D": "decode",
    "E": "execute",
    "M": "memory",
    "W": "writeback",
    "S": "stall",
}
STAGE_LEGEND_O3 = {
    "F": "fetch",
    "D": "decode",
    "R": "rename",
    "I": "dispatch",
    "E": "issue",
    "C": "complete",
    "W": "retire",
    "S": "stall",
}

GEM5_NOISE = re.compile(
    r"^(gem5 |warn:|info:|Global frequency|switching to|"
    r"\*\*\*\* REAL SIMULATION \*\*\*\*|Log4GUI:|system\.|T\d+ :|"
    r"Exiting @ tick|\$ )"
)


def container_root() -> Path:
    return Path(os.environ.get("ASE_STUDIO_HOST_ROOT", "/app")).resolve()


def load_backend():
    root = container_root()
    studio = root / "ase_studio"
    if not (studio / "backend.py").is_file():
        die(f"ase_studio/backend.py not found under {root}; is this the ASE image?")
    sys.path.insert(0, str(studio))
    import backend  # noqa: E402  (path is set up above)

    return backend


def die(message: str, status: int = 1):
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(status)


def project_name_for(stem: str) -> str:
    """``01/hello`` -> ``lab_01_hello`` (a valid project name)."""
    return "lab_" + stem.replace("/", "_").replace("-", "_")


def write_artifacts(backend, folder: Path, source_text: str, config):
    """Lay out the project exactly like the GUI does, then compile it."""
    name = folder.name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    (folder / "main.s").write_text(source_text)
    # The Makefile the GUI generates: one source file, compiled by demo.mk.
    (folder / "Makefile").write_text(backend.MAKEFILE)
    backend.save_project_config(folder, config)


def artifact_paths(folder: Path):
    stem = backend_artifact_stem(folder)
    return folder / f"{stem}.elf", folder / f"{stem}.dump"


def backend_artifact_stem(folder: Path) -> str:
    sources = sorted(list(folder.glob("*.s")) + list(folder.glob("*.S")))
    if not sources:
        return "main"
    return sources[0].stem


def program_output(text: str) -> str:
    """Best-effort: the lines gem5's own chatter does not explain.

    The program writes straight to gem5's stdout in SE mode, so its output is
    interleaved with simulator messages.  Everything the simulator prefixes
    recognisably is dropped; whatever remains is the program's own output.
    """
    kept = [line for line in text.splitlines() if not GEM5_NOISE.match(line.strip())]
    while kept and not kept[-1].strip():
        kept.pop()
    while kept and not kept[0].strip():
        kept.pop(0)
    return "\n".join(kept)


def fold_registers(deltas: dict) -> dict:
    """Apply the per-cycle write log in cycle order and return the final state."""
    final: dict[str, str] = {}
    for cycle in sorted(deltas, key=lambda value: int(value)):
        for register, value in deltas[cycle].items():
            final[register] = value
    return final


def register_sort_key(register: str):
    match = re.fullmatch(r"([xf])(\d+)", register)
    return (0 if register.startswith("x") else 1, int(match.group(2)) if match else 0)


def address_sort_key(address: str):
    return int(address, 16)


def final_memory(initial: dict, deltas: dict, symbols: list):
    """Fold initial values and runtime writes into one address -> value view."""
    labels = {}
    for symbol in symbols or []:
        address = symbol.get("address")
        if address:
            labels[int(address, 16)] = symbol.get("label") or symbol.get("name")
    state: dict[str, dict] = {}
    for address, entry in (initial or {}).items():
        state[address.lower()] = {
            "value": entry.get("value") if isinstance(entry, dict) else entry,
            "bits": entry.get("bits", 32) if isinstance(entry, dict) else 32,
            "source": "ELF initial value",
            "cycle": "",
            "label": labels.get(int(address, 16), ""),
        }
    for cycle in sorted(deltas, key=lambda value: int(value)):
        for address, entry in deltas[cycle].items():
            address = address.lower()
            if entry.get("access") != "write":
                continue
            current = state.setdefault(address, {
                "value": "", "bits": entry.get("bits", 32),
                "source": "runtime", "cycle": "", "label": labels.get(int(address, 16), ""),
            })
            current.update({
                "value": entry.get("value", ""),
                "bits": entry.get("bits", current.get("bits", 32)),
                "source": "stored by the program",
                "cycle": cycle,
            })
    return {address: state[address] for address in sorted(state, key=address_sort_key)}


def pipeline_rows(data: dict):
    rows = data.get("dynamicInstructions") or data.get("instructions") or []
    return [row for row in rows if not row.get("squashed")]


def summarize(data: dict, registers: dict, memory: dict, output: str):
    """Architectural facts only: these do not depend on the CPU model."""
    return {
        "registers": {register: registers[register]
                      for register in sorted(registers, key=register_sort_key)},
        "memory": {address: entry.get("value", "")
                   for address, entry in memory.items()},
        "output": output,
    }


def chown_tree(path: Path):
    owner = os.environ.get("ASE_OUT_OWNER", "")
    if not owner or os.geteuid() != 0:
        return
    try:
        uid_text, gid_text = owner.split(":")
        uid, gid = int(uid_text), int(gid_text)
    except ValueError:
        return
    for root, directories, files in os.walk(path):
        for name in [*directories, *files]:
            try:
                os.chown(os.path.join(root, name), uid, gid)
            except OSError:
                pass
    try:
        os.chown(path, uid, gid)
    except OSError:
        pass


def copy_artifacts(folder: Path, out: Path):
    """Copy the compiled artifacts out of the container's writable layer."""
    for name in ("main.elf", "main.dump"):
        source = folder / name
        if source.is_file():
            shutil.copy2(source, out / name)
            print(f"  wrote {name}")


def limited_run_command(seconds: int):
    """A replacement for ``backend.run_command`` that gives every child a deadline.

    ``run_command`` runs its command without a timeout, so a program that never
    reaches its ``End:`` label would hang the container forever.  The cap lives
    here rather than on the host because the host cannot do it portably -- macOS
    has no ``timeout`` command.  A reached deadline is reported as status 124 so
    the Makefile can explain it; everything else keeps gem5's own status.
    """

    def run_command(command, cwd, env):
        header = "$ " + " ".join(command) + "\n"
        try:
            result = subprocess.run(
                command, cwd=cwd, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=seconds,
            )
        except subprocess.TimeoutExpired as expired:
            partial = expired.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode(errors="replace")
            return 124, header + partial + (
                f"\nTimed out after {seconds}s: the program probably never reaches "
                "its 'End:' label.\n")
        return result.returncode, header + result.stdout

    return run_command


def run(args) -> int:
    backend = load_backend()
    backend.run_command = limited_run_command(args.timeout)
    source_path = Path(args.source)
    if not source_path.is_file():
        die(f"source file not found: {source_path}")
    source_text = source_path.read_text(encoding="utf-8")
    config = json.loads(Path(args.config).read_text()) if args.config else None
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    name = args.name or project_name_for(args.stem)
    folder = backend.project_path(name)

    if config is None:
        config = backend.DEFAULT_CONFIG.copy()
    write_artifacts(backend, folder, source_text, config)

    print(f"== {args.stem} (project {name}) ==")
    if args.elf:
        elf = Path(args.elf)
        if not elf.is_file():
            die(f"prebuilt ELF not found: {elf}")
        shutil.copy2(elf, folder / f"{backend_artifact_stem(folder)}.elf")
        print(f"using prebuilt {elf.name}")
    else:
        built = backend.build(name)
        (out / "build.log").write_text(built.get("advancedOutput", ""))
        (out / "build-display.log").write_text(built.get("output", ""))
        if not built.get("ok"):
            print(built.get("output", ""))
            chown_tree(out)
            print("build failed", file=sys.stderr)
            return 1
        print("build ok")

    if args.mode == "build":
        copy_artifacts(folder, out)
        chown_tree(out)
        return 0

    simulated = backend.simulate(name)
    simulate_log = simulated.get("advancedOutput", "")
    simulate_display = simulated.get("output", "")
    (out / "simulate.log").write_text(simulate_log)
    (out / "simulate-display.log").write_text(simulate_display)
    print(simulate_display)
    if not simulated.get("ok"):
        copy_artifacts(folder, out)
        chown_tree(out)
        print("simulation failed", file=sys.stderr)
        # 124 travels up to the Makefile, which explains what it means.
        return 124 if "Timed out after" in simulate_log else 1

    if args.report:
        data = backend.pipeline(name)
        registers = fold_registers(data.get("registerDeltas", {}))
        memory = final_memory(data.get("initialMemory", {}),
                              data.get("memoryDeltas", {}),
                              data.get("dataSymbols", []))
        output = program_output(simulate_display)
        (out / "pipeline.json").write_text(json.dumps(data, indent=1, sort_keys=True))
        (out / "summary.json").write_text(json.dumps(
            summarize(data, registers, memory, output), indent=2, sort_keys=True) + "\n")
        (out / "meta.json").write_text(json.dumps({
            "stem": args.stem,
            "project": name,
            "source": source_path.name,
            "sourceSha256": __import__("hashlib").sha256(
                source_text.encode("utf-8")).hexdigest(),
            "config": data.get("configuration", config),
            "format": data.get("format", ""),
            "cycles": data.get("cycles", 0),
            "instructions": len(pipeline_rows(data)),
            "buildOk": True,
            "simulateOk": True,
        }, indent=2, sort_keys=True) + "\n")
        rows = pipeline_rows(data)
        stalls = sum(stage == "S" for row in rows
                     for stage in row.get("cycles", {}).values())
        print(f"cycles={data.get('cycles', 0)} instructions={len(rows)} stalls={stalls}")
    copy_artifacts(folder, out)
    chown_tree(out)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "run"))
    parser.add_argument("--source", required=True, help="path to the .s file (inside /work)")
    parser.add_argument("--out", required=True, help="output directory (inside /work)")
    parser.add_argument("--stem", default="", help="lab/program stem, e.g. 01/hello")
    parser.add_argument("--name", default="", help="override the server-side project name")
    parser.add_argument("--config", default="", help="CPU configuration JSON")
    parser.add_argument("--elf", default="",
                        help="prebuilt ELF to simulate instead of compiling")
    parser.add_argument("--report", action="store_true",
                        help="also dump the pipeline/summary/meta JSON dumps")
    parser.add_argument("--timeout", type=int, default=180,
                        help="seconds allowed per compiler/simulator process")
    args = parser.parse_args()
    if not args.stem:
        args.stem = Path(args.source).with_suffix("").as_posix()
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
