# tools/spine

SPINE — the recursive symbolic structure behind Epsilon Null Operation.

The design lives in `docs/spine_core_v0_2_design.md` (project root).
This directory holds the working prototypes: the offline expander, two
worked examples, and tests.

## Status

| Prototype | What                                              | Status |
|-----------|---------------------------------------------------|--------|
| A         | Music dialect, structural compression             | done   |
| B         | Patch dialect, LNK graph resolution               | done   |
| C         | Streaming patches, feedback loops, simulator      | done   |
| D         | TBD                                               | not started |

## Layout

```
tools/spine/
├── src/
│   ├── expand.py             # offline parser + expander, both dialects
│   └── simulate.py           # tick-based simulator for streaming patches
├── tests/
│   ├── test_prototype_a.py   # music dialect smoke test (4 checks)
│   ├── test_prototype_b.py   # patch dialect smoke test (7 checks)
│   └── test_prototype_c.py   # streaming + simulator smoke test (8 checks)
├── examples/
│   ├── phrase_motif.spine                 # rolled-up music score
│   ├── phrase_motif_flat.spine            # hand-flat equivalent
│   ├── phrase_motif.expanded.txt          # reference expansion
│   ├── SIZE_COMPARISON.md                 # rolled vs flat byte comparison
│   ├── synth_voice.spine                  # subtractive synth patch
│   ├── synth_voice.graph.txt              # reference resolved graph
│   ├── bladerunner_sketch.spine           # streaming-soundscape patch
│   ├── bladerunner_sketch.graph.txt       # reference resolved graph
│   ├── bladerunner_sketch.summary.txt     # reference simulation summary
│   ├── bladerunner_sketch.trace.csv       # reference simulation CSV
│   └── bladerunner_sketch.trace.txt       # reference simulation trace
└── docs/
    ├── PROTOTYPE_B.md                     # patch dialect notes
    └── PROTOTYPE_C.md                     # streaming + simulator notes
```

## Quick start

```sh
cd tools/spine

# Run all tests:
make test

# Inspect a music score:
python3 src/expand.py examples/phrase_motif.spine

# Inspect a patch graph:
python3 src/expand.py examples/synth_voice.spine

# Simulate the streaming Bladerunner sketch:
python3 src/simulate.py examples/bladerunner_sketch.spine --summary-only

# Reachability of any of them:
python3 src/expand.py examples/synth_voice.spine --dump-reachable
```

The expander auto-detects which dialect dominates a document and
picks the appropriate output mode (event list vs graph dump). Use
`--mode music` or `--mode patch` to override.

## What this is not

- Not a synthesizer. No audio is produced.
- Not a parser-generator. The text format is hand-tokenized.
- Not a binary format. v0.2 text only.
- Not a runtime. The expander is offline tooling.

Those layers arrive in later prototypes. See
`docs/spine_open_questions.md` for what's deliberately deferred.
