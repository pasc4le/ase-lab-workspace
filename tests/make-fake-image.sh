#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
#
# Assemble a directory that looks like the image's /app, so the container's
# script can be run on the host (see tests/shim/docker).  Only what the compile
# path needs is linked in; gem5 is replaced by a stub that explains itself.
#
#   bash tests/make-fake-image.sh
#   make build DOCKER=tests/shim/docker
#
set -euo pipefail

ENV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ENV_ROOT}/.." && pwd)"
IMAGE="${ASE_FAKE_IMAGE:-${ENV_ROOT}/build/fake-image}"

# Find a RISC-V toolchain: $ASE_TOOLCHAIN, one on PATH, or a downloaded xPack
# tree left in the cache by whoever set this machine up.
find_toolchain() {
    if [[ -n "${ASE_TOOLCHAIN:-}" ]]; then
        echo "${ASE_TOOLCHAIN}"; return
    fi
    local prefix
    for prefix in riscv-none-elf riscv64-unknown-elf; do
        if command -v "${prefix}-gcc" >/dev/null 2>&1; then
            echo "$(dirname "$(command -v "${prefix}-gcc")")"; return
        fi
    done
    local candidate
    for candidate in \
        /opt/data/cache/tc2/xpack-riscv-none-elf-gcc-*/bin \
        "${HOME}"/.cache/ase-toolchain/*/bin \
        /opt/*/bin; do
        if compgen -G "${candidate}/riscv-none-elf-gcc" >/dev/null 2>&1; then
            echo "${candidate}"; return
        fi
    done
    echo "" 
}

TOOLCHAIN="$(find_toolchain)"
if [[ -z "${TOOLCHAIN}" ]]; then
    echo "No riscv-none-elf-gcc found. Set ASE_TOOLCHAIN=/path/to/toolchain/bin." >&2
    exit 1
fi
# The image installs the whole toolchain root at tools/riscv-toolchain (with
# bin/ inside) and setup_default appends /bin itself, so keep the root here.
TOOLCHAIN="$(cd "${TOOLCHAIN}" && pwd)"
if [[ "$(basename "${TOOLCHAIN}")" == "bin" ]]; then
    TOOLCHAIN="$(cd "${TOOLCHAIN}/.." && pwd)"
fi

echo "image root : ${IMAGE}"
echo "toolchain  : ${TOOLCHAIN}"

rm -rf "${IMAGE}"
mkdir -p "${IMAGE}/programs" "${IMAGE}/results" "${IMAGE}/tools/gem5/build/RISCV"

ln -s "${REPO_ROOT}/ase_studio"                 "${IMAGE}/ase_studio"
ln -s "${REPO_ROOT}/setup_default"              "${IMAGE}/setup_default"
ln -s "${REPO_ROOT}/ase_studio_branches.json"    "${IMAGE}/ase_studio_branches.json"
ln -s "${REPO_ROOT}/gem5"                       "${IMAGE}/gem5"
ln -s "${REPO_ROOT}/programs/demo.mk"           "${IMAGE}/programs/demo.mk"
ln -s "${TOOLCHAIN}"                            "${IMAGE}/tools/riscv-toolchain"

cat > "${IMAGE}/tools/gem5/build/RISCV/gem5.opt" <<'STUB'
#!/bin/sh
echo "gem5 is not available on this host (the real one lives in the container)." >&2
echo "The compile path works; run 'make run' where Docker is available." >&2
exit 127
STUB
chmod +x "${IMAGE}/tools/gem5/build/RISCV/gem5.opt"

echo "ready: make build DOCKER=tests/shim/docker"
