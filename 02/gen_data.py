#!/usr/bin/env python3
"""Regenerate the data section of program_1.s in place.

Fills `i` and `w` with 30 random single-precision floats each, uniformly
distributed in [0, 1). `b` and `y` are left untouched.

It also computes the `y` the program will produce (dot(i, w) + b, then the
"activation" rule: y = 1/acc unless acc is zero or has exponent 0x7F) and
prints it to stdout.

Usage: python3 gen_data.py
"""
import math
import random
import struct
from pathlib import Path

SRC = Path(__file__).with_name("program_1.s")
N = 30
F32_MAX = 3.4028234663852886e38


def rand_f32() -> float:
    """A random float32 uniformly distributed in [0, 1)."""
    return struct.unpack("<f", struct.pack("<f", random.random()))[0]


def to_f32(x: float) -> float:
    """Round a double to the nearest float32, saturating to +/-inf."""
    if math.isnan(x):
        return x
    if x > F32_MAX:
        return math.inf
    if x < -F32_MAX:
        return -math.inf
    return struct.unpack("<f", struct.pack("<f", x))[0]


def parse_b(line: str) -> float:
    """The float held by the `b` line (.word bits or .float value)."""
    rest = line.split(":", 1)[1].strip()
    if rest.startswith(".word"):
        bits = int(rest.split(None, 1)[1], 0)
        return struct.unpack("<f", struct.pack("<I", bits & 0xFFFFFFFF))[0]
    return float(rest.split(None, 1)[1])


def fmt(values) -> str:
    # 9 significant digits round-trips a float32 exactly.
    return ", ".join(format(v, ".9g") for v in values)


def compute_y(i, w, b: float) -> float:
    """The value the assembly stores in `y`.

    acc = sum(i[k]*w[k]) (fmadd.s), then acc += b (fadd.s); y = 0 when acc
    is zero or 1 <= |acc| < 2 (exponent 0x7F), else y = 1/acc (fdiv.s).
    """
    acc = 0.0
    for a, c in zip(i, w):
        acc = to_f32(acc + a * c)  # fused multiply-add
    acc = to_f32(acc + b)

    if acc == 0.0:
        return 0.0
    exponent = (struct.unpack("<I", struct.pack("<f", acc))[0] >> 23) & 0xFF
    if exponent == 0x7F:
        return 0.0
    return to_f32(1.0 / acc)


def main() -> None:
    lines = SRC.read_text().splitlines()
    i = [rand_f32() for _ in range(N)]
    w = [rand_f32() for _ in range(N)]

    out = []
    for line in lines:
        key = line.split(":", 1)[0].strip()
        if key == "i":
            out.append(f"\ti: .float {fmt(i)}")
        elif key == "w":
            out.append(f"\tw: .float {fmt(w)}")
        else:
            out.append(line)
    SRC.write_text("\n".join(out) + "\n")

    b_line = next(l for l in lines if l.split(":", 1)[0].strip() == "b")
    y = compute_y(i, w, parse_b(b_line))
    print(f"updated {SRC}")
    print(f"y = {y!r}  ({format(y, '.9g')})")


if __name__ == "__main__":
    main()
