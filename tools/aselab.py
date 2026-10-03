#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host-side tooling for the lab environment.

Runs on the host under ``uv`` (see ``pyproject.toml``), so it may use
dependencies; everything that touches the compiler or gem5 happens in the
container instead (``tools/incontainer.py``).

Subcommands
-----------
``config``           Merge ``cpu.toml`` (+ a per-lab ``<lab>/cpu.toml``) into the
                     CPU-configuration JSON the container consumes.
``report``           Render a ``pipeline.json`` dump as a Markdown report.
``check``            Compare each program's architectural result with its golden
                     file (``<lab>/<program>.expected``).
``update-expected``  (Re)generate those golden files.
``zip``              Build the per-lab submission archive.
``labs``             List the discovered labs and programs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import NoReturn

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

# The knobs the web UI exposes, i.e. backend.DEFAULT_CONFIG in
# ase_studio/backend.py of the pinned image.  Kept here so the host can fill in
# what a lab's cpu.toml leaves out; the container re-validates the merged result
# with the backend's own validate_config() before anything runs.
DEFAULTS = {
    "cpu": "in-order", "intAlu": 1, "intMul": 1, "intDiv": 1,
    "floatAlu": 2, "floatMul": 7, "floatDiv": 8,
    "intAluPipelined": True, "intMulPipelined": True,
    "intDivPipelined": True, "floatAluPipelined": True,
    "floatMulPipelined": True, "floatDivPipelined": False,
    "forwarding": True, "compressedInstructions": False,
    "floatingPointPrecision": "single",
    "memoryMode": "direct", "cacheStalls": False,
    "instructionMemoryLatency": 1, "dataReadLatency": 1,
    "dataWriteLatency": 1,
    "iCacheSize": "32kB", "dCacheSize": "32kB", "cacheLine": 64,
    "cacheLatency": 2, "memoryLatency": 30,
    "fetchWidth": 2, "decodeWidth": 2, "renameWidth": 2,
    "dispatchWidth": 2, "issueWidth": 2, "writebackWidth": 2,
    "commitWidth": 2, "robEntries": 64, "iqEntries": 128,
    "lqEntries": 32, "sqEntries": 32,
    "o3VisibleStages": ["issue", "execute", "memory", "cdb", "commit"],
    "branchPredictor": "local", "speculativeExecution": True,
    "outOfOrderExecution": True, "o3EvaluationLabel": "",
}

# Groups the pinned image resets to their defaults: ENABLE_MEMORY_CONFIGURATION
# and ENABLE_MULTI_ISSUE_CPU are both False in ase_studio/backend.py, so the
# in-order model is the only reachable CPU and the cache/memory knobs are
# locked.  Setting them is not an error, it simply has no effect.
DEAD_MEMORY = "memory configuration is disabled in this image"
DEAD_O3 = "the out-of-order model is disabled in this image"
LOCKED_KEYS = {
    "cpu": "this image only exposes the in-order model (multiIssueCpu: false)",
    "memoryMode": DEAD_MEMORY, "cacheStalls": DEAD_MEMORY,
    "instructionMemoryLatency": DEAD_MEMORY, "dataReadLatency": DEAD_MEMORY,
    "dataWriteLatency": DEAD_MEMORY, "iCacheSize": DEAD_MEMORY,
    "dCacheSize": DEAD_MEMORY, "cacheLine": DEAD_MEMORY,
    "cacheLatency": DEAD_MEMORY, "memoryLatency": DEAD_MEMORY,
    "fetchWidth": DEAD_O3, "decodeWidth": DEAD_O3, "renameWidth": DEAD_O3,
    "dispatchWidth": DEAD_O3, "issueWidth": DEAD_O3, "writebackWidth": DEAD_O3,
    "commitWidth": DEAD_O3, "robEntries": DEAD_O3, "iqEntries": DEAD_O3,
    "lqEntries": DEAD_O3, "sqEntries": DEAD_O3, "branchPredictor": DEAD_O3,
    "speculativeExecution": DEAD_O3, "outOfOrderExecution": DEAD_O3,
    "o3VisibleStages": DEAD_O3, "o3EvaluationLabel": DEAD_O3,
}
LIVE_KEYS = [key for key in DEFAULTS if key not in LOCKED_KEYS]

STAGE_LEGEND = {
    "F": "fetch", "D": "decode", "E": "execute", "M": "memory",
    "W": "writeback", "S": "stall", "R": "rename", "I": "dispatch",
    "C": "complete",
}
EMPTY_CELL = "·"

STATUS_OK, STATUS_SKIPPED, STATUS_FAILED = "ok", "skip", "FAIL"


def fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(2)


def require(directory: Path, name: str) -> Path:
    path = directory / name
    if not path.is_file():
        fail(f"missing {path}; run `make run` for this program first")
    return path


def maybe_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.is_file() else {}


def march_for(config: dict) -> str:
    """Mirror backend.build()'s -march, so the report documents the real ISA."""
    floating = "fd" if config.get("floatingPointPrecision") == "double" else "f"
    compressed = "c" if config.get("compressedInstructions") else ""
    return f"rv32ima{floating}{compressed}_zicsr_zifencei"


def register_sort_key(register: str):
    match = re.fullmatch(r"([xf])(\d+)", register)
    return (0 if register.startswith("x") else 1, int(match.group(2)) if match else 0)


def load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    unknown = sorted(set(data) - set(DEFAULTS))
    if unknown:
        fail(f"{path}: unknown CPU setting(s): {', '.join(unknown)}\n"
             f"       valid keys: {', '.join(sorted(DEFAULTS))}")
    return data


def config_command(args) -> int:
    merged = dict(DEFAULTS)
    notes = []
    for source in (Path(args.toml), Path(args.lab_toml) if args.lab_toml else None):
        if source is None:
            continue
        for key, value in load_toml(source).items():
            if key in LOCKED_KEYS:
                # The backend resets these to their defaults before a run, so the
                # merged file must show the value that will really be used.
                if value != DEFAULTS[key]:
                    notes.append(f"{source}: '{key}' has no effect here ({LOCKED_KEYS[key]})")
                continue
            merged[key] = value
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    for note in notes:
        print(f"note: {note}", file=sys.stderr)
    return 0


def visible_rows(data: dict) -> list:
    rows = [row for row in (data.get("dynamicInstructions") or []) if not row.get("squashed")]
    return rows or list(data.get("instructions") or [])


def pipeline_section(data: dict, columns: int) -> list:
    rows = visible_rows(data)
    lines = ["## Pipeline", ""]
    if not rows:
        return lines + ["No trace rows were produced.", ""]
    cycles = data.get("cycles", 0)
    lines += [
        f"{len(rows)} dynamic instruction(s) over {cycles} cycle(s). `{EMPTY_CELL}` means "
        "the instruction was in no stage that cycle.",
        "",
        "Legend: " + " ".join(f"`{letter}` {name}"
                              for letter, name in sorted(STAGE_LEGEND.items())),
        "",
    ]
    index_width = len(str(len(rows)))
    for start in range(1, cycles + 1, columns):
        stop = min(start + columns - 1, cycles)
        header = ["#", "line", "instruction"] + [str(cycle) for cycle in range(start, stop + 1)]
        lines += ["| " + " | ".join(header) + " |",
                  "| " + " | ".join(["---"] * len(header)) + " |"]
        for index, row in enumerate(rows, start=1):
            stages = row.get("cycles", {})
            cells = [stages.get(str(cycle)) or EMPTY_CELL
                     for cycle in range(start, stop + 1)]
            label = row.get("instruction", "").strip()
            lines.append("| " + " | ".join([
                f"{index:>{index_width}}",
                str(row.get("sourceLine") or ""),
                f"`{label}`",
                *cells,
            ]) + " |")
        lines.append("")

    lines += ["## Pipeline per instruction", "",
              "| # | line | address | instruction | stages (cycle:stage) | iterations |",
              "| --- | --- | --- | --- | --- | --- |"]
    for index, row in enumerate(rows, start=1):
        stages = sorted(((int(cycle), stage) for cycle, stage in row.get("cycles", {}).items()))
        lines.append("| " + " | ".join([
            str(index),
            str(row.get("sourceLine") or ""),
            f"`{row.get('address', '')}`",
            f"`{row.get('instruction', '').strip()}`",
            " ".join(f"{cycle}:{stage}" for cycle, stage in stages),
            str(row.get("iterations", 1)),
        ]) + " |")
    lines.append("")
    return lines


def registers_section(data: dict, summary: dict) -> list:
    lines = ["## Register writes", ""]
    deltas = data.get("registerDeltas", {})
    if not deltas:
        lines += ["No register was written.", ""]
    else:
        lines += ["| cycle | register | value |", "| --- | --- | --- |"]
        for cycle in sorted(deltas, key=int):
            for register in sorted(deltas[cycle], key=register_sort_key):
                lines.append(f"| {cycle} | `{register}` | `{deltas[cycle][register]}` |")
        lines.append("")

    lines += ["## Final registers", "",
              "Checked by `make check`; architectural state, independent of the CPU model.", ""]
    registers = summary.get("registers", {})
    if not registers:
        lines += ["Every register is zero at the end of the program.", ""]
    else:
        lines += ["| register | value |", "| --- | --- |"]
        for register, value in registers.items():
            lines.append(f"| `{register}` | `{value}` |")
        lines += ["", "Registers that are not listed still hold `0x0`.", ""]
    return lines


def memory_index(data: dict) -> tuple[dict, dict]:
    """Address -> last runtime access, and address -> label from the symbols."""
    writes: dict[str, dict] = {}
    for cycle in sorted(data.get("memoryDeltas", {}), key=int):
        for address, entry in data["memoryDeltas"][cycle].items():
            writes[address.lower()] = {"cycle": cycle, "access": entry.get("access"),
                                      "bits": entry.get("bits", 32)}
    labels = {}
    for symbol in data.get("dataSymbols", []) or []:
        address = symbol.get("address")
        if address:
            labels[address.lower()] = symbol.get("label") or symbol.get("name") or ""
    return writes, labels


def memory_section(data: dict, summary: dict) -> list:
    writes, labels = memory_index(data)
    lines = ["## Data memory", "", "Checked by `make check`.", ""]
    memory = summary.get("memory", {})
    if not memory:
        lines += ["The program declares and touches no data memory.", ""]
    else:
        lines += ["| address | label | value | origin | written at |",
                  "| --- | --- | --- | --- | --- |"]
        for address, value in memory.items():
            entry = writes.get(address.lower())
            if entry is None:
                origin, cycle_text = "ELF initial value", ""
            else:
                origin = ("stored by the program" if entry["access"] == "write"
                          else f"read ({entry['access']})")
                cycle_text = str(entry["cycle"])
            lines.append(f"| `{address}` | {labels.get(address.lower(), '')} | `{value}` "
                         f"| {origin} | {cycle_text} |")
        lines.append("")

    memory_map = data.get("memoryMap", [])
    if memory_map:
        lines += ["## Memory map", "",
                  "| section | kind | start | end | size |",
                  "| --- | --- | --- | --- | --- |"]
        for section in memory_map:
            lines.append("| " + " | ".join([
                str(section.get("name", "")), str(section.get("kind", "")),
                f"`{section.get('start', '')}`", f"`{section.get('end', '')}`",
                str(section.get("size", "")),
            ]) + " |")
        lines.append("")
    return lines


def report_command(args) -> int:
    build = Path(args.build)
    data = json.loads(require(build, "pipeline.json").read_text())
    meta = json.loads(require(build, "meta.json").read_text())
    summary = maybe_json(build / "summary.json")
    source_path = Path(args.source)
    source_lines = source_path.read_text(encoding="utf-8").splitlines()
    config = meta.get("config", {})

    stem = meta.get("stem", args.source)
    rows = visible_rows(data)
    stalls = sum(stage == "S" for row in rows for stage in row.get("cycles", {}).values())
    cycles = data.get("cycles", 0)
    cpi = round(cycles / len(rows), 3) if rows else 0

    lines = [
        f"# Lab report — `{stem}`", "",
        f"* `{meta.get('format', '?')}` pipeline · `{march_for(config)}` · gem5 from `{args.image}`",
        f"* source `{source_path.name}` · sha256 `{str(meta.get('sourceSha256', '?'))[:16]}…`",
        "",
        "## Summary", "",
        "| cycles | instructions | stalls | CPI | code bytes |",
        "| --- | --- | --- | --- | --- |",
        f"| {cycles} | {len(rows)} | {stalls} | {cpi} | {data.get('codeBytes', 0)} |",
        "",
        "## CPU characteristics", "",
        "| setting | value |", "| --- | --- |",
    ]
    for key in LIVE_KEYS:
        value = config.get(key, DEFAULTS.get(key))
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        lines.append(f"| `{key}` | {value} |")
    lines += ["", "*Locked in this image: " + ", ".join(f"`{key}`" for key in sorted(LOCKED_KEYS))
              + " (memory configuration and the out-of-order model are disabled in"
              " `ase_studio/backend.py`).*", ""]

    lines += pipeline_section(data, args.columns)
    lines += registers_section(data, summary)
    lines += memory_section(data, summary)

    output = summary.get("output", "").strip()
    lines += ["## Program output", "",
              "The program's own stdout, with the simulator's chatter removed."
              " Checked by `make check`.", "",
              "```text", output or "(no output)", "```", ""]

    lines += ["## Source", "", "```asm"]
    for number, text in enumerate(source_lines, start=1):
        lines.append(f"{number:>4}  {text}")
    lines += ["```", ""]

    lines += ["## Logs", ""]
    for title, name in (("Build log", "build.log"), ("Simulation log", "simulate.log")):
        path = build / name
        if not path.is_file():
            continue
        lines += [f"<details><summary>{title}</summary>", "", "```text",
                  path.read_text(encoding="utf-8").strip(), "```", "", "</details>", ""]

    out = Path(args.out) if args.out else build / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


def golden(summary: dict) -> dict:
    """The architectural facts a check compares: no timing, no CPU model."""
    return {
        "output": summary.get("output", "").strip(),
        "registers": summary.get("registers", {}),
        "memory": summary.get("memory", {}),
    }


def describe_difference(expected: dict, actual: dict) -> list:
    lines = []
    if expected.get("output", "") != actual.get("output", ""):
        lines.append("  output differs:")
        lines.append(f"    expected: {expected.get('output', '')!r}")
        lines.append(f"    actual:   {actual.get('output', '')!r}")
    for section in ("registers", "memory"):
        expected_values, actual_values = expected.get(section, {}), actual.get(section, {})
        keys = sorted(set(expected_values) | set(actual_values),
                      key=register_sort_key if section == "registers" else str.lower)
        for key in keys:
            if expected_values.get(key) != actual_values.get(key):
                lines.append(f"  {section}: {key}: expected "
                             f"{expected_values.get(key, '(absent)')} != actual "
                             f"{actual_values.get(key, '(absent)')}")
    return lines


def program_pairs(sources: list) -> list:
    """(stem, source path, golden path) for every discovered program."""
    pairs = []
    for source in sources:
        path = Path(source)
        pairs.append((f"{path.parent.name}/{path.stem}", path,
                      path.parent / f"{path.stem}.expected"))
    return pairs


def check_command(args) -> int:
    build = Path(args.build)
    results, failures = [], []
    for stem, source, expected_path in program_pairs(args.sources):
        summary_path = build / stem / "summary.json"
        if not summary_path.is_file():
            results.append((STATUS_SKIPPED, stem, "no result yet — run `make run`"))
            continue
        if not expected_path.is_file():
            results.append((STATUS_SKIPPED, stem,
                            f"no golden file — run `make update-expected` (or add {expected_path.name})"))
            continue
        actual = golden(json.loads(summary_path.read_text()))
        expected = json.loads(expected_path.read_text())
        if expected == actual:
            results.append((STATUS_OK, stem, ""))
        else:
            failures.append((stem, describe_difference(expected, actual)))
            results.append((STATUS_FAILED, stem, ""))

    print(f"checked {len(results)} program(s)")
    for status, stem, note in results:
        print(f"  {status:<4}  {stem}" + (f"  ({note})" if note else ""))
    for stem, differences in failures:
        print(f"\n{stem}:")
        for line in differences:
            print(line)
    if failures:
        print("\nThe architectural result changed. If that is intended, "
              "run `make update-expected`.")
        return 1
    if any(status == STATUS_SKIPPED for status, _, _ in results):
        return 1
    return 0


def update_expected_command(args) -> int:
    build = Path(args.build)
    written = []
    for stem, source, expected_path in program_pairs(args.sources):
        summary_path = build / stem / "summary.json"
        if not summary_path.is_file():
            print(f"  skip  {stem}: no result yet")
            continue
        expected_path.write_text(
            json.dumps(golden(json.loads(summary_path.read_text())), indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
        written.append(stem)
    for stem in written:
        print(f"  wrote {stem}/{Path(stem).name}.expected")
    print(f"updated {len(written)} golden file(s)")
    return 0


def submission_readme(lab: str, programs: list, build: Path) -> str:
    lines = [f"# `{lab}` — submission", "",
             f"{len(programs)} program(s), compiled and simulated with gem5 on the ASE "
             "RISC-V in-order model.", "",
             "| program | source | disassembly | report |",
             "| --- | --- | --- | --- |"]
    for program in programs:
        folder = build / lab / program.stem
        mark = lambda name: "✓" if (folder / name).is_file() else "—"  # noqa: E731
        lines.append(f"| `{program.stem}` | `main.s` | {mark('main.dump')} | "
                     f"{mark('report.md')} |")
    lines += ["",
              "Each program folder holds the source (`main.s`), the Makefile the simulator",
              "uses (`ASM = ./main.s`, `include $(ASE_STUDIO_DEMO_MK)`), the disassembly",
              "(`main.dump`) and the pipeline/register/memory `report.md`.", ""]
    return "\n".join(lines)


def zip_command(args) -> int:
    lab_dir = Path(args.lab)
    if not lab_dir.is_dir():
        fail(f"no such lab directory: {args.lab}")
    programs = sorted(lab_dir.glob("*.s"))
    if not programs:
        fail(f"{args.lab}/ contains no .s program")
    build, out = Path(args.build), Path(args.out)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{args.lab}/README.md",
                         submission_readme(args.lab, programs, build))
        # The CPU characteristics the results were produced with: the lab's own
        # cpu.toml if it has one, otherwise the shared default.
        for candidate in (lab_dir / "cpu.toml", Path(args.cpu)):
            if candidate.is_file():
                archive.write(candidate, f"{args.lab}/cpu.toml")
                break
        for index, program in enumerate(programs, start=1):
            folder = build / args.lab / program.stem
            component = f"{index:02d}-{program.stem}"
            archive.write(program, f"{args.lab}/{component}/main.s")
            for name in ("Makefile", "main.dump", "report.md"):
                if (folder / name).is_file():
                    archive.write(folder / name, f"{args.lab}/{component}/{name}")
            if not (folder / "Makefile").is_file():
                archive.writestr(f"{args.lab}/{component}/Makefile",
                                 "ASM = ./main.s\ninclude $(ASE_STUDIO_DEMO_MK)\n")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(programs)} program(s))")
    return 0


def labs_command(args) -> int:
    found = False
    for lab_dir in sorted(path for path in Path(".").glob("[0-9]*") if path.is_dir()):
        programs = sorted(path.stem for path in lab_dir.glob("*.s"))
        print(f"{lab_dir.name}: {', '.join(programs) if programs else '(no programs yet)'}")
        found = True
    if not found:
        print("no lab directory found; create one such as 01/ with .s programs")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    config = sub.add_parser("config", help="merge cpu.toml into the container's config JSON")
    config.add_argument("--toml", default="cpu.toml")
    config.add_argument("--lab-toml", default="")
    config.add_argument("--out", required=True)
    config.set_defaults(func=config_command)

    report = sub.add_parser("report", help="render a Markdown report")
    report.add_argument("--build", required=True, help="build/<lab>/<program> directory")
    report.add_argument("--source", required=True)
    report.add_argument("--out", default="")
    report.add_argument("--image", default="")
    report.add_argument("--columns", type=int, default=60,
                        help="cycle columns per pipeline table block")
    report.set_defaults(func=report_command)

    check = sub.add_parser("check", help="compare results with the golden files")
    check.add_argument("--sources", nargs="+", required=True)
    check.add_argument("--build", default="build")
    check.set_defaults(func=check_command)

    update = sub.add_parser("update-expected", help="regenerate the golden files")
    update.add_argument("--sources", nargs="+", required=True)
    update.add_argument("--build", default="build")
    update.set_defaults(func=update_expected_command)

    zip_parser = sub.add_parser("zip", help="build a lab submission archive")
    zip_parser.add_argument("--lab", required=True)
    zip_parser.add_argument("--out", required=True)
    zip_parser.add_argument("--build", default="build")
    zip_parser.add_argument("--cpu", default="cpu.toml")
    zip_parser.set_defaults(func=zip_command)

    labs = sub.add_parser("labs", help="list labs and their programs")
    labs.set_defaults(func=labs_command)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
