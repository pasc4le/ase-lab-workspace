# Lab 01 — a first pipeline

Two programs to get the tooling and the pipeline diagram into focus. Both are
small enough that the whole trace fits in one report.

| program | what it shows |
| --- | --- |
| `hello.s` | a system call (`write`) and a store to memory — 8 instructions, one pass through the pipeline |
| `loopsum.s` | a counting loop: 1 + 2 + … + 10, and what a taken branch does to the instructions behind it |

```bash
make run LAB=01          # compile, simulate, write build/01/*/report.md
make check LAB=01        # compare the results with the .expected files
make 01                  # …and produce 01.zip ready to submit
```

Expected results (what the program must compute):

| program | result |
| --- | --- |
| `hello.s` | `result = 0x2a` (42), `t2 = 0x2a`, and `OK` on stdout |
| `loopsum.s` | `total = 0x37` (55), `t2 = 0x37` |

Those facts are what `make check` compares: it runs each program and diffs the
final registers, the data memory and the printed output against
`hello.expected` / `loopsum.expected`. Those two files are not in the repository —
record them from a run you trust with `make update-expected`, after which
`make check` guards against accidental changes to the programs.

Start with `build/01/hello/report.md`: the cycle-by-cycle pipeline table should
read `F D E M W` for `li t0, 21`, and `hello.s`'s `mul` should show the latency
of the integer multiplier from `cpu.toml`.

Things worth trying, changing one line of `cpu.toml` at a time and re-running
(`make run LAB=01` re-simulates because `cpu.toml` changed):

- `forwarding = false` — how many stall cycles (`S`) appear between the two
  dependent instructions in `hello.s`?
- `intMul = 4` — the `mul` in `hello.s` now holds the `E` stage for four cycles.
- `floatDivPipelined`/`floatAlu` — not visible in these two programs; they are
  there for the floating-point labs.
