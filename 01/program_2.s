.section .data
v1: .byte      2, 6, -3, 11, 9, 18, -13, 16, 5, 1
v2: .byte      4, 2, 3, 9, 9, 7, 16, 4, 7
v3: .space     10

flags: .byte    0, 0, 0

.section .text
.globl _start
_start:
Main:
  # Next v address is the upperbound for the previous
  # one. Saving v3 twice, one for boundaries and one 
  # for counting.
  la s1, v1
  la s2, v2
  la s3, v3
  mv s4, s3

  # Using s5 to save the status of the flags 2 and 3.
  # The value 0b100 means 'uninitialized'.
  li s5, 0b100
  # s6 for v3[i-1]

  # This value is gonna be used for comparison
  # against s5 to check its state.
  li t1, 0b100

# First loop over v1
loop_v1:
  lb a0, 0(s1)
  mv t0, s2

# For each element v1[i], check
# iteratively if v2 has matching ones.
loop_v2:
  lb a1, 0(t0)
  # if found, go to insert_v3,
  # this is gonna exit early.
  beq a1, a0, insert_v3

  # if not found, go to next element
  # of v2
  addi t0, t0, 1
  bne t0, s3, loop_v2
  j no_insert_v3

# This should insert the new element (saved in a0)
# into the next position of v3 (whose address is in s4)
insert_v3:
  # This checks if s5 is 0b000 which
  # means that all flags are nil, thus
  # we can skip all checks.
  beq s5, x0, after_insert_v3
  
  # If not initialized, initialize to 
  # both flags being true.
  blt s5, t1, insert_v3_states
  li s5, 0b011
  j after_insert_v3

insert_v3_states:
  # Branch based on case
  bgt a0, s6, insert_v3_gt
  blt a0, s6, insert_v3_lt
  li s5, 0b000

# In order not to have both
# conditions be valid at the
# same time, we use a andi 
# instruction. This makes it 
# possible only for s5 to be 0b001 
# if ALL elements are increasing,
# and conversely 0b010 if ALL 
# elements are decreasing.

# This is when v3[i] > v3[i-1]
# i.e. increasing
insert_v3_gt:
  andi s5, s5, 0b001
  j after_insert_v3

# This is when v3[i] < v3[i-1]
# i.e. decreasing
insert_v3_lt:
  andi s5, s5, 0b010

# Insert in v3 and increase
# address value by 1. Store 
# current v3[i] into s6 for 
# the next cycle.
after_insert_v3:
  sb a0, 0(s4)
  addi s4, s4, 1
  mv s6, a0

# This just goes to the next loop_v1
# cycle.
no_insert_v3:
  addi s1, s1, 1
  bne s1, s2, loop_v1

# For flag1, this must be true
# if the current address for next el
# for v3 is exactly the start of v3
check_flag1:
  li t1, 1
  la t0, flags
  bne s4, s3, check_flag2
  sb t1, 0(t0)

# For these two flags' logic, look 
# at the comment above.
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
