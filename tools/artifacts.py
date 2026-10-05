#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Render the lab artifacts the simulator left behind.

Two modes, both pure standard library and both reading only files under the
build tree -- no compiler, no gem5, no ASE backend:

``report``
    ``pipeline.json`` + ``meta.json`` + ``summary.json`` -> ``report.md``.

``zip``
    One lab's sources plus its build artifacts -> ``<lab>.zip``.

Like ``tools/incontainer.py`` this is run *inside* the image (``--entrypoint
python3``); it is stdlib-only so it runs anywhere Python 3.10+ exists, which is
also why it needs no network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import zipfile
from pathlib import Path

EMPTY_CELL = "·"
STAGE_LEGEND = {
    "F": "fetch",
    "D": "decode",
    "E": "execute",
    "M": "memory",
    "W": "writeback",
    "S": "stall",
    "R": "rename",
    "I": "dispatch",
    "C": "complete",
}
# The Makefile the simulator generates for a one-source project.
DEFAULT_MAKEFILE = "ASM = ./main.s\ninclude $(ASE_STUDIO_DEMO_MK)\n"
REPORT_COLUMNS = 60


def fail(message: str, status: int = 2):
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(status)


def require(directory: Path, name: str) -> Path:
    path = directory / name
    if not path.is_file():
        fail(f"missing {path}; run `make run` (CUSTOM_PATCH=1) for this program first")
    return path


def maybe_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.is_file() else {}


def chown_to_owner(path: Path):
    """Hand the file we just wrote back to the user running make."""
    owner = os.environ.get("ASE_OUT_OWNER", "")
    if not owner or os.geteuid() != 0:
        return
    try:
        uid_text, gid_text = owner.split(":")
        uid, gid = int(uid_text), int(gid_text)
    except ValueError:
        return
    try:
        os.chown(path, uid, gid)
    except OSError:
        pass


def march_for(config: dict) -> str:
    """Mirror backend.build()'s -march, so the report documents the real ISA."""
    floating = "fd" if config.get("floatingPointPrecision") == "double" else "f"
    compressed = "c" if config.get("compressedInstructions") else ""
    return f"rv32ima{floating}{compressed}_zicsr_zifencei"


def register_sort_key(register: str):
    match = re.fullmatch(r"([xf])(\d+)", register)
    return (0 if register.startswith("x") else 1, int(match.group(2)) if match else 0)


def visible_rows(data: dict) -> list:
    rows = [row for row in (data.get("dynamicInstructions") or []) if not row.get("squashed")]
    return rows or list(data.get("instructions") or [])


# ------------------------------------------------------------------ sections ---
def summary_section(data: dict) -> list:
    rows = visible_rows(data)
    cycles = data.get("cycles", 0)
    stalls = sum(stage == "S" for row in rows for stage in row.get("cycles", {}).values())
    cpi = round(cycles / len(rows), 3) if rows else 0
    return [
        "## Summary", "",
        "| cycles | instructions | stalls | CPI | code bytes |",
        "| --- | --- | --- | --- | --- |",
        f"| {cycles} | {len(rows)} | {stalls} | {cpi} | {data.get('codeBytes', 0)} |",
        "",
    ]


def config_section(config: dict) -> list:
    lines = ["## CPU characteristics", "",
             "The effective configuration the simulator used: the shared config with",
             "everything it left out filled in by the image, which also pins the",
             "memory/cache and out-of-order knobs.", "",
             "| setting | value |", "| --- | --- |"]
    for key in sorted(config):
        value = config[key]
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        lines.append(f"| `{key}` | {value} |")
    lines.append("")
    return lines


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
              "Architectural state: the final registers do not depend on the CPU model.", ""]
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
    lines = ["## Data memory", ""]
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


def output_section(summary: dict) -> list:
    output = summary.get("output", "").strip()
    return ["## Program output", "",
            "The program's own stdout, with the simulator's chatter removed.", "",
            "```text", output or "(no output)", "```", ""]


def source_section(source_path: Path) -> list:
    lines = ["## Source", "", "```asm"]
    for number, text in enumerate(source_path.read_text(encoding="utf-8").splitlines(), start=1):
        lines.append(f"{number:>4}  {text}")
    lines += ["```", ""]
    return lines


def logs_section(build: Path) -> list:
    lines = ["## Logs", ""]
    for title, name in (("Build log", "build.log"), ("Simulation log", "simulate.log")):
        path = build / name
        if not path.is_file():
            continue
        lines += [f"<details><summary>{title}</summary>", "", "```text",
                  path.read_text(encoding="utf-8").strip(), "```", "", "</details>", ""]
    return lines


# -------------------------------------------------------------------- report ---
def report(args) -> int:
    build = Path(args.build)
    data = json.loads(require(build, "pipeline.json").read_text())
    meta = json.loads(require(build, "meta.json").read_text())
    summary = maybe_json(build / "summary.json")
    source_path = Path(args.source)
    config = meta.get("config") or data.get("configuration") or {}
    stem = meta.get("stem", args.source)

    lines = [
        f"# Lab report — `{stem}`", "",
        f"* `{meta.get('format', '?')}` pipeline · `{march_for(config)}` · gem5 from `{args.image}`",
        f"* source `{source_path.name}` · sha256 `{str(meta.get('sourceSha256', '?'))[:16]}…`",
        "",
    ]
    lines += summary_section(data)
    lines += config_section(config)
    lines += pipeline_section(data, args.columns)
    lines += registers_section(data, summary)
    lines += memory_section(data, summary)
    lines += output_section(summary)
    lines += source_section(source_path)
    lines += logs_section(build)

    out = Path(args.out) if args.out else build / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    chown_to_owner(out)
    print(f"wrote {out}")
    return 0


# ----------------------------------------------------------------------- zip ---
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


def effective_config(build: Path, lab: str, programs: list, fallback: str) -> dict:
    """The configuration a run really used, so the archive documents itself."""
    for program in programs:
        config = maybe_json(build / lab / program.stem / "meta.json").get("config")
        if config:
            return config
    if fallback and Path(fallback).is_file():
        return json.loads(Path(fallback).read_text())
    fail(f"no CPU configuration: run `make run` first, or pass --cpu")


def zip_mode(args) -> int:
    lab_dir = Path(args.lab)
    if not lab_dir.is_dir():
        fail(f"no such lab directory: {args.lab}")
    programs = sorted(lab_dir.glob("*.s"))
    if not programs:
        fail(f"{args.lab}/ contains no .s program")
    build, out = Path(args.build), Path(args.out)
    config = effective_config(build, args.lab, programs, args.cpu)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{args.lab}/README.md",
                         submission_readme(args.lab, programs, build))
        archive.writestr(f"{args.lab}/cpu.json",
                         json.dumps(config, indent=2, sort_keys=True) + "\n")
        for index, program in enumerate(programs, start=1):
            folder = build / args.lab / program.stem
            component = f"{index:02d}-{program.stem}"
            archive.write(program, f"{args.lab}/{component}/main.s")
            for name in ("Makefile", "main.dump", "report.md"):
                if (folder / name).is_file():
                    archive.write(folder / name, f"{args.lab}/{component}/{name}")
            if not (folder / "Makefile").is_file():
                archive.writestr(f"{args.lab}/{component}/Makefile", DEFAULT_MAKEFILE)

    chown_to_owner(out)
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(programs)} program(s))")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    report_parser = sub.add_parser("report", help="render report.md from the JSON dumps")
    report_parser.add_argument("--build", required=True, help="program build directory")
    report_parser.add_argument("--source", required=True, help="path to the .s file")
    report_parser.add_argument("--out", default="", help="output file (default <build>/report.md)")
    report_parser.add_argument("--image", default="?", help="image the run came from")
    report_parser.add_argument("--columns", type=int, default=REPORT_COLUMNS,
                               help="cycles per pipeline table")

    zip_parser = sub.add_parser("zip", help="zip one lab's submission")
    zip_parser.add_argument("--lab", required=True, help="lab directory, e.g. 01")
    zip_parser.add_argument("--build", required=True, help="build tree, e.g. build/gem5")
    zip_parser.add_argument("--cpu", default="", help="CPU config JSON fallback")
    zip_parser.add_argument("--out", required=True, help="output archive")

    args = parser.parse_args()
    return {"report": report, "zip": zip_mode}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
