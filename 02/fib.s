# Lab 02 — dependent instructions: the tenth Fibonacci number
#
# Each iteration needs the two previous results, so the loop cannot fill the
# pipeline as well as the copy loop: consecutive iterations are dependent on one
# another.  Compare the cycles per instruction of this program with
# `02/memcopy.s` in the two reports; with forwarding enabled the dependence costs
# less than it does with `forwarding = false` in cpu.toml.
#
# Expected result (checked by `make check`):
#   fib10 = 0x00000037 (55)

.section .data
fib10:
    .word 0

.section .text
.globl _start
_start:
    li t0, 0          # fib(0)
    li t1, 1          # fib(1)
    li t2, 1          # iteration counter
    li t3, 10         # compute up to fib(10)

loop:
    add t4, t0, t1    # fib(k) = fib(k-1) + fib(k-2)
    mv t0, t1
    mv t1, t4
    addi t2, t2, 1
    blt t2, t3, loop

    la t5, fib10
    sw t4, 0(t5)

End:
    li a0, 0
    li a7, 93
    ecall
