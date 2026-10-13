#!/usr/bin/env python3
"""Regenerate the data section of program_1.s in place.

Fills `i` and `w` with 30 random single-precision floats each, spanning the
full float32 range (tiny subnormal-ish magnitudes up to ~3.4e38, both signs),
and `b` with a single float.

Usage: python3 gen_data.py
"""
import math
import random
import struct
from pathlib import Path

SRC = Path(__file__).with_name("program_1.s")
N = 30


def rand_f32() -> float:
    """A random finite, non-zero float32 spanning the whole range."""
    while True:
        sign = random.choice((-1.0, 1.0))
        mant = 1.0 + random.random()          # [1, 2)
        exp = random.randint(-126, 127)       # float32 normal exponent range
        f = struct.unpack("<f", struct.pack("<f", sign * mant * 2.0 ** exp))[0]
        if math.isfinite(f) and f != 0.0:
            return f


def fmt(values) -> str:
    # 9 significant digits round-trips a float32 exactly.
    return ", ".join(format(v, ".9g") for v in values)


def main() -> None:
    lines = SRC.read_text().splitlines()
    out = []
    for line in lines:
        key = line.split(":", 1)[0].strip()
        if key == "i":
            out.append(f"\ti: .float {fmt(rand_f32() for _ in range(N))}")
        elif key == "w":
            out.append(f"\tw: .float {fmt(rand_f32() for _ in range(N))}")
        elif key == "b":
            out.append(f"\tb: .float {format(rand_f32(), '.9g')}")
        else:
            out.append(line)
    SRC.write_text("\n".join(out) + "\n")
    print(f"updated {SRC}")


if __name__ == "__main__":
    main()
