# lib/crest/Makefile
#
# Builds:
#   build/libcrest.a         Static library for all CREST modules.
#   build/test_crest_core    Tests for the core module (WaveletSquare, CDF 5/3, stamp).
#   build/test_crest_bases   Tests for the bases module (D4, chirplet, …).
#
# Targets:
#   make           Build everything.
#   make test      Build and run all test suites.
#   make clean     Remove build artifacts.
#   make riscv     Cross-compile for RISC-V (requires riscv64-linux-gnu-gcc).

CC      ?= gcc
AR      ?= ar

CFLAGS  = -std=c11 -O2 -Wall -Wextra -Wpedantic \
          -fno-strict-aliasing -g \
          -Iinclude

LDFLAGS = -lm

BUILD   = build
SRCS    = src/crest_core.c src/crest_bases.c
OBJS    = $(BUILD)/crest_core.o $(BUILD)/crest_bases.o
LIB     = $(BUILD)/libcrest.a

TEST_CORE  = $(BUILD)/test_crest_core
TEST_BASES = $(BUILD)/test_crest_bases

.PHONY: all test clean riscv

all: $(LIB) $(TEST_CORE) $(TEST_BASES)

test: $(TEST_CORE) $(TEST_BASES)
	./$(TEST_CORE)
	./$(TEST_BASES)

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/crest_core.o: src/crest_core.c include/crest.h | $(BUILD)
	$(CC) $(CFLAGS) -c src/crest_core.c -o $@

$(BUILD)/crest_bases.o: src/crest_bases.c include/crest.h include/crest_bases.h | $(BUILD)
	$(CC) $(CFLAGS) -c src/crest_bases.c -o $@

$(LIB): $(OBJS)
	$(AR) rcs $@ $(OBJS)

$(TEST_CORE): tests/test_crest_core.c $(LIB)
	$(CC) $(CFLAGS) tests/test_crest_core.c $(LIB) -o $@ $(LDFLAGS)

$(TEST_BASES): tests/test_crest_bases.c $(LIB)
	$(CC) $(CFLAGS) tests/test_crest_bases.c $(LIB) -o $@ $(LDFLAGS)

# RISC-V cross-build
RISCV_CC     ?= riscv64-linux-gnu-gcc
RISCV_MARCH  = rv64gcv_zba_zbb
RISCV_MABI   = lp64d
RISCV_CFLAGS = -std=c11 -O2 -Wall -Wextra \
               -march=$(RISCV_MARCH) -mabi=$(RISCV_MABI) \
               -fno-strict-aliasing -g \
               -Iinclude

riscv: | $(BUILD)
	$(RISCV_CC) $(RISCV_CFLAGS) -c src/crest_core.c  -o $(BUILD)/crest_core_rv.o
	$(RISCV_CC) $(RISCV_CFLAGS) -c src/crest_bases.c -o $(BUILD)/crest_bases_rv.o
	$(AR) rcs $(BUILD)/libcrest_rv.a \
	    $(BUILD)/crest_core_rv.o $(BUILD)/crest_bases_rv.o
	$(RISCV_CC) $(RISCV_CFLAGS) tests/test_crest_core.c  $(BUILD)/libcrest_rv.a \
	    -o $(BUILD)/test_crest_core_riscv  $(LDFLAGS)
	$(RISCV_CC) $(RISCV_CFLAGS) tests/test_crest_bases.c $(BUILD)/libcrest_rv.a \
	    -o $(BUILD)/test_crest_bases_riscv $(LDFLAGS)
	@echo "Built RISC-V binaries — copy to board and run."

clean:
	rm -rf $(BUILD)
