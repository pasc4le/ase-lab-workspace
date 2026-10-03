# Lab 01 — a loop: 1 + 2 + ... + 10
#
# The first counting loop of the course.  Watch how the branch keeps the pipeline
# from retiring an instruction every cycle: the `ble` is resolved in the
# execution stage, so the instructions that follow it in the pipeline are
# squashed until the branch is taken.
#
# Expected result (checked by `make check`):
#   total = 0x00000037 (55)
#   t2    = 0x00000037

.section .data
total:
    .word 0

.section .text
.globl _start
_start:
    li t0, 1          # the number being added
    li t1, 10         # how far to count
    li t2, 0          # the running sum

loop:
    add t2, t2, t0    # sum += counter
    addi t0, t0, 1    # counter += 1
    ble t0, t1, loop  # keep going while counter <= 10

    la t3, total      # store the answer
    sw t2, 0(t3)

End:
    li a0, 0
    li a7, 93
    ecall
