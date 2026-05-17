# SPINE Runtime Model

**Status:** Skeleton v0.1. Stub document.
**Project:** Epsilon Null Operation (ε₀)
**Companion to:** `spine_core_v0_2_design.md` (and forward to v0.3+)

---

## 0. What this document is

SPINE describes *content*: entities, gestures, scores, patches, scenes.
The runtime executes that content on real hardware: real-time audio,
GPU-paced rendering, scheduled events, allocations, teardowns.

This document captures the runtime model — separately from SPINE
itself, because the language must stay portable across boards and
runtimes, but adjacent to it, because runtime concerns leak back into
language decisions more often than they should.

It is deliberately a **skeleton at this stage**. Sections that lack
evidence are stubs with a note about what would have to be true
before they could be filled in.

### Spillover rule

When SPINE-side design work surfaces something runtime-relevant, a
short paragraph is captured here in the same turn. The SPINE
conversation stays on SPINE; the runtime doc grows as a side effect.

---

## 1. Constraints we know about

These come from the project's stated goals and from prototype evidence
to date.

- **No progress bar.** The demo starts when the user starts it. Any
  precomputation must finish during a brief, masked startup window —
  typically the first scene's fade-in or a logo card. No multi-second
  bars of progress.

- **Tiny binary.** The runtime competes for bytes with the demo's
  content. Anything we can do offline (resolve seeds, lay out
  reachability, plan allocations) is preferable to anything we have
  to ship code for.

- **Reproducibility.** Same `.spine` input + same seed → byte-
  identical render. This rules out free-running RNGs and any "ambient"
  state.

- **Demoscene-honest startup.** Cold-start to first frame should be
  perceived as immediate. Existing demoscene practice (and the game-
  engine analogy) suggests target sub-second cold start for our
  binary sizes; aspirational sub-100ms.

---

## 2. Game-engine analogy

A SPINE-driven demo is structured very much like a real-time game
loop, with a tighter content model. Useful patterns to steal:

- **Streaming asset loading.** Generate scene N+1's precomputed
  entities while scene N plays. SPINE's reachability tells you
  exactly which entities scene N+1 needs that scene N didn't.
- **Frame budget discipline.** Every streaming entity declares its
  per-frame work cost. Offline tooling can warn at build time if a
  scene's streaming entities don't fit the budget.
- **Pooled allocators.** Pre-sized at scene boundaries. Tied to
  SPINE's reachability set.
- **Just-in-time generation.** For very long demos. Most ε₀ demos
  are short enough that whole-scene preallocation is fine.

The reverse (this runtime hosting games) is true and not in scope.

---

## 3. Entity lifetimes — runtime view

SPINE declares four lifetime classes (per dialect template §1.7):
`streaming`, `event-driven`, `precomputed`, `sink`. The runtime
treats each differently.

### 3.1 Precomputed

Built once, before any reachable scene that uses it activates. Result
is cached for the duration of reachability. Examples (eventual):
wavelet impulse responses, wavetables, baked LUTs, gesture trajectory
templates rendered into the basis.

**When built:** During the startup window, plus opportunistically
during earlier scenes for entities reachable only from later scenes
("streaming asset loading," §2).

**Where built:** Any core. Latency-tolerant. Likely a worker pool on
big cores, not the real-time cores.

**Where freed:** Currently undefined. Probably: when no remaining
scene in the demo references the entity. For short demos this means
"never" — they persist until exit. Longer demos may need eviction.

**Open:** Memory pressure handling. What happens if the precomputed
working set exceeds available memory? Probably an offline error, not
a runtime fallback.

### 3.2 Streaming

Runs every tick while reachable. Examples: oscillators, LFOs, filters,
delays. Prototype C's simulator approximates this with a fixed-rate
update loop; the real runtime runs at audio rate (or fragment-rate
for blocks).

**When started:** When the enclosing GRP becomes active. Per open
question §4.3a in `spine_open_questions.md`, this is a streaming-USE
lifetime question that still needs pinning.

**When stopped:** When the enclosing GRP exits, modulated by any
`fade_out` USE-override.

**When torn down:** Within a bounded number of ticks after audible
output ceases. The bound is a runtime guarantee, not a SPINE concern.

**Where executed:** Audio-graph nodes run on the audio thread (real-
time priority). Video-pipeline streaming nodes run on the render
thread. The dialect declares which.

### 3.3 Event-driven

Does work only when an event arrives. Examples: envelopes, dice
(sample-and-hold), `music.note`. State persists between events.

**When triggered:** On any edge into an event-shape input firing.

**Where executed:** Whatever thread is currently dispatching the
event. For audio events that's the audio thread; for scheduled note
events it may be the event thread; for cross-dialect events it
depends on the source.

**Open:** What happens when an event-driven entity outlives the
sender that triggered it? E.g. a long-release envelope after its
clock stops ticking. Probably: the entity continues until its own
state says it's done (envelope reaches idle), then teardown follows
the streaming rules.

### 3.4 Sink

Terminal nodes. Consume input, produce no output. Examples:
`patch.scene_out`, `patch.output`. The simulator probes their inputs
as the canonical "what the listener hears / sees."

**Where executed:** Same thread as its input source. A `scene_out`
fed by an audio graph runs on the audio thread.

---

## 4. Threading model

Speculative; sketched in Prototype C's discussion. Not yet committed.

| Thread          | Priority    | Owns                          |
|-----------------|-------------|-------------------------------|
| audio           | real-time   | streaming audio graphs        |
| render          | vsync-paced | streaming visual graphs       |
| event/main      | soft RT     | USE dispatch, scene switches  |
| worker pool     | best-effort | precomputation, asset decode  |

The audio thread cannot allocate, cannot block, cannot wait on any
other thread. Same for render. Cross-thread communication happens via
lock-free queues or double-buffered swap.

**Open:** How does cross-dialect LNK across threads work? A music
event scheduled on the event thread firing a patch envelope on the
audio thread is the obvious case. Probably: enqueue the event into
the audio thread's incoming queue; the audio thread polls at fragment
boundaries.

---

## 5. Core affinity on K3

K3 (SpacemiT) has three core classes: big out-of-order (X100), small
in-order (A100), and real-time deterministic cores. The runtime maps
threads to core classes; SPINE doesn't.

| Thread          | Suggested core |
|-----------------|----------------|
| audio           | real-time      |
| render          | X100           |
| event/main      | X100 or A100   |
| worker pool     | A100 or X100   |

Speculative. The real-time cores' instruction set and memory model
need verifying against what an audio kernel actually needs. Some
streaming nodes (RVV-heavy convolution, complex resonators) may need
to live on X100 even at the cost of priority inversion handling.

**Open:** Are the K3 real-time cores RV64GC or something narrower? If
narrower, does Prototype-C-quality DSP fit?

---

## 6. Seed resolution

Per the v0.3 cello-phrase discussion: humanize and similar
randomization MOD operators take seeds that inherit through three
levels.

```
score-level seed   (GRP-level attribute)
      ↓ inherits to
MOD-derivation seed (per named variant; optional override)
      ↓ inherits to
USE-level seed     (per performance instance; derived automatically)
```

**Resolution is offline.** The build tool walks every humanize-bearing
entity, resolves its effective seed by hashing
`(parent_seed, entity_id, instance_counter)`, and embeds the resolved
seed in the binary form. The runtime never walks the GRP stack at
humanize evaluation time.

This is the first concrete runtime commitment in the document: do
expensive things offline, ship resolved values.

---

## 7. Frame budget

Speculative. Eventually each streaming/event-driven type declares its
per-tick work cost (in CPU cycles or simulated time units). The
offline tool sums per-scene costs and warns if a scene exceeds the
target budget on a given board.

This is the runtime's equivalent of SMOLR's byte-count report. Both
are "did we fit?" feedback loops, just in different dimensions.

**Open:** What units? Cycles aren't portable. Microseconds per tick
might be the right answer, with a per-board fudge factor.

---

## 8. Allocation strategy

Speculative. Likely:

- Per-scene arena, sized offline.
- Streaming entities live in the scene arena, allocated at scene
  start, freed wholesale at scene end.
- Precomputed entities live in a longer-lived arena, possibly the
  whole-demo arena.
- Event-driven entities follow their parent GRP's arena.
- Nothing on the audio thread allocates after warmup.

**Open:** How does cross-scene state (e.g. a reverb tail that
persists across a transition) work? Probably explicit "carrying"
entities in a transition GRP, but this is a SPINE-side question more
than a runtime one.

---

## 9. Open runtime questions

Not in the main SPINE open-questions file because they're runtime-
side, not language-side. Tracked here.

### 9.1 Audio fragment size vs SPINE tick rate

Prototype C simulates at 100 Hz. Real audio runs at fragment rate
(typically 32–512 samples at 48 kHz = 0.7–10ms per fragment). How
does SPINE's tick model map?

Probably: SPINE's "tick" is the audio fragment boundary, and within
a fragment, audio-rate processing happens conventionally. SPINE
gestures and modulators update per-fragment, not per-sample. Open.

### 9.2 Cross-dialect LNK latency

Music event → patch envelope trigger crosses thread boundaries. What
latency is acceptable? Likely one audio fragment is fine for
demoscene work but worth verifying once we have real audio.

### 9.3 Per-board core mapping discovery

How does the runtime know which cores are real-time on a given board?
Probably configured at build time per target board; no runtime
introspection. K3, Jupiter, and Mars each get their own mapping.

### 9.4 Pre-roll for streaming entities

When a streaming entity starts mid-scene, does it have a warmup
period before audible output begins? A reverb starting from silence
may need a few hundred ms of pre-roll to fill its delay buffers
plausibly. Open.

### 9.5 Memory budget reporting

How does the offline tool report total memory footprint to the
author? Per-scene, per-entity, summary? Probably analogous to
SMOLR's size report.

### 9.6 Gesture transition resolution

Surfaced by the martélé phrase work for SPINE v0.3: the
`transition_from=` USE override gives an instrument the previous
gesture's identity, so it can choose how to negotiate the bow/finger
change. *When* does the instrument resolve this? Two options:

- **Offline.** Resolve at build time, embed a transition descriptor.
  Works for purely-deterministic gestures.
- **At transition moment.** The instrument inspects the previous
  gesture's runtime state (current bow position, vibrato phase,
  humanize roll) and computes the transition. Required when
  humanization has made the state non-deterministic-from-source.

This is the first concrete case where "do it offline" doesn't fully
apply. Most transitions probably can be offline (the humanize jitter
is small enough that a precomputed transition path is acceptable);
some may need runtime resolution. The dialect should be able to
declare which transitions are "stateful" and need runtime work.

Open until a real cello dialect implementation surfaces evidence.

---

## 10. What this document is NOT yet

- Not a specification. The threading model is sketched, not committed.
- Not a contract. Numbers (fragment sizes, core counts) are
  placeholders until verified against real hardware.
- Not a final word on lifetimes. The streaming-USE `dur` question
  (open §4.3a in spine_open_questions.md) directly affects §3.2 here.
- Not detailed enough for an implementer to write the runtime from.
  Several layers of fleshing-out are needed first.

It is a **capture point**. As SPINE work surfaces runtime concerns,
they land here. The document grows in lockstep with the language.

---

## 11. Update log

- **v0.1** (current): skeleton. Sections 1, 2, 6 have committed
  content; everything else is stub-with-stake-in-the-ground.
