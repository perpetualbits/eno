# SMOLA Makefile

PYTHON ?= python3
SMOLA  := $(PYTHON) src/bin/smola

.PHONY: all test examples clean help check-assembles

help:
	@echo "Targets:"
	@echo "  test            - run unit tests (no external deps)"
	@echo "  examples        - translate all .smola in examples/ to .s"
	@echo "  check-assembles - assemble each .s with riscv64-linux-gnu-as"
	@echo "                    (requires the cross toolchain)"
	@echo "  clean           - remove generated .s files"

test:
	$(PYTHON) tests/run_tests.py tests

EXAMPLES_SRC := $(wildcard examples/*.smola)
EXAMPLES_OUT := $(EXAMPLES_SRC:.smola=.s)

examples: $(EXAMPLES_OUT)

%.s: %.smola
	$(SMOLA) $< -o $@

check-assembles: examples
	@for s in examples/*.s; do \
	    echo "    AS  $$s"; \
	    riscv64-linux-gnu-as -march=rv64gcv -o /dev/null $$s || exit 1; \
	done
	@echo "All SMOLA examples assemble cleanly."

clean:
	rm -f examples/*.s
	find . -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

all: test examples
