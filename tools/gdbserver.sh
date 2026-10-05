#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
#
# Open an ELF in gdb-multiarch, with the program running under QEMU.
#
# QEMU user-mode does not implement ptrace, so `gdb` cannot launch or step the
# inferior itself ("ptrace: Function not implemented").  Instead QEMU hosts the
# program and exposes its gdbstub on a TCP port; gdb attaches with
# `target remote`.  Breakpoints, stepping and registers all work this way.
#
#   tools/gdbserver.sh build/riscv/01/hello/main.elf
#
set -eu

elf="${1:?usage: gdbserver.sh <elf>}"
port="${GDB_PORT:-1234}"

case "$(readelf -h "$elf" | awk '/Class:/ { print $2 }')" in
  ELF32) qemu=qemu-riscv32 ;;
  ELF64) qemu=qemu-riscv64 ;;
  *) echo "error: cannot tell the ELF class of $elf" >&2; exit 1 ;;
esac

"$qemu" -g "$port" "$elf" &
qemu_pid=$!
trap 'kill "$qemu_pid" 2>/dev/null || true' EXIT INT TERM

printf '\nAttached to QEMU (no ptrace).  Set breakpoints, then use `continue`,\n'
printf 'not `run` -- the inferior is already started and paused at the entry point.\n\n'

gdb-multiarch -ex "set confirm off" -ex "target remote :$port" "$elf"
