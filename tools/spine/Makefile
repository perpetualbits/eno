# tools/spine/Makefile
#
# SPINE expander + simulator — Prototypes A (music), B (patch),
# C (streaming patches), D (cello dialect).
# No build artifacts; pure Python. Targets are convenience wrappers.

PY        ?= python3
EXPAND    := src/expand.py
SIM       := src/simulate.py
EXAMPLES  := examples

.PHONY: help test test-a test-b test-c test-d music patch simulate-c \
        cello reachable clean

help:
	@echo "Targets:"
	@echo "  test         run all SPINE prototype tests"
	@echo "  test-a       run Prototype A (music) tests only"
	@echo "  test-b       run Prototype B (patch) tests only"
	@echo "  test-c       run Prototype C (streaming) tests only"
	@echo "  test-d       run Prototype D (cello) tests only"
	@echo "  music        expand the phrase_motif example"
	@echo "  patch        resolve the synth_voice patch graph"
	@echo "  simulate-c   simulate the bladerunner_sketch"
	@echo "  cello        resolve the cello_phrases example"
	@echo "  reachable    dump reachability for synth_voice"
	@echo "  clean        remove __pycache__ directories"

test: test-a test-b test-c test-d

test-a:
	@$(PY) tests/test_prototype_a.py

test-b:
	@$(PY) tests/test_prototype_b.py

test-c:
	@$(PY) tests/test_prototype_c.py

test-d:
	@$(PY) tests/test_prototype_d.py

music:
	@$(PY) $(EXPAND) $(EXAMPLES)/phrase_motif.spine

patch:
	@$(PY) $(EXPAND) $(EXAMPLES)/synth_voice.spine

simulate-c:
	@$(PY) $(SIM) $(EXAMPLES)/bladerunner_sketch.spine --summary-only

cello:
	@$(PY) $(EXPAND) $(EXAMPLES)/cello_phrases.spine

reachable:
	@$(PY) $(EXPAND) $(EXAMPLES)/synth_voice.spine --dump-reachable

clean:
	@find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
