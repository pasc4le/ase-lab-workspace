# `env` — the lab environment

Compile every `<lab>/<program>.s` to an ELF, then run it. Everything happens in
Docker; the host only needs Docker.

```bash
make image              # build the reusable riscv64 image (once)
make build              # build/gem5/<lab>/<program>/main.elf (or build/riscv/…)
make run                # run every ELF
make debug PROG=01/hello   # open an ELF in gdb-multiarch
make help               # the target list
```

Programs are discovered, never listed: to add a lab, create `03/`; to add a
program, drop `03/myprogram.s` in it. `make build PROG=03/myprogram` restricts
any target to a single program.

## The two paths

`CUSTOM_PATH` selects how a program is built and run:

| `CUSTOM_PATH` | build | run |
| --- | --- | --- |
| `1` (default) | the ASR gem5 image, via `tools/incontainer.py` | gem5 simulation |
| `0` | the plain riscv64 image (`make image`) | the ELF runs natively |

The two paths use separate trees (`build/gem5/`, `build/riscv/`), so a gem5 rv32
build is never mistaken for a native rv64 one. `make clean` removes both.

`make debug` always uses the riscv64 image, whatever `CUSTOM_PATH` is: it opens
the ELF in `gdb-multiarch`, which reads both the rv32 and the rv64 builds.

## Requirements

- **Docker**.
- The gem5 image, already pulled (`ghcr.io/pasc4le-labs/ase_riscv_gem5_sim`,
  tag `v1.0.0-a.1` by default) for `CUSTOM_PATH=1`.
- The riscv64 image, built once with `make image` (defined in `Dockerfile.riscv`:
  `ubuntu:24.04` for `linux/riscv64` with `gcc`, `binutils` and `gdb-multiarch`),
  for `CUSTOM_PATH=0` and `make debug`.

Nothing else: no host RISC-V toolchain, no gem5, no `timeout`.

## What a build produces

For `<lab>/<program>.s`, in `build/{gem5,riscv}/<lab>/<program>/`:

| file | what it is |
| --- | --- |
| `main.elf` | the compiled program |
| `main.dump` | the disassembly (gem5 path only) |
| `build.log`, `simulate.log` | the raw compiler / gem5 output (gem5 path only) |

## Variables

| variable | default | meaning |
| --- | --- | --- |
| `CUSTOM_PATH` | `1` | `1`: gem5 image; `0`: native riscv64 |
| `IMAGE` | `ghcr.io/pasc4le-labs/…:v1.0.0-a.1` | the gem5 image |
| `RISCV_IMAGE` | `ase-riscv:24.04` | the image `make image` builds |
| `PLATFORM` | `linux/riscv64` | platform for the riscv64 image |
| `TIMEOUT` | `180` | wall-clock cap per gem5 run, in seconds |
| `PROG` | (all) | restrict to one program, e.g. `01/hello` |

## Note

`tools/aselab.py`, `cpu.toml` and the report/check/zip tooling are no longer
used by the Makefile; the gem5 path now only compiles and simulates. They are
left in the tree in case the reports are wanted back.
