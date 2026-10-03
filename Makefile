# SPDX-License-Identifier: GPL-2.0-only
#
# Compile every *.s to an ELF, then run it.
#
#   make image                 build the reusable riscv64 image (once)
#   make build                 build/{gem5,riscv}/<lab>/<program>/main.elf
#   make run                   run every ELF
#   make debug PROG=01/hello   open an ELF in gdb-multiarch
#   make clean
#
# CUSTOM_PATH=1 (default): the ASR gem5 container compiles and simulates.
# CUSTOM_PATH=0:           a plain riscv64 image (make image); the native gcc
#                          compiles and the ELF runs natively.
# `make debug` always uses the riscv64 image.

SHELL := /bin/sh
.SHELLFLAGS := -eu -c

CUSTOM_PATH ?= 1
IMAGE       ?= ghcr.io/pasc4le-labs/ase_riscv_gem5_sim:v1.0.0-a.1
RISCV_IMAGE ?= ase-riscv:24.04
PLATFORM    ?= linux/riscv64
DOCKER      ?= docker
TIMEOUT     ?= 180
PROG        ?=                   # restrict build/run/debug to one program

# Separate trees, so a gem5 (rv32) build is never run natively (rv64).
ifeq ($(CUSTOM_PATH),1)
  BUILD := build/gem5
else
  BUILD := build/riscv
endif

SOURCES := $(sort $(wildcard */*.s))
ifneq ($(PROG),)
  SOURCES := $(PROG).s
endif
ELFS         := $(patsubst %.s,$(BUILD)/%/main.elf,$(SOURCES))
RUNS         := $(patsubst %.s,$(BUILD)/%/ran,$(SOURCES))
DEBUG_PROG   ?= $(if $(PROG),$(PROG),$(firstword $(patsubst %.s,%,$(SOURCES))))

MOUNT  := -v "$(CURDIR)":/work -w /work
GEM5   := $(DOCKER) run --rm --network none $(MOUNT) \
            -e ASE_STUDIO_HOST_ROOT=/app --entrypoint python3 $(IMAGE)
RISCV  := $(DOCKER) run --rm --platform $(PLATFORM) $(MOUNT) $(RISCV_IMAGE)
GDB    := $(DOCKER) run -it --rm --platform $(PLATFORM) $(MOUNT) $(RISCV_IMAGE)

ifeq ($(CUSTOM_PATH),1)

$(BUILD)/%/main.elf: %.s
	@mkdir -p $(dir $@)
	@echo "== build $* =="
	$(GEM5) /work/tools/incontainer.py build --source "$*.s" --out "$(dir $@)" \
	    --timeout "$(TIMEOUT)"

$(BUILD)/%/ran: $(BUILD)/%/main.elf
	@echo "== run $* =="
	$(GEM5) /work/tools/incontainer.py run --source "$*.s" \
	    --elf "/work/$(dir $@)main.elf" --out "$(dir $@)" --timeout "$(TIMEOUT)"
	@touch $@

else

$(BUILD)/%/main.elf: %.s
	@mkdir -p $(dir $@)
	@echo "== build $* =="
	$(RISCV) gcc -static -no-pie -nostdlib -o "$(dir $@)main.elf" "$*.s"

$(BUILD)/%/ran: $(BUILD)/%/main.elf
	@echo "== run $* =="
	$(RISCV) "./$(dir $@)main.elf"
	@touch $@

endif

all: build
build: $(ELFS)
run: $(RUNS)
debug: $(BUILD)/$(DEBUG_PROG)/main.elf
	@echo "== gdb $< =="
	$(GDB) gdb-multiarch "$(BUILD)/$(DEBUG_PROG)/main.elf"

# --provenance/--sbom off: a bare single-platform image, so `docker run
# --platform` does not go looking for an attestation manifest.
image:
	$(DOCKER) build --platform $(PLATFORM) --provenance=false --sbom=false \
	    -t "$(RISCV_IMAGE)" -f Dockerfile.riscv .

clean:
	@rm -rf build
	@echo "removed build/"

.PHONY: all build run debug image clean help

help:
	@sed -n '3,14p' Makefile | sed 's/^# \{0,1\}//'
	@echo
	@echo "CUSTOM_PATH=$(CUSTOM_PATH)  IMAGE=$(IMAGE)  RISCV_IMAGE=$(RISCV_IMAGE)"
	@echo "Programs: $(if $(SOURCES),$(SOURCES),(none))"
