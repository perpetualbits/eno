# SMOLA Makefile

PYTHON ?= python3
SMOLA  := $(PYTHON) src/bin/smola

.PHONY: all test examples clean help

help:
	@echo "Targets:"
	@echo "  test        - run unit tests"
	@echo "  examples    - translate all .smola files in examples/"
	@echo "  clean       - remove generated .s files"
	@echo ""
	@echo "Variables:"
	@echo "  PYTHON      - python interpreter (default: python3)"

test:
	$(PYTHON) tests/run_tests.py tests

EXAMPLES_SRC := $(wildcard examples/*.smola)
EXAMPLES_OUT := $(EXAMPLES_SRC:.smola=.s)

examples: $(EXAMPLES_OUT)

%.s: %.smola
	$(SMOLA) $< -o $@

clean:
	rm -f examples/*.s

all: test examples
