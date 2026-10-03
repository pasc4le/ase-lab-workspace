# SPDX-License-Identifier: GPL-2.0-only
#
# Lab environment for the ASE RISC-V / gem5 simulator (PoliTo).
#
#   make            compile and run every program in every lab
#   make build      compile only               (build/<lab>/<program>/main.elf)
#   make run        compile, simulate, report  (build/<lab>/<program>/report.md)
#   make check      compare the results with the <lab>/<program>.expected files
#   make 01         do all of the above for lab 01, then write 01.zip
#   make zips       write one submission archive per lab
#   make labs       list the discovered labs and programs
#   make clean      remove build/ and the archives
#
# Everything the compiler and gem5 do happens inside the container image, so the
# host only needs Docker (and uv for the report tooling).  Programs are
# discovered, never listed: drop a .s file into <lab>/ and every target picks it
# up.  The CPU characteristics come from cpu.toml (see that file).
#
# The image is the one built from this repository: `make image` builds and tags
# it locally if it is not in the Docker cache yet.

SHELL := /bin/sh
.SHELLFLAGS := -eu -c

# ---------------------------------------------------------------- settings ---
IMAGE   ?= ghcr.io/pasc4le-labs/ase_riscv_gem5_sim:v1.0.0-a.1
DOCKER  ?= docker
UV      ?= uv
# Wall-clock cap per program, enforced *inside* the container (gem5 has no
# timeout of its own, so a program that never reaches its `End:` label would run
# forever).  Keeping it there means the host needs no GNU `timeout`, which does
# not exist on macOS.
TIMEOUT ?= 180
# Lab-local CPU file, merged over cpu.toml (see `make help`).
CPU     ?= cpu.toml
# Restrict every target to one lab, e.g. `make run LAB=02`.
LAB     ?=

BUILD   := build

# ------------------------------------------------------------------- layout ---
LABS    := $(sort $(notdir $(patsubst %/,%,$(wildcard [0-9]*/))))
ifneq ($(LAB),)
  LAB_DIRS := $(LAB)
else
  LAB_DIRS := $(LABS)
endif
SOURCES := $(sort $(wildcard $(addsuffix /*.s,$(LAB_DIRS))))
ELFS    := $(patsubst %.s,$(BUILD)/%/main.elf,$(SOURCES))
RESULTS := $(patsubst %.s,$(BUILD)/%/ok,$(SOURCES))
REPORTS := $(patsubst %.s,$(BUILD)/%/report.md,$(SOURCES))

# The container is used as a plain program runner: no server, no network, and
# the project tree lives in the container's own layer.  Only the artifacts and
# the JSON dump come back out, chowned to the user running make.
RUNNER  := $(DOCKER) run --rm --network none \
             -v "$(CURDIR)":/work -w /work \
             -e ASE_STUDIO_HOST_ROOT=/app \
             -e ASE_OUT_OWNER="$(shell id -u):$(shell id -g)" \
             --entrypoint python3 $(IMAGE)
PY      := $(UV) run --quiet --project "$(CURDIR)" python tools/aselab.py

# Printed when a container call fails; the exit status is still the container's,
# so `set -e` behaviour keeps working.  Plain POSIX: the recipe shell may be
# zsh (where `status` is read-only) as well as bash or dash.
CONTAINER_HINT = rc=$$?; \
	  if [ $$rc -eq 124 ]; then \
	    echo "error: the program ran longer than TIMEOUT=$(TIMEOUT)s." >&2; \
	    echo "       A program that never reaches its 'End:' label runs forever." >&2; \
	  elif [ $$rc -eq 125 ] || [ $$rc -eq 126 ] || [ $$rc -eq 127 ]; then \
	    echo "error: could not run '$(DOCKER)' or could not find the image '$(IMAGE)'" >&2; \
	    echo "       build it locally with: make image" >&2; \
	  fi; \
	  echo "       See build/$*/build.log (build) or simulate.log (simulation)." >&2

.DEFAULT_GOAL := all
.PHONY: all build run report check update-expected clean distclean help labs zips \
        image _lab _zip $(LABS) $(addsuffix .zip,$(LABS))

# ------------------------------------------------------------------ targets ---
all: build run

build: $(ELFS)

run report: $(REPORTS)

# Compile one program.
$(BUILD)/%/main.elf: %.s
	@mkdir -p $(dir $@)
	@echo "== build $* =="
	@$(RUNNER) /work/tools/incontainer.py build --source "$*.s" --out "$(dir $@)" \
	    --timeout "$(TIMEOUT)" || { $(CONTAINER_HINT); exit 1; }

# Compile and simulate one program, keeping every fact gem5 knows about it.
$(BUILD)/%/ok: %.s $(CPU)
	@mkdir -p $(dir $@)
	@echo "== run $* =="
	@$(PY) config --toml "$(CPU)"$(if $(wildcard $(firstword $(subst /, ,$*))/cpu.toml), --lab-toml "$(firstword $(subst /, ,$*))/cpu.toml",) --out "$(dir $@)cpu.json"
	@$(RUNNER) /work/tools/incontainer.py run --source "$*.s" --stem "$*" \
	    --out "$(dir $@)" --config "$(dir $@)cpu.json" --timeout "$(TIMEOUT)" \
	  || { $(CONTAINER_HINT); exit 1; }
	@touch $@

# Render the Markdown report from the JSON dump (no container needed).
$(BUILD)/%/report.md: $(BUILD)/%/ok
	@$(PY) report --build "$(BUILD)/$*" --source "$*.s" --out "$@" --image "$(IMAGE)"

check: $(REPORTS)
	@$(PY) check --sources $(SOURCES) --build "$(BUILD)"

update-expected: $(REPORTS)
	@$(PY) update-expected --sources $(SOURCES) --build "$(BUILD)"

# One lab: compile, run and archive it.
$(LABS):
	@$(MAKE) --no-print-directory _lab LAB="$@"

_lab: build run
	@$(MAKE) --no-print-directory _zip LAB="$(LAB)"
	@echo "run 'make check LAB=$(LAB)' to verify the results against <lab>/*.expected"

zips: $(addsuffix .zip,$(LABS))

$(addsuffix .zip,$(LABS)):
	@$(MAKE) --no-print-directory _zip LAB="$(patsubst %.zip,%,$@)"

_zip: run
	@$(PY) zip --lab "$(LAB)" --out "$(LAB).zip" --build "$(BUILD)" --cpu "$(CPU)"

labs:
	@$(PY) labs

image:
	@echo "building $(IMAGE) from $(CURDIR)/.. (the repository root)"
	cd .. && $(DOCKER) build -t "$(IMAGE)" .

clean:
	@rm -rf "$(BUILD)" *.zip
	@echo "removed $(BUILD)/ and the archives"

distclean: clean
	@rm -rf .venv
	@echo "removed .venv/"

help:
	@sed -n '3,20p' Makefile | sed 's/^# \{0,1\}//' || true
	@echo
	@echo "Variables: IMAGE=$(IMAGE)  LAB=$(LAB)  CPU=$(CPU)  TIMEOUT=$(TIMEOUT)"
	@echo "Labs: $(if $(LABS),$(LABS),(none yet)")
