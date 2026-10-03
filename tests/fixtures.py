"""Records shaped exactly like the ones the container produces.

The container gets its pipeline, register and memory facts from
``ase_studio/backend.py`` -- the same parser the web UI uses -- so the tooling
here never invents a format: these fixtures reproduce the structures documented
by that module (``pipeline()``, ``parse_exec_playback()``, ``elf_initial_memory()``,
``elf_memory_map()``) and let the host-side report/check/zip logic be tested
without Docker, gem5, or a toolchain.
"""

from __future__ import annotations

import json
from pathlib import Path

CONFIG = {
    "cpu": "in-order",
    "intAlu": 1, "intMul": 1, "intDiv": 1,
    "floatAlu": 2, "floatMul": 7, "floatDiv": 8,
    "intAluPipelined": True, "intMulPipelined": True, "intDivPipelined": True,
    "floatAluPipelined": True, "floatMulPipelined": True, "floatDivPipelined": False,
    "forwarding": True, "compressedInstructions": False,
    "floatingPointPrecision": "single",
    "memoryMode": "direct", "cacheStalls": False,
    "instructionMemoryLatency": 1, "dataReadLatency": 1, "dataWriteLatency": 1,
    "iCacheSize": "32kB", "dCacheSize": "32kB", "cacheLine": 64,
    "cacheLatency": 2, "memoryLatency": 30,
    "fetchWidth": 2, "decodeWidth": 2, "renameWidth": 2, "dispatchWidth": 2,
    "issueWidth": 2, "writebackWidth": 2, "commitWidth": 2,
    "robEntries": 64, "iqEntries": 128, "lqEntries": 32, "sqEntries": 32,
    "o3VisibleStages": ["issue", "execute", "memory", "cdb", "commit"],
    "branchPredictor": "local", "speculativeExecution": True,
    "outOfOrderExecution": True, "o3EvaluationLabel": "",
}

RESULT_ADDRESS = "0x10000000"


def _row(address, instruction, cycles, line, iterations=1):
    return {
        "address": address,
        "instruction": instruction,
        "cycles": {str(cycle): stage for cycle, stage in cycles},
        "sourceLine": line,
        "iterations": iterations,
        "squashed": False,
        "inferredGaps": [],
    }


def pipeline(cycles: int = 12, stall: bool = True):
    """A four-instruction trace, optionally with a stall between two dependents."""
    rows = [
        _row("0x10094", "li a0, 1", [(1, "F"), (2, "D"), (3, "E"), (4, "M"), (5, "W")], 17),
        _row("0x10098", "la a1, message", [(2, "F"), (3, "D"), (4, "E"), (5, "M"), (6, "W")], 18),
    ]
    if stall:
        rows.append(_row("0x1009c", "li a2, 3",
                         [(3, "F"), (4, "D"), (5, "S"), (6, "E"), (7, "M"), (8, "W")], 19))
    else:
        rows.append(_row("0x1009c", "li a2, 3",
                         [(3, "F"), (4, "D"), (5, "E"), (6, "M"), (7, "W")], 19))
    rows.append(_row("0x100a0", "ecall", [(9, "F"), (10, "D"), (11, "E"), (12, "W")], 20))
    return {
        "format": "minor",
        "cycles": cycles,
        "codeBytes": 16,
        "instructions": rows,
        "dynamicInstructions": list(rows),
        "registerDeltas": {
            "5": {"a0": "0x00000001"},
            "6": {"a1": "0x00010000"},
            "8": {"a2": "0x00000003"},
            "11": {"a7": "0x00000040"},
        },
        "pcDeltas": {str(cycle): row["address"] for cycle, row in
                     enumerate(rows, start=1)},
        "memoryDeltas": {
            "8": {RESULT_ADDRESS: {"value": "0x0000002a", "bits": 32,
                                   "access": "write", "pc": "0x100a4"}},
        },
        "jumps": [],
        "dataSymbols": [{"address": RESULT_ADDRESS, "label": "result", "size": 4}],
        "initialMemory": {RESULT_ADDRESS: {"value": "0x00000000", "bits": 32,
                                           "access": "initial value", "pc": ""}},
        "memoryMap": [
            {"name": ".text", "kind": "code", "start": "0x10094", "end": "0x100a4", "size": 16},
            {"name": ".rodata", "kind": "read-only data", "start": "0x100a8", "end": "0x100aa", "size": 3},
            {"name": ".data", "kind": "data", "start": "0x10000000", "end": "0x10000003", "size": 4},
        ],
    }


def summary(output: str = "OK"):
    return {
        "output": output,
        "registers": {"a0": "0x00000001", "a1": "0x00010000", "a2": "0x00000003",
                      "a7": "0x00000040", "t2": "0x0000002a"},
        "memory": {RESULT_ADDRESS: "0x0000002a"},
    }


def meta(stem: str = "01/hello", source: str = "hello.s", cycles: int = 12):
    return {
        "stem": stem,
        "project": "lab_" + stem.replace("/", "_"),
        "source": source,
        "sourceSha256": "0" * 64,
        "config": CONFIG,
        "format": "minor",
        "cycles": cycles,
        "instructions": 4,
        "buildOk": True,
        "simulateOk": True,
    }


BUILD_LOG = """$ make clean
rm -f main.elf main.dump
$ make
riscv-none-elf-gcc -o main.elf ./main.s -O0  -mcmodel=medlow ...
riscv-none-elf-objdump -d main.elf > main.dump
"""

# The simulation log as the backend hands it over for display: simulator chatter
# plus the program's own write() output, which lands on gem5's stdout.
SIMULATE_LOG = """$ /app/tools/gem5/build/RISCV/gem5.opt --debug-flags=MinorGUI,Exec --outdir=/app/results/lab_01_hello --verbose /app/gem5/riscv_in_order_hen_patt.py --caches --cpu-type MinorCPU -c main.elf
gem5 Simulator System.  http://gem5.org
gem5 is copyrighted software; use the --copyright option for details.

gem5 version 23.0.0.1
warn: The `MinorGUI` debug flag is specific to this build.
OK
Exiting @ tick 123456 because exiting with last active thread context
"""


def write(directory: Path, stem: str = "01/hello", **overrides) -> Path:
    """Lay the fixture out the way the container does and return the directory."""
    directory.mkdir(parents=True, exist_ok=True)
    payloads = {
        "pipeline.json": overrides.get("pipeline", pipeline()),
        "meta.json": overrides.get("meta", meta(stem)),
        "summary.json": overrides.get("summary", summary()),
    }
    for name, payload in payloads.items():
        (directory / name).write_text(json.dumps(payload, indent=1, sort_keys=True))
    (directory / "build.log").write_text(BUILD_LOG)
    (directory / "simulate.log").write_text(SIMULATE_LOG)
    return directory
