.section .data
	i: .float 0.438292146, 0.40554741, 0.515517592, 0.22091718, 0.0332678892, 0.261155486, 0.631655991, 0.237002209, 0.774878025, 0.230780542, 0.730855286, 0.227772221, 0.649443984, 0.325487018, 0.473041058, 0.794263422, 0.402260423, 0.478051931, 0.760393739, 0.860964179, 0.450923234, 0.141651824, 0.945473373, 0.60360682, 0.495533347, 0.889945805, 0.598719656, 0.425704479, 0.111415304, 0.990705311
	w: .float 0.807723641, 0.467753738, 0.238377795, 0.417637825, 0.128217489, 0.929971159, 0.0735255778, 0.0691691339, 0.862891316, 0.0493728146, 0.152222306, 0.418120921, 0.647199333, 0.749067903, 0.85222131, 0.306006074, 0.488260895, 0.592035472, 0.760163903, 0.222364426, 0.253333002, 0.816284001, 0.744083941, 0.962645888, 0.804723918, 0.296884805, 0.506050706, 0.125261545, 0.23931925, 0.534667432
	b: .word 0xab
  y: .float 0

.globl _start
_start:
Main:
  la        s1, i
  la        s2, w
  la        s3, b
  flw       f3, 0(s3)
  la        s4, y

  fcvt.s.w  f4, zero # x
  mv        t1, s2

perc_loop:
  flw       f1, 0(s1)
  flw       f2, 0(s2)

  fmadd.s   f4, f1, f2, f4

  addi      s1, s1, 4
  addi      s2, s2, 4
  bne       s1, t1, perc_loop

add_b:
  fadd.s    f4, f4, f3

act_fn:
  fclass.s  t1, f4
  andi      t1, t1, 0x18 # bit 3 and 4 identifies +0 and -0 cases

  fmv.x.w   t2, f4  # a bit convoluted, but it shifts to make code easier 
                    # and matches for exponent
  srli      t2, t2, 23
  andi      t2, t2, 0xFF
  xori      t2, t2, 0x7F

  seqz      t2, t2
  or        t1, t1, t2
  bnez      t1, End

  li        t1, 0x3f800000 # 1.0f in hex
  fmv.w.x   f1, t1
  fdiv.s    f4, f1, f4
  fsw       f4, 0(s4)

End:
  # exit() syscall. This is needed to end the simulation gracefully
  li a0, 0
  li a7, 93
  ecall
