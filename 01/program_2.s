.section .data
v1: .byte      2, 6, -3, 11, 9, 18, -13, 16, 5, 1
v2: .byte      4, 2, 3, 9, 9, 7, 16, 4, 7
v3: .space     10

flags: .byte    0, 0, 0

.section .text
.globl _start
_start:
Main:
  la s1, v1
  la s2, v2
  la s3, v3
  mv s4, s3

  li s5, 0b100
  # s6 for v3[i-1]
  li t1, 0b100

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
  beq s5, x0, after_insert_v3
  blt s5, t1, 3
  li s5, 0b011
  j after_insert_v3

  bgt a0, s6, insert_v3_gt
  blt a0, s6, insert_v3_lt
  li s5, 0b000

insert_v3_gt:
  andi s5, s5, 0b001
  j after_insert_v3

insert_v3_lt:
  andi s5, s5, 0b010

after_insert_v3:
  sw a0, 0(s4)
  addi s4, s4, 1
  mv s6, a0

no_insert_v3:
  addi s1, s1, 1
  bne s1, s2, loop_v1

check_flag1:
  bne s4, s3, check_flag2
  la t0, flags
  li t1, 1
  sb t1, 0(t0)

check_flag2:
  li t2, 0b001
  bne s5, t2, check_flag3
  sb t1, 1(t0)

check_flag3:
  li t2, 0b010
  bne s5, t2, End
  sb t1, 2(t0)

End:
  li a0, 0
  li a7, 93
  ecall
