# tools/smold/Makefile
#
# Builds smold M1 (fallback walker): RV64 asm core + thin C CLI.
#
# Builds (host = whatever uname -m says; cross = riscv64-linux-gnu-):
#   build/libsmold-core.a    Static library (asm only).
#   build/smold              CLI binary, links the static library.
#   build/test_core          Test runner.
#   build/test_layout        Compile-time struct layout assertions.
#
# Targets:
#   make            Build everything.
#   make test       Build and run the test suite (via qemu-user if cross).
#   make clean      Remove build artifacts.
#   make riscv      Force the RISC-V cross-build path explicitly.
#
# Auto-detect:
#   On a riscv64 host (`uname -m` is riscv64) we use unprefixed tools.
#   On any other host we use the riscv64-linux-gnu- cross prefix and
#   run tests under qemu-riscv64.

UNAME_M := $(shell uname -m)
ifeq ($(UNAME_M),riscv64)
  CROSS    ?=
  RUN      ?=
else
  CROSS    ?= riscv64-linux-gnu-
  RUN      ?= qemu-riscv64 -L /usr/riscv64-linux-gnu
endif

CC      = $(CROSS)gcc
AR      = $(CROSS)ar

MARCH   = rv64gc_zba_zbb_zbs
MABI    = lp64d

# Common flags. -ffunction-sections + -fdata-sections + --gc-sections at
# link time give us the per-atom dropping the smold design relies on.
CFLAGS  = -std=c11 -O2 -Wall -Wextra -Wpedantic \
          -fno-strict-aliasing -g \
          -march=$(MARCH) -mabi=$(MABI) \
          -ffunction-sections -fdata-sections \
          -Iinclude -Isrc

# Assembly flags: we use cpp via gcc -x assembler-with-cpp so #include works.
ASFLAGS = -march=$(MARCH) -mabi=$(MABI) \
          -Iinclude -Isrc \
          -x assembler-with-cpp

# Link-time gc-sections so unused atoms are dropped.
LDFLAGS = -Wl,--gc-sections

BUILD   = build

CORE_ASM_SRCS = src/core.S
CORE_OBJS     = $(BUILD)/core.o
CORE_LIB      = $(BUILD)/libsmold-core.a

CLI_SRCS      = cli/smold-cli.c
CLI_BIN       = $(BUILD)/smold

TEST_CORE_SRC = tests/test_core.c
TEST_CORE_BIN = $(BUILD)/test_core

TEST_LAY_SRC  = tests/test_layout.c
TEST_LAY_BIN  = $(BUILD)/test_layout

.PHONY: all test clean riscv

all: $(CORE_LIB) $(CLI_BIN) $(TEST_CORE_BIN) $(TEST_LAY_BIN)

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/core.o: src/core.S src/smold-internal.h src/asm-macros.h | $(BUILD)
	$(CC) $(ASFLAGS) -c src/core.S -o $@

$(CORE_LIB): $(CORE_OBJS)
	$(AR) rcs $@ $(CORE_OBJS)

$(CLI_BIN): cli/smold-cli.c $(CORE_LIB)
	$(CC) $(CFLAGS) cli/smold-cli.c $(CORE_LIB) -o $@ $(LDFLAGS)

$(TEST_CORE_BIN): tests/test_core.c $(CORE_LIB)
	$(CC) $(CFLAGS) tests/test_core.c $(CORE_LIB) -o $@ $(LDFLAGS)

$(TEST_LAY_BIN): tests/test_layout.c
	$(CC) $(CFLAGS) tests/test_layout.c -o $@ $(LDFLAGS)

test: $(TEST_CORE_BIN) $(TEST_LAY_BIN)
	$(RUN) ./$(TEST_LAY_BIN)
	$(RUN) ./$(TEST_CORE_BIN)

# Explicit cross-build alias; on an x86 host `make` already cross-builds,
# this exists so `make -C tools/smold riscv` from the ENO top-level works
# consistently with the wavelet/Makefile convention.
riscv: all
	@echo "Built smold for RISC-V ($(MARCH), $(MABI))."

clean:
	rm -rf $(BUILD)
