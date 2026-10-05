# ASE Laboratory Environment

Compile every `<lab>/<program>.s` to an ELF, then run it. Everything happens in
Docker; the host only needs Docker.

```bash
make image              # build the reusable riscv64 image (once)
make build              # build/gem5/<lab>/<program>/main.elf (or build/riscv/…)
make run                # run every ELF
make debug PROG=01/hello   # open an ELF in gdb-multiarch (or pwndbg)
make help               # the target list
```

Programs are discovered, never listed: to add a lab, create `03/`; to add a
program, drop `03/myprogram.s` in it. `make build PROG=03/myprogram` restricts
any target to a single program.

## The two paths

`CUSTOM_PATCH` selects how a program is built and run:

| `CUSTOM_PATCH` | build | run |
| --- | --- | --- |
| `1` (default) | the ASR gem5 image, via `tools/incontainer.py` | gem5 simulation |
| `0` | the plain riscv64 image (`make image`) | the ELF runs natively |

The two paths use separate trees (`build/gem5/`, `build/riscv/`), so a gem5 rv32
build is never mistaken for a native rv64 one. `make clean` removes both.

`make debug` always uses the riscv64 image, whatever `CUSTOM_PATCH` is, and
reads both the rv32 and the rv64 builds. See [Debugging](#debugging).

## Requirements

- **Docker**.
- The gem5 image, already pulled (`ghcr.io/pasc4le-labs/ase_riscv_gem5_sim`,
  tag `v1.0.0-a.1` by default) for `CUSTOM_PATCH=1`.
- The riscv64 image, built once with `make image` (defined in `Dockerfile.riscv`:
  `ubuntu:24.04` for `linux/riscv64` with `gcc`, `binutils`, `gdb-multiarch`,
  `qemu-user` and pwndbg), for `CUSTOM_PATCH=0` and `make debug`.  Building it
  needs network access (pwndbg is fetched from `install.pwndbg.re`).

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
| `CUSTOM_PATCH` | `1` | `1`: gem5 image; `0`: native riscv64 |
| `IMAGE` | `ghcr.io/pasc4le-labs/…:v1.0.0-a.1` | the gem5 image |
| `RISCV_IMAGE` | `ase-riscv:24.04` | the image `make image` builds |
| `PLATFORM` | `linux/riscv64` | platform for the riscv64 image |
| `TIMEOUT` | `180` | wall-clock cap per gem5 run, in seconds |
| `PROG` | (all) | restrict to one program, e.g. `01/hello` |
| `DEBUGGER` | `gdb` | `make debug` front end: `gdb` (gdb-multiarch) or `pwndbg` |

Any of these can be put in a git-ignored `.env` file instead of passed on the
command line; copy `.env.example` to start. Command-line values still win.

## Debugging

```bash
make debug PROG=01/hello                        # gdb-multiarch
DEBUGGER=pwndbg make debug PROG=01/hello        # pwndbg
```

`DEBUGGER` picks the front end, and also works from `.env`. `gdb` (the default)
is `gdb-multiarch`; `pwndbg` is the enhanced GDB (`pwndbg` portable release,
which bundles its own GDB 17.2 built `--enable-targets=all`, so rv32 and rv64
both work) baked into the riscv64 image. Both share the QEMU/gdbstub flow below,
so nothing changes but the UI: pwndbg adds its registers/disassembly/stack
panels, `vmmap` and the rest.

Either way, this opens a debugger on `build/{gem5,riscv}/01/hello/main.elf`.
Because the riscv64 container runs under QEMU user-mode emulation, which does not
implement `ptrace`, gdb cannot launch the inferior itself. Instead
`tools/gdbserver.sh` runs the ELF under `qemu-riscv32`/`qemu-riscv64` and attaches
gdb to QEMU's gdbstub (`target remote`). The program is already paused at its
entry point, so set breakpoints and use **`continue`** -- `run` will not work:

```
(gdb) break Main
(gdb) continue
```

Stepping (`stepi`, `nexti`), registers, memory and breakpoints all work.
