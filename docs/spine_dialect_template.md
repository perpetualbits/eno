# SPINE Dialect Template

**Companion to:** `spine_core_v0_3_design.md`
Project: Epsilon Null Operation (ε₀)
Status: v0.3 — empty template + worked examples (`music`, `cello` sketch)

---

## 0. What this document is

SPINE core knows nothing about cellos, caves, fractals, or robes. A
**dialect** is what tells SPINE what those things are.

To prevent dialects from drifting into incompatible ad-hoc shapes as
the library grows, every dialect is defined by a one-page contract
filling in the template in §1. The `music` dialect in §2 is the v0.2
worked example, just enough to run Prototype A.

A dialect is a *specification document* plus a *dialect interpreter*
(code that consumes SPINE events and produces domain output). The
specification is what stays stable. The interpreter is allowed to
evolve.

---

## 1. The template

Copy this section as the starting point for a new dialect.

### 1.1 Domain

- **Domain name:** `<short_lowercase>` — appears as the prefix in type
  ids like `<domain>.<family>.<type>`.
- **Purpose:** One paragraph. What problem does this dialect describe?
- **Status:** Draft / stable / deprecated.

### 1.2 Type ids

For every entity type this dialect introduces, list:

- **Type id:** `<domain>.<family>.<type>`
- **Description:** One line.
- **Required parameters:** name and value type.
- **Optional parameters:** name, value type, default.
- **Notes:** anything dialect-specific.

Example row format:

```text
Type id:    music.phrase
Required:   notes: vector
Optional:   step: float = 1.0    swing: float = 0.0
Notes:      A linear sequence of notes spaced by `step` local-time units.
```

### 1.3 Ports

For each type, list the named endpoints LNK can target.

```text
Type:       music.phrase
Inputs:     (none in v0.2)
Outputs:    out  — emits note events
```

If a type has no ports, say so explicitly.

### 1.4 Operators

For each MOD operator this dialect supports, list:

- **Operator name**
- **Arity:** how many tokens after the operator name belong to it
  (default 1; v0.3 supports mixed)
- **Argument shape:** e.g. `+N` (signed int), `vector`, `bool`,
  `<key> <value>` (the patch dialect's `set`), `<curve>` (a curve
  value)
- **Verb forms** (if the operator accepts curve sugar): the verb names
  and what each maps to, e.g. `rise <a> <b>` → linear ramp from a to
  b; `fall <a> <b>` → linear ramp down; `decelerando <factor>` →
  named curve from the dialect's curve library
- **Applies to which types**
- **Effect**
- **Composes with:** which other operators it stacks cleanly with

Operators are also valid as USE override keys unless explicitly marked
"MOD-only."

### 1.5 Override keys

If the dialect introduces USE override keys that are *not* MOD
operators, list them here. These are usually instance-only properties
(gain, seed, channel routing) that don't make sense as named MOD
derivations.

### 1.6 Time interpretation

How does this dialect interpret a group's local time?

- **Time-positioned types:** which type ids inside a group are placed
  by `at` and `dur`.
- **Non-time-positioned types:** which type ids ignore time (e.g. patch
  nodes, materials).
- **Positioning mode:** *sequential* (USE without `at` starts where the
  previous USE ended) or *positioned* (USE without `at` defaults to
  0.0). Music-like dialects pick sequential; scene/animation dialects
  usually pick positioned. Mixed dialects must justify the choice.
- **Stretching behavior:** when a USE changes a group's duration, how
  do contents respond?
- **Default local duration:** how is local duration computed if a GRP
  doesn't declare one?

### 1.7 Lifetime and execution

Each type declares one **lifetime**:

- **streaming** — produces output continuously while reachable. Costs
  CPU every tick. Examples: oscillators, LFOs, filters, delays.
- **event-driven** — does work only when an event arrives at one of
  its event-shape inputs. Costs CPU only on trigger. Examples: envelopes,
  sample-and-hold (`patch.dice`), `music.note`.
- **precomputed** — built once before activation, then read-only.
  Examples (future): wavelet impulse responses, wavetables, baked LUTs.
  Streaming entities may reference precomputed ones via `ref()`.
- **sink** — terminal node, consumes input, produces no output. Example:
  `patch.scene_out`.

Lifetime is declared in the dialect's port catalog (currently in
`expand.py` as `PATCH_PORTS` and `MUSIC_PORTS`; future versions will
factor this into a dialect-specific schema file).

Lifetime affects how a runtime schedules the entity (deferred to the
runtime model document), how the simulator ticks it, and how
reachability handles its teardown when a GRP exits (open).

### 1.8 Transition table (optional)

For dialects with gesture transitions (cello, motion, etc.), declare
how (from_gesture, to_gesture) pairs resolve. The `transition_from=`
USE override (SPINE core §3.2) carries the marker; this table tells
the dialect's resolver what to do with it.

A transition table entry typically declares:

- **from_gesture** — type id pattern (may use wildcards within domain)
- **to_gesture** — same
- **resolver** — symbolic name of the handoff procedure
  (`continue_bow`, `lift_then_attack`, `crossfade_over_N_ticks`)
- **runtime_state_needed** — bool. If true, the resolver requires
  inspecting the previous gesture's live state and cannot be fully
  resolved offline. See `spine_runtime_model.md` §9.6.

Most dialects do not have transitions and skip this section.

### 1.9 Interpreter notes

- **Implementation:** language, location in repo.
- **Output:** what the interpreter produces (events, samples, frames,
  text, geometry).
- **Dependencies on other dialects:** if any.
- **Known limitations / TODO.**

### 1.10 Open questions

Dialect-specific open questions, separate from the global ones in
`spine_open_questions.md`.

---

## 2. Worked example: the `music` dialect (v0.2)

This is the dialect Prototype A uses. It is deliberately small: enough
to express phrases, transposition, stretching, muting, and reuse.
Instruments are declared as types but not yet interpreted.

### 2.1 Domain

- **Domain name:** `music`
- **Purpose:** Symbolic representation of pitched note sequences,
  phrases, and simple performance variation. Output is a flat list of
  note events in global time, suitable for later consumption by an
  audio dialect, a tracker, or a notation renderer.
- **Status:** Draft v0.2.

### 2.2 Type ids

```text
Type id:    music.note
Required:   pitch: symbol   (e.g. C3, D#4, Bb2)
Optional:   velocity: float = 1.0
            duration: float = 1.0     (local-time units)
Notes:      A single pitched event. Pitch uses scientific notation:
            <letter>[#|b]<octave>. C4 = middle C.

Type id:    music.rest
Required:   (none)
Optional:   duration: float = 1.0
Notes:      A timed silence. Mostly used to fill positions in a phrase
            after a mute override removes a note.

Type id:    music.phrase
Required:   notes: vector
Optional:   step: float = 1.0          (spacing between successive notes)
            swing: float = 0.0          (deferred — declared, not yet used)
Notes:      A sequence of notes spaced by `step` local-time units. The
            `notes` vector contains pitch symbols; each becomes a
            music.note with duration = step. For Prototype A this is
            sufficient. Real scores will eventually want explicit
            note durations per element.

Type id:    music.instrument
Required:   (none in v0.2)
Optional:   timbre: symbol = "default"
Notes:      Placeholder. The v0.2 expander records the LNK but does
            not synthesize. An audio dialect will eventually consume
            note events routed through this type.
```

### 2.3 Ports

```text
music.note:        Inputs: (none)              Outputs: out (note event)
music.rest:        Inputs: (none)              Outputs: out (rest event)
music.phrase:      Inputs: (none)              Outputs: out (event stream)
music.instrument:  Inputs: in (event stream)   Outputs: out (deferred)
```

### 2.4 Operators

```text
Operator: transpose
Args:     signed int (semitones)
Applies:  music.note, music.phrase
Effect:   Shifts every pitch by N semitones. Rests pass through unchanged.
Composes: with stretch (independent axes); transposes stack additively
          (transpose +7 then transpose -12 == transpose -5).

Operator: stretch
Args:     positive float
Applies:  music.phrase, music.note
Effect:   Multiplies durations and `step` by the factor. stretch 0.5
          halves all timings.
Composes: with transpose (independent); stretches stack multiplicatively
          (stretch 0.5 then stretch 2.0 == identity).

Operator: mute
Args:     vector of int indices (0-based)
Applies:  music.phrase
Effect:   Replaces the notes at the given indices with rests of equal
          duration. Indices out of range are ignored with a warning.
Composes: with transpose and stretch; mute indices refer to the phrase's
          original index order regardless of stacking.
```

### 2.5 Override keys

Same as operators (`transpose`, `stretch`, `mute`), plus:

```text
Override: gain
Args:     float
Applies:  any music type (passes through to event metadata)
Effect:   Multiplies velocity on emitted events. Instance-only; not a
          MOD operator because "the same phrase but quieter" rarely
          deserves its own name.
```

### 2.6 Time interpretation

- **Time-positioned types:** `music.note`, `music.rest`, `music.phrase`,
  nested GRPs containing music types.
- **Non-time-positioned types:** `music.instrument` (it is a routing
  target, not an event).
- **Positioning mode:** **sequential**. A USE inside a music GRP without
  an explicit `at` starts where the previous USE ended. This matches
  how scores are read and keeps per-note byte cost minimal. Authors
  override with explicit `at` only when desynchronization is wanted
  (grace notes, anticipations).
- **Stretching behavior:** when a USE's `dur` differs from the group's
  local duration, all contained note start times and durations scale
  linearly by `dur / local_dur`.
- **Default local duration:** for a `music.phrase`, local_dur =
  `len(notes) * step` after any stretch operator. For a GRP containing
  music statements, local_dur = max end-time of contents (after
  sequential positioning resolves implicit `at` values).

### 2.7 Interpreter notes

- **Implementation:** Python 3, in `tools/spine/expand.py` (Prototype A
  tool).
- **Output:** a flat list of dicts `{t: global_time, type:
  "note"|"rest", pitch: str, dur: float, velocity: float}`,
  serialized to `phrase_motif.expanded.txt` for diffing.
- **Dependencies:** none. Music is the seed dialect.
- **Known limitations:**
  - No per-note duration in `music.phrase` — all notes are `step` long.
  - No swing yet (declared but unimplemented).
  - No instrument synthesis — LNK to `music.instrument` is recorded but
    not acted on.
  - No chords — a phrase is monophonic. Polyphony arrives by USEing
    multiple phrases in parallel.

### 2.8 Open questions

1. Should `music.phrase` accept a parallel `durations` vector for
   per-note duration override?
2. How should `transpose` interact with scale-aware operations
   (e.g. "transpose within key of D minor")? Currently chromatic only.
3. Should `mute` accept a slice syntax (`mute=[2..5]`) or stay
   index-list-only?
4. When does `music.chord` become a type vs. just "USE three notes at
   the same time"?
5. Velocity: 0..1 float or 0..127 MIDI int? v0.2 picks float; revisit
   if the audio dialect prefers MIDI.

---

## 3. Worked example: the `cello` dialect (v0.3 sketch)

The cello dialect is the v0.3 worked example for gesture composition,
seed inheritance, sparse continuous modifiers, and gesture transitions.
It is deliberately a **sketch**: enough types and operators to write
two example phrases (one legato, one martélé→legato) and exercise all
the v0.3 design surface, but not a complete instrument. The real
instrument-side specification (synthesis math, gesture trajectory
templates in the wavelet basis, operator-matrix recipes) lives in a
separate cello-dialect chat.

### 3.1 Domain

- **Domain name:** `cello`
- **Purpose:** Gesture-level notation for cello performance. The score
  notates *which gesture, when, on what pitch, with what sparse
  deviations*. Trajectory templates, synthesis, and the wavelet basis
  live instrument-side and are out of scope here.
- **Status:** Draft v0.3 sketch. Real specification lives elsewhere.

### 3.2 Type ids

```text
Type id:    cello.gesture.détaché
            cello.gesture.martelé
            cello.gesture.legato
            cello.gesture.vibrato_warm
            cello.gesture.vibrato_narrow
            cello.gesture.sul_tasto
            cello.gesture.pizzicato

Required:   (none — gestures are atomic; defaults come from the
            instrument-side trajectory template)

Optional:   None at this level. Variants are produced via MOD.

Notes:      Each gesture references an instrument-side trajectory
            template (bow_force, bow_velocity, contact_point,
            vibrato_rate, vibrato_depth, finger_pressure, ...). The
            score never sees the trajectory; it just names the gesture.

Type id:    cello.note
Required:   pitch: symbol      (scientific notation)
            gesture: reference (to a cello.gesture.* entity)
Optional:   transition_from: reference (to the previous gesture)
            duration: float (local-time units; comes from USE `dur`)
Notes:      Represents one bow stroke / one performance event with a
            named gesture. Distinct from music.note because it carries
            a gesture binding.

Type id:    cello.curve.standard
Required:   shape: symbol (rise, fall, hold, swell_then_settle, ...)
            args: vector of floats
Notes:      Standard library curve referenced via ref() for sparse
            modifier values. Instrument-side maps shape+args to actual
            wavelet-basis coefficients.
```

### 3.3 Ports

Gestures and notes have no SPINE-visible ports in v0.3. Connection
between music events and the cello instrument happens at the
`audio.instrument.cello` level (audio dialect), not here. Curves are
value-shape outputs only when referenced as modifier values.

```text
cello.gesture.*:        Inputs: (none)   Outputs: (none in v0.3)
cello.note:             Inputs: (none)   Outputs: out (event)
cello.curve.standard:   Inputs: (none)   Outputs: out (value, curve-shaped)
```

### 3.4 Operators

```text
Operator:  with_pressure   Arity: 2 (verb + arg pair)
Args:      Verb form: `rise <a> <b>`, `fall <a> <b>`, `hold <v>`
           Reference form: `ref(<curve_entity>)`
Applies:   cello.gesture.*
Effect:    Attaches a bow_pressure curve to the gesture's trajectory.
Composes:  with most other gesture operators independently.

Operator:  with_depth      Arity: 2 (verb + arg pair)
Args:      Verb form: `rise <a> <b>`, `fall <a> <b>`,
                      `grow <a> <b>`
           Reference form: `ref(<curve_entity>)`
Applies:   cello.gesture.vibrato_*
Effect:    Attaches a vibrato_depth curve.
Composes:  with decelerando, humanize.

Operator:  decelerando     Arity: 1
Args:      float in [0.0, 1.0] — final-tempo ratio
Applies:   cello.gesture.vibrato_*
Effect:    Slows vibrato rate toward the end of the gesture.
Composes:  with with_depth, humanize.

Operator:  accelerando     Arity: 1
Args:      float — final-tempo ratio (typically > 1.0)
Applies:   cello.gesture.vibrato_*
Effect:    Speeds vibrato rate toward the end.
Composes:  with with_depth, humanize.

Operator:  slur_from_prev  Arity: 0
Args:      (none — flag-style)
Applies:   cello.gesture.legato, cello.gesture.détaché
Effect:    Marks the gesture as bow-continuous from the previous note.
           Instrument-side renders no re-articulation.
Composes:  with with_pressure, humanize.

Operator:  with_attack     Arity: 2 (verb + arg pair)
Args:      Verb form: `sharper <degree>`, `softer <degree>`
Applies:   cello.gesture.martelé, cello.gesture.détaché
Effect:    Modifies the attack transient shape.
Composes:  with with_pressure, humanize.

Operator:  humanize        Arity: 1 or 2
Args:      float (jitter amount, ~0.0-0.1)
           Optional: `seed <int>` follows the float for explicit seed.
Applies:   any cello.gesture.*
Effect:    Adds seeded jitter to all trajectory parameters. Without
           explicit seed, derives from inherited GRP seed.
Composes:  with everything (typically last in the chain).
```

### 3.5 Override keys

```text
Override:  gesture
Args:      reference (to a cello.gesture.* entity, possibly MOD-derived)
Applies:   cello.note USE
Effect:    Binds this note to a specific gesture variant.

Override:  transition_from
Args:      reference (to the previous note's gesture variant)
Applies:   cello.note USE
Effect:    Marks an explicit gesture handoff. Instrument resolves via
           the transition table in §3.8.

Override:  seed
Args:      int
Applies:   any USE of a humanize-bearing entity
Effect:    Overrides inherited seed for this USE only.
```

### 3.6 Time interpretation

- **Time-positioned types:** `cello.note`, GRPs containing cello.notes.
- **Non-time-positioned types:** `cello.gesture.*`, `cello.curve.*` —
  these are definitions, not events.
- **Positioning mode:** sequential (same as music dialect; notes follow
  the previous note's end unless explicit `at` is given).
- **Stretching behavior:** when a USE's `dur` differs from local
  duration, all note timings scale linearly. Gesture trajectory shapes
  rescale too (a vibrato that "rises over first half" rises over the
  scaled first half).
- **Default local duration:** sum of note durations in sequential mode.

### 3.7 Lifetime

- `cello.gesture.*` — **precomputed.** Trajectory templates load once
  at build time. Score variants (MOD chains) also resolve at build
  time, except for the humanize-rolled portion (resolved offline per
  seed §4.5 of the main design doc).
- `cello.note` — **event-driven.** Emits one performance event when
  scheduled; the event carries the gesture binding.
- `cello.curve.standard` — **precomputed.** Standard-library curve
  shapes are deterministic.

### 3.8 Transition table

```text
from_gesture                      to_gesture            resolver
cello.gesture.legato              cello.gesture.legato  continue_bow
cello.gesture.détaché             cello.gesture.legato  continue_bow
cello.gesture.legato              cello.gesture.détaché continue_bow

cello.gesture.martelé             cello.gesture.legato  lift_and_settle
cello.gesture.martelé             cello.gesture.détaché lift_and_settle

cello.gesture.legato              cello.gesture.martelé reattack
cello.gesture.détaché             cello.gesture.martelé reattack

cello.gesture.*                   cello.gesture.pizzicato pluck_attack
cello.gesture.pizzicato           cello.gesture.*       bow_recover

(default)                         (any)                 brief_silence
```

Most transitions can resolve offline. `lift_and_settle` after a
humanized martélé needs to know the bow's perturbed position at the
moment of release; that resolver flag's runtime_state_needed = true.
See `spine_runtime_model.md` §9.6.

### 3.9 Interpreter notes

- **Implementation:** Python sketch in `tools/spine/src/expand.py`
  (Prototype D). Validates parse, resolves MOD chains, captures
  transition markers, propagates seeds through reachability.
- **Output:** A *resolved phrase dump* — flat per-note records with
  resolved gesture variant id, transition_from id, effective seed
  (stubbed in v0.3), and any sparse-curve references.
- **No audio.** Synthesis is out of scope; that work lives in the
  cello-dialect chat plus eventual softsynth.
- **Dependencies:** none in Prototype D. Eventually `audio` dialect
  for instrument-level integration.
- **Known limitations:**
  - Effective seed values are recorded as `(parent_seed, entity_id,
    instance_counter)` tuples rather than hashed integers. Real
    hashing is scheduled for the first audio-producing prototype.
  - Verb-form curve resolution is a stub: the dialect records what
    curve verb+args was used, but does not yet materialize the
    wavelet coefficients.
  - Transition table is a static lookup; no contextual logic.

### 3.10 Open questions

1. Should `legato` be a base gesture or a transformation? Currently
   listed as a base; in some performance contexts it's clearer as
   `détaché slur_from_prev`. Possibly redundant.
2. How should chord notation work? Two notes USE'd simultaneously?
   A `cello.chord` type? Deferred until first multi-stop phrase.
3. Where do bowings (down-bow / up-bow) live? Probably as a
   transformation operator (`down_bow`, `up_bow`), but real cellists
   may want explicit notation. Deferred.
4. How does `decelerando` compose with `accelerando`? Currently
   left-to-right last-wins; might want a different policy. Open.
5. The transition table grows combinatorially with gesture count.
   At what size does it need a different representation (default rules
   + exceptions)?

---

## 4. Future dialects (placeholders)

Listed here so the namespace is reserved and so future-you remembers
which corners of the design are claimed:

- **`audio`** — instruments, resonators, exciters, effects, signal flow.
  Consumes events from `music` and `cello`.
- **`wavelet`** — coefficient-space envelopes, splines, fields, IRs.
  Provides control signals to `audio`, `cello`, and `motion`.
- **`patch`** — generic node/port/connection patchbays (already exists,
  used in Prototypes B and C).
- **`graphics`** — shaders, geometry atoms, cameras, render events.
- **`motion`** — gait, gesture, cloth, body motion motifs.
- **`text`** — UTF-8 strings, layout, glyph masks, text-as-visual.
- **`scene`** — top-level scene structure, story beats, scene
  transitions. May be a thin coordinator rather than a real dialect.

Each will get its own filled template before its first prototype.

---

## 5. The dialect interpreter contract

Every dialect interpreter, regardless of language, presents the same
shape to SPINE core:

```text
on_def(id, type_id, params)         -> register entity
on_use(entity_id, ctx, overrides)   -> instantiate in context
on_set(target, param, value)        -> assign
on_mod(new_id, src_id, ops)         -> derive variant
on_lnk(src_port, dst_port)          -> record connection
on_grp_enter(id) / on_grp_exit()    -> scope boundaries
finalize()                          -> emit domain output
```

Dialects share neither runtime state nor type ids. A SPINE document
may use multiple dialects; the host walks the event stream once and
dispatches each event to the dialect named by its type id's prefix.

Cross-dialect LNK (e.g. `music.phrase.out -> audio.instrument.in`) is
the host's responsibility to deliver. The dialects on each end need
only agree on the *shape* of what flows across the port. For Prototype
A this is moot — only `music` exists.

---

## 6. One-page reminder

A dialect declares:

```text
Types       (what entities exist)
Ports       (where LNK can connect)
Operators   (what MOD can do)
Overrides   (what USE can tweak)
Time        (how local time works)
Interpreter (the code that runs)
```

SPINE core records structure. Dialects give it meaning. Keep dialects
small individually; let the library of them grow.
