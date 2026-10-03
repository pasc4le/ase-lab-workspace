"""Shared setup: a miniature lab tree plus the loader for the host tooling."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ENV_ROOT = HERE.parent
TOOLS = ENV_ROOT / "tools"


def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def aselab():
    return load_tool("aselab")


@pytest.fixture
def fixtures():
    spec = importlib.util.spec_from_file_location("fixtures", HERE / "fixtures.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["fixtures"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def lab_tree(tmp_path, fixtures, monkeypatch):
    """A working directory with two labs, sources and recorded results."""
    (tmp_path / "cpu.toml").write_text(
        "# forwarding disabled for this lab session\n"
        "forwarding = false\n"
        "intMul = 3\n"
    )
    (tmp_path / "01").mkdir()
    (tmp_path / "02").mkdir()
    shutil.copy(ENV_ROOT / "01" / "hello.s", tmp_path / "01" / "hello.s")
    shutil.copy(ENV_ROOT / "01" / "loopsum.s", tmp_path / "01" / "loopsum.s")
    shutil.copy(ENV_ROOT / "02" / "fib.s", tmp_path / "02" / "fib.s")
    # A lab-local override, including a knob this image locks.
    (tmp_path / "02" / "cpu.toml").write_text("floatAlu = 5\nmemoryLatency = 99\n")
    fixtures.write(tmp_path / "build" / "01" / "hello")
    fixtures.write(tmp_path / "build" / "01" / "loopsum", stem="01/loopsum",
                   summary=fixtures.summary(output="55"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(aselab, monkeypatch, *argv) -> int:
    """Invoke the CLI the way the Makefile does, returning its exit status."""
    monkeypatch.setattr(sys, "argv", ["aselab.py", *argv])
    try:
        return aselab.main()
    except SystemExit as exit_code:
        return int(exit_code.code or 0)
