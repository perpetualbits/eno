# SPINE Dialect Template

**Companion to:** `spine_core_v0_2_design.md`
Project: Epsilon Null Operation (ε₀)
Status: v0.2 — empty template + one worked example (`music`)

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
- **Argument shape:** e.g. `+N`, `vector`, `bool`
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

### 1.8 Interpreter notes

- **Implementation:** language, location in repo.
- **Output:** what the interpreter produces (events, samples, frames,
  text, geometry).
- **Dependencies on other dialects:** if any.
- **Known limitations / TODO.**

### 1.9 Open questions

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

## 3. Future dialects (placeholders)

Listed here so the namespace is reserved and so future-you remembers
which corners of the design are claimed:

- **`audio`** — instruments, resonators, exciters, effects, signal flow.
  Consumes events from `music`.
- **`wavelet`** — coefficient-space envelopes, splines, fields, IRs.
  Provides control signals to `audio` and `motion`.
- **`patch`** — generic node/port/connection patchbays. May subsume
  parts of `audio` once it stabilizes.
- **`graphics`** — shaders, geometry atoms, cameras, render events.
- **`motion`** — gait, gesture, cloth, body motion motifs.
- **`text`** — UTF-8 strings, layout, glyph masks, text-as-visual.
- **`scene`** — top-level scene structure, story beats, scene
  transitions. May be a thin coordinator rather than a real dialect.

Each will get its own filled template before its first prototype.

---

## 4. The dialect interpreter contract

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

## 5. One-page reminder

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
