"""The host tooling: CPU configuration, report, check, golden files, archives."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from conftest import ENV_ROOT, run

ALL_SOURCES = ["01/hello.s", "01/loopsum.s", "02/fib.s"]


# ------------------------------------------------------------------- config ---
def test_config_merges_defaults_the_shared_file_and_the_lab_file(aselab, lab_tree, monkeypatch, capsys):
    status = run(aselab, monkeypatch, "config", "--toml", "cpu.toml",
                 "--lab-toml", "02/cpu.toml", "--out", "build/02/fib/cpu.json")
    assert status == 0
    config = json.loads((lab_tree / "build" / "02" / "fib" / "cpu.json").read_text())
    assert config["forwarding"] is False          # from cpu.toml
    assert config["intMul"] == 3                  # from cpu.toml
    assert config["floatAlu"] == 5                # lab override wins
    assert config["memoryLatency"] == 30          # locked: stays at the default
    assert config["intAlu"] == 1                  # untouched default is filled in
    assert "memoryLatency" in capsys.readouterr().err


def test_config_without_a_lab_file(aselab, lab_tree, monkeypatch):
    run(aselab, monkeypatch, "config", "--toml", "cpu.toml", "--out", "cpu.json")
    config = json.loads((lab_tree / "cpu.json").read_text())
    assert config["forwarding"] is False


def test_config_rejects_a_misspelled_key(aselab, lab_tree, monkeypatch, capsys):
    (lab_tree / "typo.toml").write_text("fowarding = true\n")
    status = run(aselab, monkeypatch, "config", "--toml", "typo.toml", "--out", "typo.json")
    assert status == 2
    assert "fowarding" in capsys.readouterr().err


# ------------------------------------------------------------------- report ---
def test_report_renders_every_section(aselab, lab_tree, monkeypatch):
    status = run(aselab, monkeypatch, "report", "--build", "build/01/hello",
                 "--source", "01/hello.s", "--out", "report.md", "--image", "test-image")
    assert status == 0
    report = (lab_tree / "report.md").read_text()
    for section in ("# Lab report — `01/hello`", "## Summary", "## CPU characteristics",
                    "## Pipeline", "## Pipeline per instruction", "## Register writes",
                    "## Final registers", "## Data memory", "## Memory map",
                    "## Program output", "## Source", "## Logs"):
        assert section in report, section
    assert "| 12 | 4 | 1 | 3.0 | 16 |" in report          # cycles, instrs, stalls, CPI, bytes
    assert "`rv32imaf_zicsr_zifencei`" in report
    assert "test-image" in report
    assert "`forwarding` | True" in report                # the config really used
    assert "| `t2` | `0x0000002a` |" in report            # final register file
    assert "| `0x10000000` | result | `0x0000002a` | stored by the program | 8 |" in report
    assert "| `a7` | `0x00000040` |" in report            # the write log, not the final state
    assert "| 5 |" in report and "`a0`" in report
    assert "```text\nOK\n```" in report or "OK" in report
    assert "   1  # Lab 01" in report                     # numbered source listing
    assert "<details><summary>Build log</summary>" in report


def test_report_shows_the_stall_and_stage_letters(aselab, lab_tree, monkeypatch):
    run(aselab, monkeypatch, "report", "--build", "build/01/hello",
        "--source", "01/hello.s", "--out", "report.md", "--image", "test-image")
    report = (lab_tree / "report.md").read_text()
    assert "| 3 | 19 | `li a2, 3` | · | · | F | D | S | E | M | W | · | · | · | · |" in report
    assert "`S` stall" in report


def test_report_has_no_stall_when_the_trace_has_none(aselab, fixtures, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fixtures.write(tmp_path / "build" / "01" / "hello", pipeline=fixtures.pipeline(stall=False))
    (tmp_path / "01").mkdir()
    (tmp_path / "01" / "hello.s").write_text((ENV_ROOT / "01" / "hello.s").read_text())
    run(aselab, monkeypatch, "report", "--build", "build/01/hello",
        "--source", "01/hello.s", "--out", str(tmp_path / "report.md"), "--image", "x")
    report = (tmp_path / "report.md").read_text()
    assert "| 3 | 19 | `li a2, 3` | · | · | F | D | E | M | W | · | · | · | · |" in report
    assert "| 12 | 4 | 0 |" in report                       # no stall counted


def test_report_chunks_a_long_trace_into_several_tables(aselab, lab_tree, monkeypatch):
    run(aselab, monkeypatch, "report", "--build", "build/01/hello", "--source", "01/hello.s",
        "--out", "wide.md", "--columns", "4", "--image", "x")
    wide = (lab_tree / "wide.md").read_text()
    assert wide.count("| # | line | instruction |") == 3     # 12 cycles / 4 columns


def test_report_fails_with_a_clear_message_without_results(aselab, lab_tree, monkeypatch, capsys):
    status = run(aselab, monkeypatch, "report", "--build", "build/02/fib",
                 "--source", "02/fib.s", "--out", "missing.md", "--image", "x")
    assert status == 2
    assert "run `make run`" in capsys.readouterr().err


# -------------------------------------------------------------------- check ---
def test_check_passes_against_a_matching_golden(aselab, lab_tree, monkeypatch, capsys):
    (lab_tree / "01" / "hello.expected").write_text(
        json.dumps(aselab.golden(json.loads((lab_tree / "build/01/hello/summary.json").read_text())),
                   indent=2, sort_keys=True))
    status = run(aselab, monkeypatch, "check", "--sources", *ALL_SOURCES)
    output = capsys.readouterr().out
    assert status == 1                       # the other two programs have no result yet
    assert "ok    01/hello" in output
    assert "skip  01/loopsum" in output


def test_check_fails_and_explains_a_changed_result(aselab, lab_tree, monkeypatch, capsys):
    golden = aselab.golden(json.loads((lab_tree / "build/01/hello/summary.json").read_text()))
    golden["registers"]["t2"] = "0x00000000"
    golden["memory"]["0x10000000"] = "0x00000000"
    (lab_tree / "01" / "hello.expected").write_text(json.dumps(golden, indent=2, sort_keys=True))
    status = run(aselab, monkeypatch, "check", "--sources", "01/hello.s")
    output = capsys.readouterr().out
    assert status == 1
    assert "FAIL  01/hello" in output
    assert "registers: t2: expected 0x00000000 != actual 0x0000002a" in output
    assert "memory: 0x10000000: expected 0x00000000 != actual 0x0000002a" in output
    assert "make update-expected" in output


def test_check_fails_on_a_changed_output(aselab, lab_tree, monkeypatch, capsys):
    golden = aselab.golden(json.loads((lab_tree / "build/01/hello/summary.json").read_text()))
    golden["output"] = "55"
    (lab_tree / "01" / "hello.expected").write_text(json.dumps(golden, indent=2, sort_keys=True))
    status = run(aselab, monkeypatch, "check", "--sources", "01/hello.s")
    output = capsys.readouterr().out
    assert status == 1
    assert "output differs" in output


def test_check_skips_a_program_without_a_golden_file(aselab, lab_tree, monkeypatch, capsys):
    status = run(aselab, monkeypatch, "check", "--sources", "01/hello.s")
    assert status == 1
    assert "no golden file" in capsys.readouterr().out


def test_update_expected_writes_a_golden_file_that_then_passes(aselab, lab_tree, monkeypatch, capsys):
    status = run(aselab, monkeypatch, "update-expected", "--sources", "01/hello.s")
    assert status == 0
    golden = json.loads((lab_tree / "01" / "hello.expected").read_text())
    assert golden["registers"]["t2"] == "0x0000002a"
    assert golden["memory"]["0x10000000"] == "0x0000002a"
    assert golden["output"] == "OK"
    assert run(aselab, monkeypatch, "check", "--sources", "01/hello.s") == 0
    assert "ok    01/hello" in capsys.readouterr().out


def test_update_expected_skips_programs_that_have_not_run(aselab, lab_tree, monkeypatch, capsys):
    assert run(aselab, monkeypatch, "update-expected", "--sources", *ALL_SOURCES) == 0
    output = capsys.readouterr().out
    assert "updated 2 golden file(s)" in output
    assert not (lab_tree / "02" / "fib.expected").exists()


# ---------------------------------------------------------------------- zip ---
def test_zip_builds_the_submission_layout(aselab, lab_tree, monkeypatch):
    for name in ("hello", "loopsum"):
        (lab_tree / "build" / "01" / name / "main.dump").write_text("main.dump")
        (lab_tree / "build" / "01" / name / "Makefile").write_text("ASM = ./main.s\n")
        (lab_tree / "build" / "01" / name / "report.md").write_text("# report")
    assert run(aselab, monkeypatch, "zip", "--lab", "01", "--out", "01.zip") == 0
    with zipfile.ZipFile(lab_tree / "01.zip") as archive:
        names = sorted(archive.namelist())
        assert names == [
            "01/01-hello/Makefile", "01/01-hello/main.dump", "01/01-hello/main.s",
            "01/01-hello/report.md", "01/02-loopsum/Makefile", "01/02-loopsum/main.dump",
            "01/02-loopsum/main.s", "01/02-loopsum/report.md", "01/README.md", "01/cpu.toml",
        ]
        assert archive.read("01/01-hello/main.s").decode() == \
            (ENV_ROOT / "01" / "hello.s").read_text()
        assert archive.read("01/cpu.toml").decode().startswith("# forwarding disabled")
        readme = archive.read("01/README.md").decode()
        assert "`hello`" in readme and "`loopsum`" in readme


def test_zip_uses_the_lab_cpu_file_when_present(aselab, lab_tree, monkeypatch):
    (lab_tree / "build" / "02" / "fib").mkdir(parents=True)
    (lab_tree / "build" / "02" / "fib" / "summary.json").write_text("{}")
    assert run(aselab, monkeypatch, "zip", "--lab", "02", "--out", "02.zip") == 0
    with zipfile.ZipFile(lab_tree / "02.zip") as archive:
        assert archive.read("02/cpu.toml").decode().strip() == "floatAlu = 5\nmemoryLatency = 99"


def test_zip_writes_the_makefile_when_the_run_did_not(aselab, lab_tree, monkeypatch):
    assert run(aselab, monkeypatch, "zip", "--lab", "01", "--out", "01.zip") == 0
    with zipfile.ZipFile(lab_tree / "01.zip") as archive:
        assert archive.read("01/01-hello/Makefile").decode() == \
            "ASM = ./main.s\ninclude $(ASE_STUDIO_DEMO_MK)\n"


def test_zip_refuses_a_lab_without_programs(aselab, lab_tree, monkeypatch, capsys):
    (lab_tree / "03").mkdir()
    assert run(aselab, monkeypatch, "zip", "--lab", "03", "--out", "03.zip") == 2
    assert "no .s program" in capsys.readouterr().err


# --------------------------------------------------------------------- labs ---
def test_labs_lists_what_it_found(aselab, lab_tree, monkeypatch, capsys):
    assert run(aselab, monkeypatch, "labs") == 0
    output = capsys.readouterr().out
    assert "01: hello, loopsum" in output
    assert "02: fib" in output


def test_labs_says_so_when_there_is_nothing(aselab, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert run(aselab, monkeypatch, "labs") == 0
    assert "no lab directory" in capsys.readouterr().out
