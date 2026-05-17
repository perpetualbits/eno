# SPINE Open Questions

**Companion to:** `spine_core_v0_3_design.md`
Project: Epsilon Null Operation (ε₀)
Status: living document — append as new questions arise

---

## 0. Purpose

These are design questions deliberately deferred from v0.2. Each entry
records:

- the question
- why it is deferred
- what would force a decision
- the current lean, if any

The goal is to keep these out of the main design doc (which should
stay short and decisive) without losing them.

When a question gets answered, it moves into the main doc and gets
struck through here with a date and a pointer.

---

## 1. Format and grammar

### 1.1 Formal grammar (EBNF)

**Question:** What is the exact grammar of the v0.2 text format?

**Deferred because:** Prototype A's hand-written parser will reveal
syntactic awkwardness that a formal grammar would lock in prematurely.

**Force a decision when:** A second tool (renderer, validator,
syntax-highlight plugin) needs to parse `.spine` files independently.

**Current lean:** Wait until after Prototype A and Prototype B
(patchbay) before writing the grammar down. Two real example files are
worth more than one speculative grammar.

### 1.2 Comments and whitespace

**Question:** Are nested block comments allowed? Multi-line strings?
Continuation lines?

**Deferred because:** Hash-to-end-of-line and double-quoted single-line
strings are sufficient for any example I can sketch.

**Force a decision when:** A real coefficient blob needs to be embedded
inline.

### 1.3 Include / import system

**Question:** Can one `.spine` file include another?

**Deferred because:** Single-file demos are fine for the foreseeable
prototypes. Includes invite namespace and dependency problems best
handled after the dialect contract stabilizes.

**Force a decision when:** The library of reusable phrases / patches /
gestures grows past what fits comfortably in one file.

**Current lean:** A simple `INCLUDE "path"` at top-level, no
conditional includes, no macros, no recursive resolution. Mimic C's
`#include` minus the trauma.

---

## 2. Binary format

### 2.1 Binary opcode encoding

**Question:** What is the runtime binary layout? Variable-length
integers? Fixed records? Stream-of-tokens?

**Deferred because:** The text format will change at least twice
during Prototypes A and B. Binary follows text.

**Force a decision when:** A real demo needs to fit under a size
budget where text-form SPINE costs measurable bytes.

**Current lean (subject to change):** 3-bit opcode + varint ids +
dictionary-coded type/operator names + delta-coded times + typed
parameter payloads. Per-domain entropy coding over the final stream.
But this is speculation until measured.

### 2.2 Dictionary scope

**Question:** Is the type-id and operator dictionary global to the
demo, per-dialect, or per-stream?

**Deferred until:** Binary format is designed.

### 2.3 Large coefficient blobs

**Question:** Where do large arrays live — inline, in a separate
data section, in a separate file?

**Deferred because:** Prototype A only uses small vectors.

**Force a decision when:** The first wavelet envelope or impulse
response shows up.

**Current lean:** Inline up to ~64 elements; separate section beyond
that, referenced by id.

---

## 3. Roll-up and structural compression

### 3.1 Near-repetition detection

**Question:** How do we detect "same structure, different parameters"
and roll it into MOD-of-MOD or parameterized templates?

**Deferred because:** Hard algorithm; needs evidence that exact-
repetition roll-up is worth its weight first.

**Force a decision when:** Prototype A shows measurable byte savings
from exact-repetition roll-up, *and* a real demo has obvious
near-repetition the exact algorithm cannot find.

**Current lean:** Likely a similarity score over normalized statement
sequences with bounded edit distance. Probably needs to be operator-
aware (transpose-equivalent phrases are "the same" up to transposition).

### 3.2 Roll-up scoring and stopping

**Question:** When the roll-up tool has many candidate replacements,
how does it choose? Greedy by savings? Search? Beam?

**Deferred until:** First measured roll-up has produced more than one
candidate at a time.

**Current lean:** Greedy by estimated bytes saved, with a
configurable min-savings threshold. Crinkler-style search comes much
later if at all.

### 3.3 Roll-up and randomness

**Question:** If two USEs of `walk_0` use different seeds, are they
"the same"? Should the roll-up promote them with a seed parameter?

**Deferred until:** Seeded determinism is implemented in any dialect.

---

## 4. Time and timing

### 4.1 Non-linear time

**Question:** Can a USE's time mapping be non-linear — a curve, a
loop, a phase function?

**Deferred because:** Linear scaling handles all of Prototype A.

**Force a decision when:** A motion motif needs to phase-lock to
footsteps, or an animation needs a held pose plus a quick exit.

**Current lean:** Introduce a `timewarp` USE-override (or MOD
operator) that names a reference to a time-curve entity. The curve
itself is a `wavelet.spline.env` or similar. Defers complexity to the
referenced entity rather than the time model.

### 4.2 Multi-domain time

**Question:** A group containing both audio and animation events —
does it have one local time or two?

**Deferred because:** Single-domain demos work.

**Force a decision when:** The first audiovisual demo with
synchronization requirements ships.

**Current lean:** One local time per group. Domains agree on the
mapping. If audio and animation disagree, it's two groups linked by a
shared time reference.

### 4.3 Event-driven timing

**Question:** Can event A trigger event B at runtime ("when the
footstep lands, scatter sand")?

**Deferred because:** Pre-baked schedules are sufficient for the
demos we have in mind.

**Force a decision when:** A demo needs interactive or generative
timing.

### 4.3a Streaming-USE lifetime semantics

**Question:** When a USE references a GRP of streaming entities (a
patchbay rather than a scheduled event sequence), what do `at` and
`dur` mean? When does the patch start producing output, and when does
it stop? What happens to allocated state when it stops?

**Status:** Surfaced by Prototype C (the Bladerunner sketch).
Prototype C dodged this by simulating the whole reachable graph for
the entire simulation duration. Real demos cannot dodge it — a
streaming patch must start somewhere and stop somewhere.

**Current lean (from the design conversation):**

- `at` is the wall-clock time the patch begins producing output.
- `dur` omitted → the patch runs while its enclosing GRP is active
  (scene-lifetime).
- `dur` present → the patch runs for `dur` beats, then output is
  gated off.
- A `fade_out` USE-override controls the gating shape:
  - absent → abrupt cutoff
  - `fade_out=N` → linear fade over N beats
  - `fade_out=ref(curve)` → fade following a named envelope/spline

The audible behavior (abrupt vs. fade) is a SPINE concern. The
*executable* behavior (when state is deallocated, when CPU stops
being spent) is a runtime concern. The runtime model document, when
written, will commit to a bound: after audible output ceases, the
streaming graph is torn down within some bounded number of ticks.

**Force a decision before:** Any prototype with scene transitions.

**Open sub-questions:**
- Does `fade_out` apply to event-driven children too, or only
  streaming ones? Probably only streaming — events fire or they don't.
- Does `at` allow negative values, meaning "the patch was already
  running when the scene started, fade it in from the past"? Probably
  not; pre-roll is a separate concern.
- How are precomputed entities scheduled? The build-phase model
  needs articulating, but no prototype needs it yet.

### 4.4 Loops and iteration

**Question:** Is there an explicit "repeat N times" construct, or do
N USEs handle it?

**Status update:** Drum patterns and other rhythmic motifs make the case
clear: writing 3 or 8 explicit USEs of the same group is byte-expensive
at the source level, and obscures the author's intent ("this thing
repeats N times" vs. "this thing happens at these specific moments").

**Likely answer:** Yes, as a USE override:

```text
USE drum_pattern_0 at 8.0 dur 2.0 repeat=3    # plays 3x, each 2.0 long
USE drum_pattern_0 at 24.0 dur 2.0 repeat=2   # plays 2x at a different point
```

`repeat=N` means N consecutive plays starting at `at`, each lasting
`dur`. Total span is `N * dur`. Equivalent to N explicit USEs but
shorter to write and easier for the roll-up tool to recognize as
intentional iteration.

**Force a decision before:** Prototype B (patchbay) starts. Music
prototypes will exercise repeat heavily; deferring further risks
collecting workarounds.

**Open sub-questions:**
- Should `repeat=N` interact with seed inheritance such that each
  iteration gets a fresh implicit seed offset? (Likely yes — same
  mechanism as N explicit USEs.)
- Should there be a `gap=t` companion override for "play 3 times with
  half a beat between"? (Possibly. Or just author with two GRPs.)

---

## 5. Value types and expressions

### 5.1 Computed values

**Question:** Can a parameter value be an expression like `a + 2 * b`?

**Deferred because:** No prototype needs it yet.

**Force a decision when:** A real demo wants "this resonator's size is
twice that one's."

**Current lean:** A `compute` value type referencing other entities'
parameters. Pure functional, no side effects. But introduce only when
needed.

### 5.2 Curves as first-class values

**~~Open~~ RESOLVED in v0.3** (`spine_core_v0_3_design.md` §4.4).

**Resolution:** A curve is a value type, accepting two surface forms:
canonical `ref(curve_entity)` and verb sugar
(`rise 0.0 0.7`, `decelerando 0.7`). Both desugar to entity
references at parse time. Inline curve points are still deferred.

### 5.3 Blobs

**Question:** When does a vector become a blob? What's the cutoff?

**Deferred until:** Real coefficient arrays exist.

**Current lean:** ~64 elements. Above that, separate section with
id-reference. Below, inline.

---

## 6. Type checking and validation

### 6.1 Dialect type checking

**Question:** Does the dialect interpreter validate that a USE's
overrides match the operator signatures? Or do bad inputs just produce
weird output?

**Deferred because:** Prototype A author is the same person as the
interpreter implementer.

**Force a decision when:** A second author writes a `.spine` file.

**Current lean:** Warn on unknown overrides; error on type mismatch;
continue on out-of-range index. Be permissive but loud.

### 6.2 Cross-dialect LNK validation

**Question:** How do we check that `music.phrase.out` and
`audio.instrument.in` are compatible?

**Deferred because:** Only `music` exists in v0.2.

**Force a decision when:** The audio dialect lands.

**Current lean:** Each port declares a *shape* (`event_stream`,
`signal`, `texture`, `value`). The host checks shape match at LNK
resolution time. Detailed type compatibility is the dialect's problem.

---

## 7. Randomness and determinism

### 7.1 Seed model

**~~Open~~ RESOLVED in v0.3** (`spine_core_v0_3_design.md` §4.5).

**Resolution:** three-level inheritance.

1. **Score-level** — a `seed N` attribute on a GRP. Sets the root
   seed for all reachable descendants.
2. **MOD-derivation-level** — explicit `seed N` in a humanize MOD.
   Overrides inherited score-level seed for that named variant and
   anything derived from it.
3. **USE-level** — explicit `seed=N` USE override. Affects this
   instance only.

Effective seeds are derived by hashing
`(inherited_seed, entity_id, instance_counter)`. Resolution is
**offline**: the build tool walks every humanize-bearing entity and
embeds the resolved seed in the binary form. The runtime never walks
the GRP stack at humanize evaluation time.

**Constraint on roll-up:** the roll-up tool may NOT merge two USEs
with different effective seeds, even if their surface MOD chain is
identical. Two notes both written `gesture=vib_swell_h` produce
different jitter because their instance counters differ; this is
audible content, not implementation detail.

Implementation status: Prototype D records each humanize-bearing
entity's seed-derivation tuple `(parent_seed, entity_id,
instance_counter)`. Real hashing to a final seed integer is
scheduled for the first audio-producing prototype.

### 7.2 Probabilistic operators

**Question:** Can MOD operators be probabilistic ("transpose by a
random value in [-2, +2]")?

**Deferred until:** Seed model is decided.

**Current lean:** Yes, but the result must be reproducible from the
seed. So `MOD x_drift = x transpose_rand seed=123 range=[-2,2]` rather
than `transpose_rand range=[-2,2]` alone.

---

## 8. Streaming and runtime

### 8.1 Progressive decoding

**Question:** Can a long demo stream-decode SPINE as it plays, or must
the whole document be in memory?

**Deferred because:** Demoscene demos are short. Whole-program load is
fine.

**Force a decision when:** A demo exceeds available memory (unlikely
under any realistic scenario) or wants generative open-ended runtime.

### 8.2 Just-in-time MOD evaluation

**Question:** When MOD chains get deep (`MOD a3 = a2 ...; MOD a2 = a1
...; MOD a1 = a0 ...`), do we evaluate eagerly at load time or lazily
at first USE?

**Deferred because:** Prototype A's MOD chains are shallow.

**Current lean:** Eager. Tiny runtime, no thunks.

---

## 9. Dialect system

### 9.1 Dialect plug-in mechanism

**Question:** How does the runtime know which interpreter handles
which dialect prefix? A static table? A registration call?

**Deferred until:** Two dialects coexist.

**Current lean:** Static table compiled in. Dialects are a
build-time choice, not a runtime one. SMOLR-style atom discipline
applies: only used dialects link in.

### 9.2 Operator name collisions

**Question:** Two dialects both define `transpose` — is that legal?
Does it matter?

**Deferred until:** It happens.

**Current lean:** Operators are scoped to type ids, so
`music.transpose` and `motion.transpose` are distinct. Authors write
`transpose` only because the source entity's dialect disambiguates.
Cross-dialect MOD is rare.

### 9.3 Dialect versioning

**Question:** What happens when the `music` dialect changes between
v0.2 and v0.3?

**Deferred because:** Only one version exists.

**Current lean:** Every dialect declares a version. Stored documents
declare which version of each dialect they require. Mismatch is an
error with a clear message; migration is offline.

### 9.4 Feedback-eligible input ports

**Question:** How does a dialect declare which input ports may
participate in a feedback cycle? Prototype C codifies this as
`PATCH_FEEDBACK_INPUTS` in `expand.py`, a hardcoded set of
`(type_id, port_name)` tuples that whitelist `patch.delay.in` and
`patch.allpass_delay.in`. Should this graduate to a per-dialect
schema?

**Status:** Working as designed for two patch types. The list will
grow as the patch dialect grows (likely `patch.feedback_node`,
maybe `patch.echo`, eventually wavelet-based reverbs with feedback).
A new dialect (e.g. `wavelet.coefficient_field` with state-fed
operators) might want its own feedback-eligible ports.

**Force a decision when:** A third dialect introduces feedback-
capable ports.

**Current lean:** Move into the dialect template's port catalog as
an optional per-port flag (e.g. `feedback_eligible: true`). The
topo sort reads this flag instead of a global set. Cheap rename, no
semantics change.

### 9.5 Multi-source input combining

**Question:** When multiple LNKs target the same input port, how
are they combined? Prototype C's simulator sums signal/value
sources and OR's event sources. Is this universal across dialects,
or per-dialect, or per-port?

**Status:** Implemented in the simulator; documented in
`spine_core_v0_2_design.md` §3.5. Currently dialect-blind: signal
+ signal = sum, event OR event = either-fires.

**Force a decision when:** A dialect wants different semantics
(e.g. "first-wins," "blend with a parameter," "stereo-pan based on
source index").

**Current lean:** Keep universal for v0.2 (sum signals, OR events).
Per-port overrides via a `combine: sum | first | latest | replace`
field in the port catalog if a real need surfaces. Mixer-style
"weighted blend" is best expressed as an explicit `patch.mixer`
node, not a port semantic.

---

## 10. Tooling

### 10.1 Editor support

**Question:** Syntax highlighter? Folding? Reference navigation?

**Deferred because:** Plain editors and ad-hoc regex work for
Prototype A.

**Force a decision when:** Hand-authoring fatigue sets in.

### 10.2 Visualization

**Question:** Is there a tool that draws a `.spine` file as a graph
(entities, references, LNKs, GRPs as boxes)?

**Deferred because:** Files are still small enough to read.

**Force a decision when:** A demo's reference graph stops fitting in
one's head.

**Current lean:** Graphviz output from a tiny tool. Read-only. No
graphical editor.

### 10.3 Differential testing

**Question:** How do we verify the expander matches a hand-written
flat reference?

**Already decided for Prototype A:** Diff `phrase_motif.expanded.txt`
against `phrase_motif_flat.spine`'s own expansion. They must match
byte-for-byte after canonical formatting.

---

## 11. Re-entry checklist for future-me

If you come back to SPINE after a long break and something in this
document feels wrong, do this:

1. Re-read the v0.2 main design doc first.
2. Re-read this file.
3. If a deferred question now has a clear answer:
   - Move it into the main doc.
   - Strike it through here with the date and a pointer.
   - Note what evidence forced the answer.
4. If a new question has appeared:
   - Add it here, not in the main doc.
   - Use the same shape (question / deferred because / force a
     decision when / current lean).

The main doc gets shorter over time as questions resolve. This file
gets longer. That ratio is the project being honest about what it
knows.
