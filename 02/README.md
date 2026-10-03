# Lab 02 — memory and dependencies

Two programs that stress the two things lab 01 deliberately avoided: data memory
and dependent instructions.

| program | what it shows |
| --- | --- |
| `memcopy.s` | copies a four-word array; every iteration is one load and one store, so the memory column of the report has two entries per iteration |
| `fib.s` | the tenth Fibonacci number; each iteration depends on the previous two, so the pipeline cannot overlap iterations |

```bash
make run LAB=02
make check LAB=02
make 02
```

`fib.s` is the interesting one: compare its cycles-per-instruction with
`memcopy.s` in the two reports, then set `forwarding = false` in `cpu.toml` and
run again. With forwarding disabled, the dependent `add`/`mv` chain in `fib.s`
must wait for write-back, and the stall count in the report grows — the same
program, the same result, a different pipeline.

Expected results: `memcopy.s` leaves `dest = {1, 2, 3, 4}` with `source`
untouched; `fib.s` leaves `fib10 = 0x37` (55). `make check` compares the final
registers, data memory and output against `memcopy.expected` / `fib.expected`,
which `make update-expected` records from a run you trust (they are not shipped,
so that the golden files always come from a run on your machine).
