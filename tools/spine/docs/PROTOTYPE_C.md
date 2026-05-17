# PROTOTYPE_C.md

Prototype C for SPINE v0.2 — streaming patches and the simulator.

## What it does

A SPINE patch can now describe a self-sustaining, time-extended audio
graph: oscillators that run forever, modulators that evolve, sequencers
that fire on a clock, and feedback loops through delay lines. The
expander resolves the graph as before; a new `src/simulate.py` ticks
the graph at a fixed rate and produces a trace.

The Bladerunner-style sketch example exercises every new piece in one
~15-node patch.

## What's new

| Concern                          | Prototype B | Prototype C |
|----------------------------------|-------------|-------------|
| Patch node types                 | 5           | 15          |
| Lifetime in dialect contract     | implicit    | explicit (streaming / event-driven / sink) |
| Feedback loops                   | rejected    | allowed through delay-line inputs |
| Output kind                      | graph dump  | + tick simulation trace (CSV + readable + summary) |
| Multi-source inputs              | last-wins   | summed (signal/value) or OR'd (event) |
| Cycle detection                  | Kahn fails  | two-pass: detect, then designate eligible back-edges |

## New patch types

Streaming:
  - `patch.lfo` — slow periodic value
  - `patch.noise` — random signal
  - `patch.clock` — periodic trigger emitter
  - `patch.lowpass`, `patch.highpass` — specialized filters
  - `patch.delay`, `patch.allpass_delay` — feedback-capable delays
  - `patch.mixer` — multi-input summer (in0…in7)
  - `patch.scene_out` — streaming-aware terminal node

Event-driven:
  - `patch.dice` — sample-and-hold on trigger

The Prototype B types (`patch.oscillator`, `patch.envelope`,
`patch.filter`, `patch.gain`, `patch.output`) remain.

## Feedback semantics

Two ports are designated as "feedback-eligible" in
`PATCH_FEEDBACK_INPUTS`:

  - `patch.delay.in`
  - `patch.allpass_delay.in`

An edge into one of these ports is allowed to participate in a cycle.
The topological sort uses a two-pass strategy: first try ordering with
all edges, and only if a cycle remains, mark cycle-participating
feedback-eligible edges as actual feedback (excluded from ordering)
and try again. Any cycle that does NOT route through a delay is a real
error and is reported.

This avoids the trap of marking every delay-input edge as feedback,
which would let a simple `mixer -> delay -> out` chain be placed in
the wrong order.

## Lifetime classification

Each entity type declares one of:

  - `streaming` — produces output every tick while active
  - `event-driven` — does work only in response to events
  - `precomputed` — built once before activation; v0.2 has none of these
  - `sink` — terminal node, consumes input, no output

Lifetime is declared in `PATCH_PORTS` / `MUSIC_PORTS` in `expand.py`.
The dialect template's §1.7 will be updated to document this; for now
the truth is in code.

## The simulator

`src/simulate.py` runs the resolved patch graph for N simulated
seconds at a fixed tick rate. It is not a real synthesizer:

  - Tick rate defaults to 100 Hz (audio is much higher).
  - Oscillators use `sin(2πft)` regardless of waveform parameter for
    sine; square/sawtooth/triangle use simple piecewise functions.
  - Filters use 1-pole IIR with a wide approximation of the cutoff.
  - Delays are sample-shift buffers.
  - All stubs are honest about being design-validation tools, not
    audio.

The point: prove the graph resolves coherently, feedback loops
converge, no NaN/Inf, signal actually propagates from sources to sinks.

### Output formats

Three outputs are produced from one simulation run:

  - **Summary** (always to stdout): per-probe min/max/mean/RMS plus
    NaN/Inf/flat flags. This is what the test suite asserts on.
  - **CSV trace** (`--csv FILE`): one row per tick, one column per
    probe. Easy to diff or plot.
  - **Human-readable trace** (`--trace FILE`): one line per (tick,
    probe). Long but greppable.

### Default probes

Without `--probes`, the simulator selects:

  - `in` port of every `patch.scene_out` (the canonical "what you'd
    hear")
  - `out` port of every `patch.lfo` (modulation source visibility)

Override with `--probes node1.port1,node2.port2,...`.

### Multi-source inputs

A port can receive multiple incoming edges. The simulator sums them
for signal/value shapes and OR's them for event shapes. This is how
the Bladerunner reverb works: `master_mix.out` and `reverb_ap2.out`
both feed `reverb_ap1.in`, and the delay sees their sum.

This was a Prototype B bug (last-wins overwrite); it only surfaced
when Prototype C introduced delays. Fixed by changing the simulator's
incoming-edge map from `{port: source}` to `{port: list[sources]}`.

## Running

From `tools/spine/`:

```sh
# Resolve and print the graph:
python3 src/expand.py examples/bladerunner_sketch.spine

# Simulate for 5 s, default probes, brief trace on stdout:
python3 src/simulate.py examples/bladerunner_sketch.spine

# Just the summary:
python3 src/simulate.py examples/bladerunner_sketch.spine --summary-only

# Write CSV + human trace files:
python3 src/simulate.py examples/bladerunner_sketch.spine \
    --csv /tmp/trace.csv --trace /tmp/trace.txt --summary-only

# Probe specific nodes:
python3 src/simulate.py examples/bladerunner_sketch.spine \
    --probes seq_dice.out,scene_main.in
```

Or via the Makefile: `make simulate-c`, `make test-c`.

## What this surfaced for the design

Things that need to fold back into the SPINE design docs before
Prototype D:

1. **Lifetime is now a first-class dialect-contract field.** Update
   `spine_dialect_template.md` §1.7 to require it explicitly.

2. **Feedback-eligible input ports** are a dialect-level declaration.
   Currently in code as `PATCH_FEEDBACK_INPUTS`; should be documented
   in the dialect template as part of the port catalog.

3. **Multi-source input ports** are legal and have summation semantics
   (or OR for events). Should be added to the main design doc §3.5
   (LNK).

4. **Streaming USE lifetime** still has open questions: when does a
   streaming USE start, when does it stop, what does `dur` mean. This
   prototype dodged the question by running the entire reachable
   graph for the full simulation. Open question §4.2 of
   `spine_open_questions.md` (or a new one) needs to commit to a
   model before any prototype with actual scene transitions.

5. **The runtime model document** is now overdue. The simulator's
   ad-hoc "tick everyone in topo order, feedback edges see last
   tick's values" works for design validation but is not the
   eventual real runtime model. A separate `spine_runtime_model.md`
   should sketch how this maps to threads and cores on K3.

## Open questions newly relevant

- **§4.2 streaming dur semantics.** Touched but not resolved.
- **§4.4 repeat=N.** Still relevant for Prototype D+ (rhythmic music).
- **§6.2 cross-dialect LNK validation.** Confirmed working through B
  and C; no need to revisit unless behavior changes.
- **New: feedback-edge eligibility per dialect.** Should the dialect
  template specify these ports? Probably yes.
- **New: streaming entity teardown.** When a GRP exits, what happens
  to the streaming nodes inside? Runtime concern, deferred.

## Bugs caught during bring-up

1. **Eager feedback flagging.** First version marked every edge into
   a delay input as feedback. This put nodes whose only out-edge fed
   a delay (like master_mix) at the end of the topo order, which
   meant their values weren't ready when downstream non-delay nodes
   read them. Fixed with two-pass topo: only mark feedback when
   needed to break a cycle.

2. **Multi-source overwrite.** Inherited from B: the simulator's
   incoming-edge map stored one source per port, last-wins. With B's
   examples this was harmless. With C's delays, the feedback edge
   overwrote the regular signal edge and the reverb input silently
   went to zero. Fixed with list-valued incoming map and per-shape
   combining (sum for signal/value, OR for event).

Both bugs are the kind of thing that only surfaces with a real
multi-feature example. The Bladerunner sketch caught them within
minutes; a smaller test would not have.
