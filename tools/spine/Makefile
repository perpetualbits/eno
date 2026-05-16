# tools/spine/Makefile
#
# SPINE expander — Prototypes A (music) and B (patch).
# No build artifacts; the expander is pure Python. Targets are
# convenience wrappers around python3 invocations.

PY        ?= python3
SRC       := src/expand.py
EXAMPLES  := examples

.PHONY: help test test-a test-b music patch reachable clean

help:
	@echo "Targets:"
	@echo "  test       run all SPINE prototype tests"
	@echo "  test-a     run Prototype A (music) tests only"
	@echo "  test-b     run Prototype B (patch) tests only"
	@echo "  music      expand the phrase_motif example"
	@echo "  patch      resolve the synth_voice patch graph"
	@echo "  reachable  dump reachability for synth_voice"
	@echo "  clean      remove __pycache__ directories"

test: test-a test-b

test-a:
	@$(PY) tests/test_prototype_a.py

test-b:
	@$(PY) tests/test_prototype_b.py

music:
	@$(PY) $(SRC) $(EXAMPLES)/phrase_motif.spine

patch:
	@$(PY) $(SRC) $(EXAMPLES)/synth_voice.spine

reachable:
	@$(PY) $(SRC) $(EXAMPLES)/synth_voice.spine --dump-reachable

clean:
	@find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
