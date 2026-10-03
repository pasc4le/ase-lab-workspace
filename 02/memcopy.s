# Lab 02 — loads and stores: copying an array
#
# Copies four words from `source` to `dest`, one word per iteration.  This is the
# program to look at when the question is memory: every iteration appears twice
# in the memory column of the report, once as a read of `source` and once as a
# write of `dest`.
#
# Expected result (checked by `make check`):
#   dest  = { 1, 2, 3, 4 }, i.e. 0x10000010 = 1, 0x10000014 = 2, …
#   source is untouched.

.section .data
source:
    .word 1, 2, 3, 4
dest:
    .word 0, 0, 0, 0

.section .text
.globl _start
_start:
    la t0, source     # read pointer
    la t1, dest       # write pointer
    li t2, 0          # index
    li t3, 4          # number of words

loop:
    slli t4, t2, 2    # byte offset = index * 4
    add t5, t0, t4    # &source[index]
    lw t6, 0(t5)      # load the word
    add t5, t1, t4    # &dest[index]
    sw t6, 0(t5)      # store it
    addi t2, t2, 1    # next index
    blt t2, t3, loop  # while index < 4

End:
    li a0, 0
    li a7, 93
    ecall
