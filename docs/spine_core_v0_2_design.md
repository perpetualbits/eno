# SPINE Core v0.2

**STATUS: SUPERSEDED by `spine_core_v0_3_design.md`.**

This document is kept for historical reference. v0.3 is strictly
additive: every concept here remains valid, but the canonical
specification is now v0.3. Read v0.3 for current work.

---

**Working design document**
Project: Epsilon Null Operation (ε₀)
Status: v0.2 draft — supersedes v0.1 and its appendix
Companions: `spine_dialect_template.md`, `spine_open_questions.md`
Purpose: define the smallest useful SPINE core, with the load-bearing
decisions pinned down, before Prototype A.

---

## 0. Re-entry summary

SPINE is the symbolic backbone of Epsilon Null Operation. It describes
and compresses everything a demo is made of: scores, patches, envelopes,
gestures, scenes, motifs, shaders, text events, motion, echo fields.

SPINE itself knows nothing about cellos, caves, fractals, robes, or
cameras. It knows six operations:

```text
DEF   define a reusable entity
USE   place an entity in context (with optional per-use overrides)
SET   assign a parameter
MOD   derive a new named entity from an existing one
LNK   connect one endpoint to another
GRP   group entities into a reusable scope
```

Everything else is a **domain dialect** layered on top.

The central principle: **structural compression before entropy coding**.
Meaning is reused before bytes are compressed.

v0.2 differs from v0.1 in four pinned decisions (chapter 4), a cleaner
MOD/USE split, an explicit dialect template, and the deliberate removal
of premature binary/grammar/interpreter sketches. Those return after
Prototype A produces evidence.

---

## 1. Problem statement

Epsilon Null Operation will accumulate hundreds of reusable things:
wavelet kernels, instrument bodies, patch nodes, gesture motifs, shader
helpers, animation cycles, text routines, echo fields, geometry atoms.

A given demo uses only a fraction of these. The hard problem is not
storing the library — it is **describing relationships** between the
parts in a way that is:

- strictly defined
- recursively reusable
- domain-neutral at the core
- domain-rich at the edges
- friendly to entropy coding
- friendly to a tiny RISC-V runtime

The temptation is a giant ontology. SPINE rejects that route. The core
stays small. Dialects grow.

---

## 2. Mental model

Three layers:

```text
+---------------------------------------------------+
| Domain dialects                                   |
| audio, music, wavelet, graphics, patch, motion... |
+---------------------------------------------------+
| SPINE core operations                             |
| DEF USE SET MOD LNK GRP                           |
+---------------------------------------------------+
| Compact binary / log representation               |
| tokens, IDs, deltas, references, entropy coding   |
+---------------------------------------------------+
```

The core records *structure*. The dialect interprets *meaning*. The
binary layer makes it *small*.

This mirrors the SMOLR/smold split one layer down: the same atom
discipline applies, just for symbols and events rather than for
instructions and bytes.

---

## 3. The six core operations

### 3.1 DEF — define a reusable entity

```text
DEF <id> : <domain.type> { params }
```

```text
DEF cello_body_0 : audio.resonator.cello { brightness=0.54 }
DEF bow_env_0    : wavelet.spline.env    { basis=cdf53 }
DEF arpeggio_0   : music.phrase          { notes=[C3,E3,G3,C4] step=0.25 }
```

A DEF registers a named entity. It does not schedule anything. It is
available for later USE, SET, MOD, LNK, GRP.

**v0.2 commitment:** DEF is non-destructive. A definition, once made, is
immutable from SPINE's perspective. Later operations may *derive* new
entities but never mutate existing ones.

### 3.2 USE — place an entity in context

```text
USE <id> [at <time>] [dur <duration>] [loc <location>] { overrides }
```

```text
USE arpeggio_0 at 0.0 dur 2.0
USE arpeggio_0 at 2.0 dur 2.0 transpose=+7
USE arpeggio_0 at 4.0 dur 1.0 transpose=+7 mute=[2]
USE walk_0     at 0.0 dur 32.0 loc=actor.old_man
```

USE creates an *instance* of an entity in a context. Each USE produces
an implicit instance — see §4.2.

**Overrides** (the parameter block on USE) apply only to this instance.
They never affect the definition or other uses. This is the ephemeral
case in §4.1: lightweight per-use variation that is not worth naming.

### 3.3 SET — assign a parameter

```text
SET <target>.<parameter> = <value>
```

```text
SET cello_body_0.size = 1.0
SET palette_0.stops   = [#000, #f80, #fff]
```

SET assigns a value to an entity, instance, port, or group. Values may
be numbers, references, vectors, blobs, or symbols. The accepted value
types for v0.2 are listed in §4.4.

SET on a definition applies before any USE sees it. SET on an instance
(by instance id) applies only to that instance.

### 3.4 MOD — derive a new named entity

```text
MOD <new_id> = <source_id> <operator> <args> [<operator> <args> ...]
```

```text
MOD arpeggio_t7    = arpeggio_0 transpose +7
MOD arpeggio_t7_s2 = arpeggio_t7 stretch 0.5
MOD building_5fl   = building_0 set floors=5
MOD walk_mirrored  = walk_0 mirror left_right
```

MOD always produces a **new named entity** derived from a source. The
source is untouched. The derived entity is first-class: it can be USEd,
MODded again, LNKed, included in reachability analysis, rolled up.

**v0.2 commitment:** MOD is never anonymous, never destructive, never
attached to a "next USE." If you want per-use variation, use USE
overrides (§3.2). If you want a reusable variant, use MOD.

The available **operators** (transpose, stretch, mirror, set, damp,
mute, …) are defined by domain dialects, not by SPINE core. Core only
records `MOD id = src op args`.

Operator stacking applies left-to-right: in `MOD x2 = x1 transpose +7
stretch 0.5`, the transpose runs first, then the stretch.

### 3.5 LNK — connect output to input

```text
LNK <source.port> -> <destination.port>
```

```text
LNK bow_env_0.out      -> cello_body_0.bow_pressure
LNK mandel_0.out       -> robe_0.texture
LNK palette_0.out      -> mandel_0.palette
LNK time.beat          -> palette_0.phase
LNK cello_phrase.note_on -> flash_env.trigger     # event-driven
LNK flash_env.out        -> palette_robe.brightness
```

LNK records a connection between endpoints. SPINE does not know what
"output" means; that is the dialect's job. The connection may carry a
continuous signal, a value, an event stream, a modulation, a texture,
or any other shape the two endpoints agree on. **Event-stream ports are
first class:** a port may emit discrete events (`note_on`, `trigger`,
`tick`) just as naturally as a continuous signal, and LNK is how
cross-domain synchronization is expressed — a graphical flash driven by
a musical note-on event is wired, not separately scheduled. Synchronized
events are *caused by* their trigger, not scheduled alongside it, which
makes them sample-accurate by construction and impossible to drift.

LNK is the mechanism for cross-domain wiring (e.g. Example 3 from the
design discussion: a fractal generator's output feeding a cloth
material's texture input). It is *not* a MOD case.

**Multi-source inputs are legal.** A port may receive multiple
incoming LNKs. The dialect interpreter decides how to combine them:
signal/value-shape ports sum the sources, event-shape ports OR them
(any source firing fires the destination). The mixer's `inN` ports
have distinct names by convention because they want individually
addressable connections; a delay's `in` port is genuinely single-
named but may have multiple sources (e.g. main signal plus feedback)
that sum naturally. Surfaced by Prototype C; see
`tools/spine/docs/PROTOTYPE_C.md`.

### 3.6 GRP — group into a reusable scope

```text
GRP <id> { statements }
```

```text
GRP phrase_0 {
  USE note_C3 at 0.0 dur 0.5
  USE note_E3 at 0.5 dur 0.5
  USE note_G3 at 1.0 dur 1.0
}

USE phrase_0 at bar 8
MOD phrase_t12 = phrase_0 transpose +12
USE phrase_t12 at bar 12
```

GRP creates a named scope. Groups have **local time** (see §4.3) and
local coordinate context. A group can contain DEF, USE, SET, MOD, LNK,
and nested GRP statements.

A group is itself an entity: it can be USEd, MODded, LNKed, referenced.

---

## 4. The four pinned decisions

These are the load-bearing semantic choices for v0.2. The v0.1 + appendix
left them ambiguous. Prototype A cannot be written without them.

### 4.1 MOD scope and the USE-override / MOD split

**Decision:** SPINE has *two* variation mechanisms, used for different
intents:

| Mechanism      | Scope                | Names a new entity? | When to use                        |
|----------------|----------------------|---------------------|------------------------------------|
| USE overrides  | This use only        | No                  | One-off tweak, not worth naming    |
| MOD            | Creates new entity   | Yes (mandatory)     | Reusable variant, may be MODded again |

**Rationale.** The natural workflow is: you make a quick tweak, then
later realize you want it twice more, then promote it. The notation
should follow that workflow. Authors do not have to decide "is this
worth a name?" up front.

**Equivalence.** A USE override is semantically equivalent to an
anonymous single-use MOD. The runtime may implement it that way, but
authors do not write it that way.

**Promotion is a one-line edit.** Going from:

```text
USE arpeggio_0 at bar 4 transpose=+7
USE arpeggio_0 at bar 8 transpose=+7
```

to:

```text
MOD arpeggio_t7 = arpeggio_0 transpose +7
USE arpeggio_t7 at bar 4
USE arpeggio_t7 at bar 8
```

is what the offline roll-up tool will do automatically (§6). Hand
authors can do it themselves when convenient.

**Override compatibility.** Override keys overlap with MOD operators
(transpose, stretch, mute, etc.) by design. A dialect that supports
`transpose` as a MOD operator supports it as a USE override too, with
identical semantics.

### 4.2 Instance identity

**Decision:** every USE produces an implicit instance with an
auto-assigned id (`<entity_id>#<counter>` is fine for v0.2). Instances
are referable by id for later SET targeting:

```text
USE arpeggio_0 at bar 4              # produces arpeggio_0#0
USE arpeggio_0 at bar 8              # produces arpeggio_0#1
SET arpeggio_0#1.gain = 0.7          # only affects the second use
```

Explicit ids are also allowed for clarity:

```text
USE arpeggio_0 as quiet_one at bar 8
SET quiet_one.gain = 0.7
```

**Rationale.** Without instance identity, "modify just this one
appearance" requires either duplicating the entity or polluting it with
context. Both are worse than a one-byte counter.

**Implementation note.** In the binary form, implicit ids may be elided
when never referenced. The roll-up pass can drop unused id slots.

### 4.3 Time model

**Decision:** every GRP defines a **local time domain**. A USE of a
group maps that local domain to global time via two parameters: start
(`at`) and duration (`dur`).

For groups whose contents are *time-positioned* (notes, animation
frames, scheduled events), the mapping is linear:

```text
local_t in [0, local_dur]  ->  global_t in [at, at + dur]
scale = dur / local_dur
```

For groups whose contents are *not time-positioned* (a patchbay, a
material definition, a static scene), `dur` is meaningful only if the
dialect uses it. Patches don't stretch; that is fine.

**Two ways to position USEs inside a time-positioned GRP:**

```text
GRP melody {                   # sequential mode (default for music-like)
  USE note_C3                  # implicit at = 0.0
  USE note_E3                  # implicit at = previous end
  USE note_G3 dur 2.0          # implicit at = previous end, twice as long
}

GRP scene {                    # positioned mode
  USE crash      at 4.2
  USE flash      at 4.2        # simultaneous events have the same `at`
  USE camera_cut at 4.25
}
```

A USE without `at` starts where the previous USE in the same GRP
ended. A USE with explicit `at` starts at that local time and resets
the "previous end" cursor to its own end. This means a score that
follows the beat costs one entity reference per note rather than one
timestamp per note, which is the byte-economy the music dialect needs.

Choice of mode is by convention per dialect rather than a syntactic
keyword: the music dialect treats unspecified `at` as sequential; the
graphics/scene dialect treats unspecified `at` as 0.0 (positioned). A
GRP may freely mix both styles — explicit `at` always wins.

**v0.2 limitation.** The time model is linear scaling only. Non-linear
time (curves, loops, phase-locking, event-driven timing) is deferred —
see `spine_open_questions.md`. Note that event-driven *synchronization*
is already possible via LNK on event-stream ports (§3.5); only
event-driven *time mapping* is deferred.

**Local duration default.** If a GRP does not declare its local
duration, it is the max end-time of its contents. A USE may override
the mapping by specifying `dur` differently from the natural local
duration.

**Cross-domain note.** Audio and animation may want different mappings
of the same group. v0.2 does not solve this; the convention is that one
group is authored for one primary time interpretation, and other
domains follow. Multi-interpretation timing is a v0.3+ question.

### 4.4 Parameter value types for v0.2

**Decision:** the v0.2 interpreter accepts six value types. Anything
beyond these is deferred to a later version.

| Type      | Syntax                | Notes                                  |
|-----------|-----------------------|----------------------------------------|
| int       | `42`, `-7`            | 32-bit signed, plenty for v0.2         |
| float     | `0.72`, `-1.5e-3`     | 64-bit float; quantized later          |
| symbol    | `sine`, `sul_tasto`   | Bare identifier, dialect-defined enum  |
| reference | `ref(bow_env_0)`      | Points at another entity by id         |
| vector    | `[0.1, 0.2, 0.3]`     | Fixed-length array of int/float        |
| string    | `"hello world"`       | UTF-8; sparingly used                  |

**Explicitly deferred:** curves (parameterized envelopes that are not
just references to envelope entities), blobs (large coefficient
arrays), expressions (`a + b * 2`), and any computed values. These
matter, but Prototype A does not need them, and committing now risks
guessing wrong.

**Coefficient arrays.** A wavelet envelope's coefficient list is a
`vector` for v0.2. If a vector grows past, say, 64 elements, it
graduates to a blob in v0.3.

---

## 5. The dialect contract

SPINE core does not know what a cello is. A **dialect** does. To prevent
ad-hoc drift as dialects accumulate, each dialect is defined by a
one-page contract — see `spine_dialect_template.md` for the empty form.

A dialect declares:

- **Domain name** (`audio`, `music`, `motion`, `graphics`, …)
- **Type ids** — the entities the dialect understands (`audio.resonator.cello`)
- **Parameters** — for each type, the parameter names and value types
- **Ports** — for each type, the named input and output endpoints LNK can target
- **Operators** — the MOD operators the dialect supports (`transpose`, `mirror`, …)
- **Override keys** — which operators are also valid as USE overrides (usually all of them)
- **Time interpretation** — how the dialect uses local time on groups it produces

A dialect interpreter is a piece of code (initially Python, eventually
C/asm) that consumes the SPINE event stream and produces domain output:
audio samples, frame events, geometry, text.

**v0.2 starter dialect:** the `music` dialect, just enough to run
Prototype A. See the dialect template companion document.

---

## 6. Reachability and roll-up

### 6.1 Reachability

A final demo includes only definitions reachable from the demo root:

```text
GRP demo_root {
  USE scene_intro
  USE scene_desert
  USE scene_exit
}
```

Reachability walks: USE references, LNK endpoints, MOD sources, SET
targets, GRP contents.

Unreachable DEFs are dropped at link time. This is exactly the SMOLR /
`--gc-sections` philosophy applied to SPINE entities.

### 6.2 Roll-up: v0.2 scope

The roll-up pass detects repeated structure and replaces it with
DEF/MOD/USE references. **v0.2 commits to exact repetition only.**

Two patterns the v0.2 roll-up tool handles:

**Pattern A: identical override sequences.** When the same override is
applied to N≥2 uses of the same source, propose promotion to MOD:

```text
USE arpeggio_0 at bar 4 transpose=+7
USE arpeggio_0 at bar 8 transpose=+7
USE arpeggio_0 at bar 12 transpose=+7
```

becomes:

```text
MOD arpeggio_t7 = arpeggio_0 transpose +7
USE arpeggio_t7 at bar 4
USE arpeggio_t7 at bar 8
USE arpeggio_t7 at bar 12
```

**Pattern B: identical statement sequences inside groups.** When the
same sequence of N≥2 statements appears in K≥2 places, propose
extracting it as a sub-group.

**Explicitly deferred:** near-repetition (same structure with different
parameters), structural similarity, content-similar but not identical.
These compress music and motion best, but are a much harder algorithm
and need to wait until exact-repetition rolling has measurable value.
See `spine_open_questions.md`.

### 6.3 Roll-up is offline

The roll-up tool runs at authoring time, not at runtime. The runtime
sees only DEFs, USEs, MODs, SETs, LNKs, GRPs — already rolled up. Tiny
runtime, expensive offline.

---

## 7. Textual format v0.2

The v0.2 text format is the interpreter's input. It is human-readable,
line-oriented, and deliberately under-engineered.

```text
DEF id : domain.type { key=value key=value }
USE id [as instance_id] [at time] [dur duration] [loc location] { overrides }
SET target.param = value
MOD new_id = source_id operator args [operator args ...]
LNK source.port -> destination.port
GRP id { statements }
```

Whitespace and newlines are not significant except as separators.
Comments use `#` to end of line. Strings are double-quoted.

Example covering all six ops:

```text
# A small score fragment.

DEF arpeggio_0 : music.phrase {
  notes = [C3, E3, G3, C4]
  step  = 0.25
}

DEF cello_0 : audio.instrument.cello {
  brightness = 0.54
}

LNK arpeggio_0.out -> cello_0.in

MOD arpeggio_t7 = arpeggio_0 transpose +7

GRP scene_intro {
  USE arpeggio_0   at 0.0  dur 2.0
  USE arpeggio_t7  at 2.0  dur 2.0
  USE arpeggio_0   at 4.0  dur 1.0 mute=[2]
}

GRP demo_root {
  USE scene_intro at 0.0
}
```

**Grammar.** A formal grammar is deferred. The Prototype A expander
parses by hand — regex plus a tiny line tokenizer. When the format
stabilizes after Prototype A and B, the grammar gets written down.

---

## 8. Prototype A

### 8.1 Scope

A single hand-authored `.spine` file describing a musical motif: a
phrase, reused several times, with MOD variants and USE overrides,
nested inside a scene group. Plus a Python tool that expands it to a
flat global-time event list.

### 8.2 Deliverables

| File                                       | Role                                  |
|--------------------------------------------|---------------------------------------|
| `examples/phrase_motif.spine`              | Hand-authored input                   |
| `tools/spine/expand.py`                    | Toy expander                          |
| `examples/phrase_motif.expanded.txt`       | Flat global-time event dump           |
| `examples/phrase_motif_flat.spine`         | The same demo, hand-written flat      |
| `examples/SIZE_COMPARISON.md`              | Byte counts: rolled vs flat           |

### 8.3 What Prototype A must exercise

- DEF of at least three entities
- GRP with at least one nested GRP
- USE with `at` and `dur` (positioned mode)
- USE with implicit timing (sequential mode, music dialect)
- USE with overrides (at least `transpose` and `mute`)
- MOD producing a named variant
- MOD operator stacking (one example, e.g. `transpose +7 stretch 0.5`)
- Reachability: include at least one DEF that is *not* reachable from
  `demo_root`, and verify the expander drops it
- A flat vs rolled byte-count comparison that shows structural
  compression is doing something

### 8.4 What Prototype A explicitly does not need

- LNK resolution beyond recording the connection (no signal flow yet)
- SET on instances (use overrides instead)
- Any audio, graphics, or rendering output
- A formal grammar or parser-generator
- A binary format
- Near-repetition roll-up

### 8.5 The music dialect for Prototype A

Just enough to make the expander meaningful. Defined in
`spine_dialect_template.md`. Notes, phrases, transpose, stretch, mute,
gain. No instruments yet (instrument as a type is declared but the
expander ignores it).

### 8.6 Success criterion

The expanded flat event list is identical when produced from the
rolled-up `.spine` and from the hand-written flat `.spine`. And the
rolled-up version is meaningfully smaller in bytes than the flat one.

That second part is the v0.2 equivalent of SMOLR's "make `wc -c` look
confused." If we cannot demonstrate that structural compression saves
bytes at this scale, the entire premise is wrong and we should know
before building more.

---

## 9. What is deferred and why

| Topic                       | Why deferred                              | Re-open after                  |
|-----------------------------|-------------------------------------------|--------------------------------|
| Binary format               | Text format will change; binary follows   | Prototype A + B                |
| Formal grammar (EBNF)       | Same                                      | Prototype A + B                |
| C interpreter struct        | MOD semantics just changed; would rewrite | Prototype A                    |
| Near-repetition roll-up     | Hard; needs evidence of value             | Exact-repetition measured win  |
| Curves as a value type      | Refs to envelope entities cover Prototype A | First wavelet-using prototype |
| Blob payloads               | Vectors suffice up to ~64 elements        | First real coefficient array   |
| Non-linear time             | Linear is enough for music                | First motion or motif phasing  |
| Multi-domain time           | One time per group is enough              | Cross-domain demo              |
| Streaming evaluation        | Whole-program load is fine for demos      | Procedural / generative demo   |
| Probabilistic operators     | Need seeded determinism first             | After seed model lands         |
| Type checking in dialects   | Trust authors for now                     | After dialects accumulate      |

Everything in this table has a placeholder entry in
`spine_open_questions.md`.

---

## 10. Glossary

**Entity** — A reusable defined thing, created with DEF or MOD.

**Instance** — A scheduled or contextual appearance of an entity,
created by USE.

**Override** — A per-use parameter on USE that affects only that
instance.

**Variant** — A named derived entity created with MOD.

**Group** — A reusable scope with local time, created with GRP.

**Dialect** — A domain-specific vocabulary (types, ports, operators)
layered on SPINE core.

**Operator** — A transformation name passed to MOD or used as an
override key. Defined by dialects.

**Port** — A named endpoint on an entity, targetable by LNK.

**Roll-up** — Offline pass that detects repetition and replaces it with
DEF/MOD/USE references.

**Reachability** — Inclusion of definitions reachable from the demo
root through USE, MOD, LNK, SET, or GRP.

**Local time** — Time inside a group, mapped to global time by USE.

---

## 11. One-page reminder

SPINE is six operations:

```text
DEF   define a reusable entity            non-destructive
USE   place in context with overrides     instance-scoped overrides
SET   assign a parameter                  static or per-instance
MOD   derive a new named variant          always named, never destructive
LNK   connect endpoints                   dataflow, cross-domain wiring
GRP   group with local time               reusable scope
```

Two variation mechanisms:

- **USE overrides** for ephemeral tweaks.
- **MOD** for variants worth naming. Roll-up promotes overrides to MOD
  when warranted.

Three layers: core / dialect / binary.

One principle: structural compression before entropy coding.

Library may explode. Core stays small. Reachability prunes. Roll-up
folds. Entropy coding comes last.

That is SPINE.
