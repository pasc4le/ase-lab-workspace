# Lab 01 — a first program: syscalls and a store
#
# Writes a message with the write() system call, then computes 21 * 2 = 42 and
# stores it in the variable `result`.  Small enough that the whole pipeline fits
# in one screen: 8 instructions.
#
# Expected result (checked by `make check`):
#   result = 0x0000002a (42)
#   t2     = 0x0000002a

.section .data
# A word of storage the program initialises at run time.
result:
    .word 0

.section .rodata
# The message handed to write(): three bytes, no terminating zero needed.
message:
    .ascii "OK\n"

.section .text
# _start is where the simulator begins and must stay visible to the linker.
.globl _start
_start:
    # write(1, message, 3)
    li a0, 1          # file descriptor 1 = stdout
    la a1, message    # buffer address
    li a2, 3          # number of bytes
    li a7, 64         # system call number for write
    ecall

    # 21 * 2, then store the product in `result`.
    li t0, 21
    li t1, 2
    mul t2, t0, t1
    la t3, result
    sw t2, 0(t3)

# The End block stops the program and returns control to the simulator.
End:
    li a0, 0
    li a7, 93
    ecall
