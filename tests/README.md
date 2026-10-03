# Tests

Two things are checked here, neither of which needs Docker or gem5:

| what | how |
| --- | --- |
| the host tooling (`tools/aselab.py`): CPU-config merging, the Markdown report, result checking, golden files, submission archives | `uv run pytest tests -q` — 29 tests against records shaped exactly like the container's output |
| the compile path, through the Makefile | `bash tests/make-fake-image.sh` then `make build DOCKER=tests/shim/docker` — compiles the lab programs with a real RISC-V toolchain |

## Why a Docker shim

`tests/shim/docker` is a `docker` stand-in: it understands the `docker run` shape
the Makefile emits, maps `/work` onto the host mount, points
`ASE_STUDIO_HOST_ROOT` at a locally assembled image root and runs
`tools/incontainer.py` with the host interpreter. That makes the environment
testable on a machine with no Docker daemon (CI, or a laptop without one), and
what it exercises is the real thing — the toolchain, the project layout the
backend expects, the container script, the artifact plumbing.

`tests/make-fake-image.sh` assembles that image root in `build/fake-image/`:
symlinks to `ase_studio/`, `setup_default`, `gem5/`, `programs/demo.mk` and a
RISC-V toolchain (`$ASE_TOOLCHAIN`, or one on `PATH`, or a downloaded xPack tree).
It replaces `gem5.opt` with a stub that fails with a message, so **`make build` is
the target to run this way**; a real `make run` needs the container.

## What is not covered

The gem5 simulation itself. It needs the container (or a gem5 build with the
PoliTo fork's `--ase-*` flags), so no test here can assert on a real trace;
`tests/fixtures.py` reproduces the record shapes that `ase_studio/backend.py`
produces, which is what the report/check logic consumes. The container smoke test
in `.github/workflows/publish-container.yml` is what exercises a real
compile-and-simulate path.

```bash
uv run pytest tests -q                    # host tooling
bash tests/make-fake-image.sh && make build DOCKER=tests/shim/docker
```
