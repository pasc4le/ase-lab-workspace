.section .data
v1: .byte   2, 6, -3, 11, 9, 18, -13, 16, 5, 1
v2: .byte   4, 2, -13, 3, 9, 9, 7, 16, 4, 7
v3: .space  10

flags: .byte 0

.section .text
.globl _start
_start:
Main:
  la s1, v1
  la s2, v2
  la s3, v3
  mv s4, s3

  li s6, 1
  li s7, 1

loop_v1:
  lb a0, 0(s1)
  mv t0, s2

loop_v2:
  lb a1, 0(t0)
  beq a1, a0, insert_v3

  addi t0, t0, 1
  bne t0, s3, loop_v2
  j no_insert_v3

insert_v3:
  sw a0, 0(s4)
  addi s4, s4, 1

no_insert_v3:
  addi s1, s1, 1
  bne s1, s2, loop_v1

check_flag1:
  beq s4, s3, after_flag1

after_flag1:
  la t0, flags
  li t1, 1
  sb t1, 0(t0)

End:
  li a0, 0
  li a7, 93
  ecall
