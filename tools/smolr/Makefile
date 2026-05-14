# tools/smolr/Makefile
#
# Phase 0-1: toolchain probe + relocation survey.
#
# Builds:
#   build/toolchain-probe.txt           Local toolchain capability report
#   build/survey/<test>-<tier>-<flags>.o,.elf  Survey corpus objects + ELFs
#   build/survey/<test>-<tier>-<flags>.reloc   readelf -rW output per artifact
#   build/survey/<test>-<tier>-<flags>.disasm  objdump -dr output per artifact
#   build/baseline-sizes.txt            Normal-ld + UPX size measurements
#   docs/riscv-relocation-survey.md     Phase 1 deliverable
#
# Targets:
#   make           Build everything (probe, survey, report, baseline).
#   make probe     Run the toolchain probe only.
#   make survey    Build the survey corpus only.
#   make report    Regenerate docs/riscv-relocation-survey.md.
#   make baseline  Measure normal-ld and (optional) UPX sizes.
#   make clean     Remove build artifacts.
#
# Auto-detect:
#   On a riscv64 host (`uname -m` is riscv64) we use unprefixed tools.
#   On any other host we use the riscv64-linux-gnu- cross prefix.
#   Override with SMOLR_CROSS=... on the command line.

UNAME_M := $(shell uname -m)
ifeq ($(UNAME_M),riscv64)
  SMOLR_CROSS ?=
else
  SMOLR_CROSS ?= riscv64-linux-gnu-
endif

export SMOLR_CROSS

GCC      = $(SMOLR_CROSS)gcc
AS       = $(SMOLR_CROSS)as
LD       = $(SMOLR_CROSS)ld
OBJDUMP  = $(SMOLR_CROSS)objdump
READELF  = $(SMOLR_CROSS)readelf
STRIP    = $(SMOLR_CROSS)strip
NM       = $(SMOLR_CROSS)nm

BUILD     = build
SURVEY    = $(BUILD)/survey

# Test sources (one .c file per survey test).
TESTS = 01-call-puts \
        02-call-multi \
        03-call-libm \
        04-call-indirect \
        05-syscall-only

# ISA tiers exercised by the survey.
# rva23u64 may not be accepted by older toolchains; the survey scripts
# fall back to a manually expanded ISA string when that happens.
TIERS = rv64gc \
        rv64gcv_zba_zbb_zbs \
        rva23u64

# Relocation/relaxation flag combinations exercised by the survey.
# Naming convention: <relax>-<plt>
#   relax     -mrelax
#   norelax   -mno-relax
#   plt       (default, with PLT)
#   noplt     -fno-plt
FLAGCOMBOS = relax-plt norelax-plt relax-noplt norelax-noplt

# Common compiler flags for the survey. Matches ENO conventions but adds
# -nostartfiles because the test programs supply their own _start.
SURVEY_CFLAGS_COMMON = -std=c11 -Wall -Wextra -Wpedantic \
                      -fno-strict-aliasing \
                      -Os \
                      -fno-stack-protector \
                      -fno-unwind-tables \
                      -fno-asynchronous-unwind-tables \
                      -ffunction-sections -fdata-sections \
                      -nostartfiles

.PHONY: all probe survey report baseline clean

all: probe survey report baseline

# -- Phase 0: probe -----------------------------------------------------------

probe: $(BUILD)/toolchain-probe.txt

$(BUILD)/toolchain-probe.txt: tools/probe-toolchain.sh | $(BUILD)
	@tools/probe-toolchain.sh > $@ 2>&1 || \
	    (echo "probe-toolchain.sh failed; see $@"; cat $@; exit 1)
	@echo "Wrote $@"

$(BUILD):
	mkdir -p $(BUILD)

$(SURVEY): | $(BUILD)
	mkdir -p $(SURVEY)

# -- Phase 1: survey ----------------------------------------------------------
#
# We don't try to generate the cartesian product as explicit Make targets,
# because the rules would be huge and most of the value is in the inspection
# step. Instead we delegate to a single driver script that knows how to
# build, inspect, and tag every (test, tier, flagcombo) tuple.

survey: $(SURVEY)/.survey-stamp

$(SURVEY)/.survey-stamp: $(addprefix survey/tests/,$(addsuffix .c,$(TESTS))) \
                        survey/scripts/build-survey.sh \
                        | $(SURVEY)
	@TESTS="$(TESTS)" TIERS="$(TIERS)" FLAGCOMBOS="$(FLAGCOMBOS)" \
	 CFLAGS_COMMON="$(SURVEY_CFLAGS_COMMON)" \
	 BUILD="$(SURVEY)" GCC="$(GCC)" \
	 survey/scripts/build-survey.sh
	@touch $@

# -- Phase 1: inspect + report ------------------------------------------------

report: docs/riscv-relocation-survey.md

docs/riscv-relocation-survey.md: $(SURVEY)/.survey-stamp \
                                 survey/scripts/inspect-all.sh \
                                 survey/scripts/build-report.py
	@TESTS="$(TESTS)" TIERS="$(TIERS)" FLAGCOMBOS="$(FLAGCOMBOS)" \
	 BUILD="$(SURVEY)" READELF="$(READELF)" OBJDUMP="$(OBJDUMP)" NM="$(NM)" \
	 survey/scripts/inspect-all.sh
	@TESTS="$(TESTS)" TIERS="$(TIERS)" FLAGCOMBOS="$(FLAGCOMBOS)" \
	 BUILD="$(SURVEY)" \
	 python3 survey/scripts/build-report.py > $@
	@echo "Wrote $@"

# -- baseline ----------------------------------------------------------------

baseline: $(BUILD)/baseline-sizes.txt

$(BUILD)/baseline-sizes.txt: $(SURVEY)/.survey-stamp tools/size-baseline.sh
	@BUILD="$(BUILD)" SURVEY="$(SURVEY)" \
	 TESTS="$(TESTS)" TIERS="$(TIERS)" \
	 GCC="$(GCC)" STRIP="$(STRIP)" \
	 tools/size-baseline.sh > $@
	@echo "Wrote $@"

# -- clean -------------------------------------------------------------------

clean:
	rm -rf $(BUILD)
	rm -f docs/riscv-relocation-survey.md
