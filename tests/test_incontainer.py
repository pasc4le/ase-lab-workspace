"""The container-side script's pure logic.

``tools/incontainer.py`` runs inside the image with the standard library only, so
its data-shaping functions can be imported and tested directly here; only
``load_backend()`` needs the image.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


incontainer = load("incontainer")


def test_fold_registers_applies_writes_in_cycle_order():
    deltas = {"10": {"t2": "0x0000000a"}, "3": {"t2": "0x00000001", "a0": "0x1"}}
    assert incontainer.fold_registers(deltas) == {"t2": "0x0000000a", "a0": "0x1"}


def test_register_and_address_sort_keys():
    registers = ["x10", "f2", "x2", "f10"]
    assert sorted(registers, key=incontainer.register_sort_key) == ["x2", "x10", "f2", "f10"]
    assert sorted(["0x10000010", "0x10000004"], key=incontainer.address_sort_key) == \
        ["0x10000004", "0x10000010"]


def test_final_memory_keeps_initial_values_and_applies_writes():
    initial = {"0x10000000": {"value": "0x00000000", "bits": 32, "access": "initial value"}}
    deltas = {
        "4": {"0x10000000": {"value": "0x00000005", "bits": 32, "access": "read"}},
        "9": {"0x10000000": {"value": "0x0000002a", "bits": 32, "access": "write"}},
    }
    memory = incontainer.final_memory(initial, deltas, [{"address": "0x10000000", "label": "result"}])
    assert memory["0x10000000"]["value"] == "0x0000002a"
    assert memory["0x10000000"]["source"] == "stored by the program"
    assert memory["0x10000000"]["cycle"] == "9"
    assert memory["0x10000000"]["label"] == "result"


def test_final_memory_ignores_reads():
    initial = {"0x10000000": {"value": "0x00000007", "bits": 32}}
    deltas = {"4": {"0x10000000": {"value": "0x00000007", "bits": 32, "access": "read"}}}
    memory = incontainer.final_memory(initial, deltas, [])
    assert memory["0x10000000"]["value"] == "0x00000007"
    assert memory["0x10000000"]["source"] == "ELF initial value"


def test_final_memory_records_a_store_to_an_address_the_elf_never_declared():
    deltas = {"7": {"0x10000040": {"value": "0x00000001", "bits": 32, "access": "write"}}}
    memory = incontainer.final_memory({}, deltas, [])
    assert memory == {"0x10000040": {"value": "0x00000001", "bits": 32, "source":
                                     "stored by the program", "cycle": "7", "label": ""}}


def test_program_output_keeps_only_the_programs_own_lines():
    text = ("$ gem5 build/RISCV/gem5.opt --outdir=x config.py -c main.elf\n"
            "gem5 Simulator System.\n"
            "warn: Build-specific flag used.\n"
            "info: a notice\n"
            "OK 42\n"
            "second line\n"
            "Exiting @ tick 123 because exiting with last active thread context\n")
    assert incontainer.program_output(text) == "OK 42\nsecond line"


def test_program_output_of_a_silent_program_is_empty():
    assert incontainer.program_output("gem5 Simulator System.\nwarn: nothing here\n") == ""


def test_summarize_sorts_registers_naturally():
    registers = {"x10": "0x1", "f0": "0x2", "x2": "0x3"}
    result = incontainer.summarize({}, registers, {"0x10000000": {"value": "0x4"}}, "out\n")
    assert list(result["registers"]) == ["x2", "x10", "f0"]
    assert result["memory"] == {"0x10000000": "0x4"}
    assert result["output"] == "out\n"


def test_project_name_for_is_a_valid_project_name():
    assert incontainer.project_name_for("01/hello") == "lab_01_hello"
    assert incontainer.project_name_for("10/linked-list") == "lab_10_linked_list"


def test_limited_run_command_keeps_the_normal_output(tmp_path):
    command = incontainer.limited_run_command(30)
    status, output = command(["echo", "hello"], tmp_path, os.environ)
    assert status == 0
    assert output == "$ echo hello\nhello\n"


def test_limited_run_command_stops_a_runaway_program(tmp_path):
    # gem5 has no timeout of its own; a program that never reaches End: would
    # otherwise hang the container forever.
    command = incontainer.limited_run_command(1)
    status, output = command(["sleep", "30"], tmp_path, os.environ)
    assert status == 124
    assert "Timed out after 1s" in output
    assert "never reaches" in output
