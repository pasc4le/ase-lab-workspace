# `env` — the lab environment

A drop-in workflow for the ASE RISC-V + gem5 simulator: **compiling and simulating
happen in the container image**, the reports and the submission archives are
produced on the host.

```bash
make                # compile and simulate every program in every lab
make check          # verify the results against the golden files
make 01             # do everything for lab 01, then write 01.zip
make help           # the full target list
```

Everything is discovered, nothing is listed: to add a lab, create `03/`; to add a
program, drop `03/myprogram.s` in it. All targets pick it up (`make labs` shows
what was found).

## What a run produces

For `<lab>/<program>.s`, in `build/<lab>/<program>/`:

| file | what it is |
| --- | --- |
| `main.elf`, `main.dump` | the compiled program and its disassembly |
| `report.md` | **the deliverable**: cycle-by-cycle pipeline table, pipeline per instruction, every register write, the final register file, the data memory (initial values, what the program stored and when), the ELF memory map, the program's output, the source listing and both logs |
| `pipeline.json` | every fact gem5 produced, exactly as the web UI receives it |
| `summary.json` | the architectural result (registers, memory, output) — what `make check` compares |
| `meta.json` | the CPU characteristics and the source hash this run used |
| `build.log`, `simulate.log` | the raw `make` and gem5 output |
| `cpu.json` | the merged CPU configuration handed to the container |

`report.md` is the one to read: it is generated from `pipeline.json` with the
same reading of the trace the GUI uses, so a report and the browser show the same
pipeline.

## CPU characteristics

`cpu.toml` holds the same knobs as the GUI's CPU configuration dialog
(functional-unit latencies, which units are pipelined, forwarding, the
instruction set). A lab can override them with `<lab>/cpu.toml`, or a single run
can use another file:

```bash
make run LAB=02 CPU=02/cpu.toml
```

Every report states the configuration that was in effect. Note which knobs this
image **locks**: `ENABLE_MEMORY_CONFIGURATION` and `ENABLE_MULTI_ISSUE_CPU` are
`false` in `ase_studio/backend.py`, so the out-of-order model and the whole
cache/memory group are reset by the backend and listed as locked in the report.
The tooling warns if a lab sets one of them.

## Checking results

`make check` compares each program's **architectural** result — the final
registers, the data memory and the program's printed output — against
`<lab>/<program>.expected`. Those facts do not depend on the CPU model, so a
check does not break when you change `cpu.toml`; only the timing in the report
changes. That is deliberate: the golden files assert what the program computes,
the report explains how long it took.

```bash
make update-expected     # after an intentional change to a program
make check LAB=02        # a single lab
```

A missing golden file is reported as `skip` and makes `make check` exit
non-zero, so a fresh lab cannot silently pass.

## Submission archives

`make 01` writes `01.zip` with the layout the course's own submission pipeline
uses:

```
01/
├── README.md                  # generated: what the archive contains
├── cpu.toml                   # the CPU characteristics the results came from
├── 01-hello/
│   ├── main.s  Makefile  main.dump  report.md
└── 02-loopsum/
    └── …
```

## Requirements

- **Docker** with the image built (`make image` builds and tags it from this
  repository; the default tag is `v1.0.0-a.1`).
- **uv** for the report tooling: `uv run` creates `.venv` from `pyproject.toml`
  on first use.

Nothing else: no GNU `timeout` (the simulation cap lives inside the container,
`TIMEOUT=180` by default), no RISC-V toolchain, no gem5. The image is used as a
plain program runner — no server, no published port, `--network none`.

## Verification

`tests/` holds the checks for this environment. They need neither Docker nor
gem5: the Docker shim runs the container's own script on the host against a
locally assembled image root (see `tests/README.md`).

```bash
uv run pytest tests -q          # host tooling: report, check, zip, config
bash tests/make-fake-image.sh   # assemble the fake image root
make build DOCKER=tests/shim/docker   # really compiles, with the host toolchain
```
