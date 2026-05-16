# PROTOTYPE_B.md

Prototype B for SPINE v0.2 — patchbay resolution.

## What it does

The expander now supports a second dialect: `patch`. A `.spine` file
describing a graph of patch nodes connected by LNKs is resolved into:

- a node list (DEF parameters with MOD overrides applied),
- an edge list (annotated with source and destination port shapes),
- a topological order,
- warnings for port-shape mismatches.

This is what LNK looks like when it does real work, not just record a
connection.

## What it does NOT do

No audio synthesis. No signal generation. The output is a text dump of
the resolved graph. Phase 2+ adds an audio dialect that consumes this
description; v0.2 stops at "the graph is well-formed."

## What's new since Prototype A

| Concern                          | Prototype A | Prototype B |
|----------------------------------|-------------|-------------|
| Number of dialects               | 1 (music)   | 2 (music, patch) |
| LNK behavior                     | recorded    | resolved into a graph |
| Port shapes                      | n/a         | signal/value/event, checked |
| MOD on a typed entity            | music ops   | + `patch.set` |
| Output kind                      | event list  | graph dump or event list (auto-detected) |
| Multi-arg MOD operators          | none        | `set <key> <value>` |
| Cross-dialect connections        | n/a         | LNK records + shape-validates |

## Running

Run from `tools/spine/`:

```sh
# Patch graph from synth_voice.spine:
python3 src/expand.py examples/synth_voice.spine

# Music events from phrase_motif.spine (Prototype A, unchanged):
python3 src/expand.py examples/phrase_motif.spine

# Reachability dump (works for both):
python3 src/expand.py examples/synth_voice.spine --dump-reachable
```

Or use the Makefile targets: `make test`, `make patch`, `make music`,
`make reachable`.

The expander auto-detects which dialects the document uses and picks
the appropriate output mode. Override with `--mode patch` or
`--mode music` if needed.

## Reading the patch graph output

Example output:

```
# patch graph: 8 nodes, 10 edges
# warnings: 1
# WARN  osc_1.out -> env_1.trigger: port shape mismatch: signal -> event

# topological order:
#   osc_1
#   env_1
#   filt_1
#   ...

node osc_1 : patch.oscillator
    freq = 220.0
    waveform = 'sawtooth'

...

edge amp_1.out -> out_main.in  [signal -> signal]
edge osc_1.out -> env_1.trigger  [signal -> event]  WARNING: port shape mismatch: signal -> event
```

- The header line summarizes counts.
- Warnings appear as `# WARN` comments at the top, prefixed in
  individual edges, and are also written to stderr so test harnesses
  can detect them without parsing the body.
- Topological order is reported as a comment block.
- Each node lists its resolved parameters (DEF + any MOD overrides).
- Edges are sorted by (src_node, src_port, dst_node, dst_port) for
  stability across runs.
- Port shapes in `[src_shape -> dst_shape]` use the dialect's port
  catalog (see `PATCH_PORTS` and `MUSIC_PORTS` in `expand.py`).

## Port shapes

Defined in the dialect template (§1.3) and codified in `expand.py`:

- `signal` — continuous audio-rate data (oscillator outputs, filter
  outputs).
- `value` — slow control data (envelope output driving a filter cutoff).
- `event` — discrete trigger / note_on / note_off.

Matching shapes connect cleanly. Mismatches are recorded but warned —
the design decision (open question §6.2) was "warning, not error" for
v0.2. Future dialects may introduce additional shapes; the catalog is
the source of truth.

## Cross-dialect LNK

`music.phrase.note_on -> patch.envelope.trigger` is a legal connection
because both ports declare shape `event`. The host (expand.py) routes
this without either dialect needing to know about the other. This is
the §6.2 design point in action: cross-dialect compatibility lives
in the shared port catalog, not in the dialects themselves.

## Tests

```sh
python3 tests/test_prototype_b.py
```

Seven checks: reference graph match, MOD override + inheritance,
cross-dialect matched/mismatched edges, reachability, topo constraints,
and Prototype A regression.

## What this surfaced for the design docs

Three observations that should fold back into the design before
Prototype C:

1. **MOD operator arity is now non-uniform.** `transpose` takes one
   arg, `set` takes two. The parser handles this via a tiny arity
   table. The dialect template (§1.4) currently says "argument shape"
   per operator — that wording is enough, but worth a sentence in the
   main design doc clarifying that arity ≥1 is supported.

2. **Port shapes are a third axis** the dialect template doesn't yet
   spell out in its empty form. The `music` dialect declared them in
   §2.3 informally; Prototype B made them load-bearing. Worth pulling
   into the template's §1.3 as a first-class requirement.

3. **Auto-detection of output mode** is convenient but ad-hoc. A
   demo with both dialects would need both kinds of output. Future
   prototypes that mix audio events with patch graphs will need to
   either run both in sequence or define a multi-mode output. For now,
   `--mode` overrides the auto-detection.

## Open questions newly relevant

These items from `spine_open_questions.md` now have concrete evidence
behind them:

- **§6.2** Cross-dialect LNK validation — implemented as a warning
  path. Working as designed. The decision to defer hard errors looks
  correct: the deliberate mismatch in the example was instructive, not
  destructive.
- **§9.1** Dialect plug-in mechanism — currently a static catalog
  baked into `expand.py`. Fine for two dialects. Worth revisiting
  before adding a third.
- **§9.2** Operator name collisions — `set` is patch-only for now.
  When the music dialect grows a `set` operator (it might, for per-
  instance parameter overrides), the dispatch via type-id prefix
  should keep them disjoint. Confirmed by reading the code, not yet
  exercised.
