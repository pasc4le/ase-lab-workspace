# SPDX-License-Identifier: GPL-2.0-only
#
# Compile every *.s to an ELF, then run it.
#
#   make image                 build the reusable riscv64 image (once)
#   make build                 build/{gem5,riscv}/<lab>/<program>/main.elf
#   make run                   run every ELF (gem5: keeps the pipeline trace)
#   make report                render <build>/<lab>/<program>/report.md
#   make zip LAB=01            archive one lab's submission as 01.zip
#   make debug PROG=01/hello   open an ELF in gdb-multiarch (DEBUGGER=pwndbg)
#   make clean
#
# CUSTOM_PATCH=1 (default): the ASR gem5 container compiles and simulates.
# CUSTOM_PATCH=0:           a plain riscv64 image (make image); the native gcc
#                          compiles and the ELF runs natively.
# `make debug` always uses the riscv64 image.  Values can also go in .env.

SHELL := /bin/sh
.SHELLFLAGS := -eu -c

# Local overrides (`CUSTOM_PATCH=0`, `TIMEOUT=60`, …).  Missing file is fine.
-include .env

CUSTOM_PATCH ?= 1
IMAGE       ?= ghcr.io/pasc4le-labs/ase_riscv_gem5_sim:v1.0.0-a.1
RISCV_IMAGE ?= ase-riscv:24.04
PLATFORM    ?= linux/riscv64
DOCKER      ?= docker
TIMEOUT     ?= 180
PROG        ?=                   # restrict build/run/debug to one program

# CPU characteristics, straight into the container (`--config`).  A lab can use
# its own with `make run CPU=02/cpu.json`.
CPU         ?= cpu.json

# `make debug` front end: gdb-multiarch, or pwndbg.  (No trailing comment here:
# make would keep the padding as part of the value.)
DEBUGGER    ?= gdb

# Separate trees, so a gem5 (rv32) build is never run natively (rv64).
ifeq ($(CUSTOM_PATCH),1)
  BUILD := build/gem5
else
  BUILD := build/riscv
endif

SOURCES := $(sort $(wildcard */*.s))
ifneq ($(PROG),)
  # Accept both `01/hello` and `01/hello.s`.
  SOURCES := $(patsubst %.s,%,$(PROG)).s
endif
ELFS         := $(patsubst %.s,$(BUILD)/%/main.elf,$(SOURCES))
RUNS         := $(patsubst %.s,$(BUILD)/%/ran,$(SOURCES))
REPORTS      := $(patsubst %.s,$(BUILD)/%/report.md,$(SOURCES))
DEBUG_PROG   ?= $(firstword $(patsubst %.s,%,$(SOURCES)))

# `make zip LAB=01`; defaults to the lab of the first program.
LAB          ?= $(firstword $(subst /, ,$(firstword $(SOURCES))))
LAB_REPORTS  := $(patsubst %.s,$(BUILD)/%/report.md,$(sort $(wildcard $(LAB)/*.s)))

MOUNT  := -v "$(CURDIR)":/work -w /work
GEM5   := $(DOCKER) run --rm --network none $(MOUNT) \
            -e ASE_STUDIO_HOST_ROOT=/app \
            -e ASE_OUT_OWNER="$(shell id -u):$(shell id -g)" \
            --entrypoint python3 $(IMAGE)
RISCV  := $(DOCKER) run --rm --platform $(PLATFORM) $(MOUNT) $(RISCV_IMAGE)
GDB    := $(DOCKER) run -it --rm --platform $(PLATFORM) $(MOUNT) \
            -e DEBUGGER=$(DEBUGGER) $(RISCV_IMAGE)

ifeq ($(CUSTOM_PATCH),1)

$(BUILD)/%/main.elf: %.s $(CPU)
	@mkdir -p $(dir $@)
	@echo "== build $* =="
	$(GEM5) /work/tools/incontainer.py build --source "$*.s" --out "$(dir $@)" \
	    --config "/work/$(CPU)" --timeout "$(TIMEOUT)"

$(BUILD)/%/ran: $(BUILD)/%/main.elf
	@echo "== run $* =="
	$(GEM5) /work/tools/incontainer.py run --source "$*.s" \
	    --elf "/work/$(dir $@)main.elf" --out "$(dir $@)" --config "/work/$(CPU)" \
	    --report --timeout "$(TIMEOUT)"
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
report: $(REPORTS)

# Rendering needs only the JSON dumps, but they exist only after a gem5 run.
$(BUILD)/%/report.md: $(BUILD)/%/ran
	@echo "== report $* =="
	$(GEM5) /work/tools/artifacts.py report --build "/work/$(dir $@)" --source "$*.s" \
	    --out "/work/$@" --image "$(IMAGE)"

zip: $(LAB_REPORTS)
	@echo "== zip $(LAB) =="
	$(GEM5) /work/tools/artifacts.py zip --lab "$(LAB)" --build "/work/$(BUILD)" \
	    --cpu "/work/$(CPU)" --out "/work/$(LAB).zip"

debug: $(BUILD)/$(DEBUG_PROG)/main.elf
	@echo "== gdb $< =="
	$(GDB) /work/tools/gdbserver.sh "$(BUILD)/$(DEBUG_PROG)/main.elf"

# --provenance/--sbom off: a bare single-platform image, so `docker run
# --platform` does not go looking for an attestation manifest.
image:
	$(DOCKER) build --platform $(PLATFORM) --provenance=false --sbom=false \
	    -t "$(RISCV_IMAGE)" -f Dockerfile.riscv .

clean:
	@rm -rf build *.zip
	@echo "removed build/ and the archives"

.PHONY: all build run report zip debug image clean help

help:
	@sed -n '3,16p' Makefile | sed 's/^# \{0,1\}//'
	@echo
	@echo "CUSTOM_PATCH=$(CUSTOM_PATCH)  IMAGE=$(IMAGE)  RISCV_IMAGE=$(RISCV_IMAGE)"
	@echo "DEBUGGER=$(DEBUGGER)  CPU=$(CPU)  LAB=$(LAB)"
	@echo "Programs: $(if $(SOURCES),$(SOURCES),(none))"
