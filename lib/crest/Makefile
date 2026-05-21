# lib/crest/Makefile
#
# Builds:
#   build/libwavelet.a       Static library, linked into other ENO components.
#   build/test_wavelet       Test binary, links the static library.
#
# Targets:
#   make           Build everything.
#   make test      Build and run the test suite.
#   make clean     Remove build artifacts.
#   make riscv     Cross-compile for RISC-V (requires riscv64-linux-gnu-gcc).

CC      ?= gcc
AR      ?= ar

CFLAGS  = -std=c11 -O2 -Wall -Wextra -Wpedantic \
          -fno-strict-aliasing -g \
          -Iinclude

LDFLAGS = -lm

BUILD   = build
SRCS    = src/wavelet.c
OBJS    = $(BUILD)/wavelet.o
LIB     = $(BUILD)/libwavelet.a
TEST    = $(BUILD)/test_wavelet

.PHONY: all test clean riscv

all: $(LIB) $(TEST)

test: $(TEST)
	./$(TEST)

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/wavelet.o: src/wavelet.c include/wavelet.h | $(BUILD)
	$(CC) $(CFLAGS) -c src/wavelet.c -o $@

$(LIB): $(OBJS)
	$(AR) rcs $@ $(OBJS)

$(TEST): tests/test_wavelet.c $(LIB)
	$(CC) $(CFLAGS) tests/test_wavelet.c $(LIB) -o $@ $(LDFLAGS)

# RISC-V cross-build
RISCV_CC     ?= riscv64-linux-gnu-gcc
RISCV_MARCH  = rv64gcv_zba_zbb
RISCV_MABI   = lp64d
RISCV_CFLAGS = -std=c11 -O2 -Wall -Wextra \
               -march=$(RISCV_MARCH) -mabi=$(RISCV_MABI) \
               -fno-strict-aliasing -g \
               -Iinclude

riscv: | $(BUILD)
	$(RISCV_CC) $(RISCV_CFLAGS) -c src/wavelet.c -o $(BUILD)/wavelet_rv.o
	$(AR) rcs $(BUILD)/libwavelet_rv.a $(BUILD)/wavelet_rv.o
	$(RISCV_CC) $(RISCV_CFLAGS) tests/test_wavelet.c $(BUILD)/libwavelet_rv.a \
		-o $(BUILD)/test_wavelet_riscv $(LDFLAGS)
	@echo "Built $(BUILD)/test_wavelet_riscv — copy to board and run."

clean:
	rm -rf $(BUILD)
