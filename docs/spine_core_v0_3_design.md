# SPINE Core v0.3

**Working design document**
Project: Epsilon Null Operation (ε₀)
Status: v0.3 draft — supersedes v0.2
Companions: `spine_dialect_template.md`, `spine_open_questions.md`,
`spine_runtime_model.md`
Purpose: extend v0.2 with gesture composition, three-level seed
inheritance, sparse continuous modifiers, and gesture transitions, as
required by the cello-dialect work.

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

v0.3 keeps the six-op core unchanged. It extends v0.2 with:

- **Gesture composition** (§4.5) — composable MOD operator stacking with
  mixed arities, validated by the cello-dialect work
- **Three-level seed inheritance** (§4.5) — score-level / MOD-level /
  USE-level seeds, propagated by hashing, resolved offline
- **Sparse continuous modifiers** (§3.4, §4.4) — verb-sugared curve
  references that desugar to entity references
- **Gesture transitions** (§3.2) — a `transition_from=` USE override that
  gives the receiving instrument the previous gesture's identity
- **Score-level seed syntax** (§3.6) — a new `seed=` attribute on GRP

v0.2 readers will recognize everything above as additive: no existing
syntax breaks, no existing prototype regresses. The dialect contract
(§5) tightens to require lifetime declaration, which v0.2 already
introduced informally through Prototype C.

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
USE <id> [as <instance_id>] [at <time>] [dur <duration>] [loc <location>] { overrides }
```

```text
USE arpeggio_0 at 0.0 dur 2.0
USE arpeggio_0 at 2.0 dur 2.0 transpose=+7
USE arpeggio_0 at 4.0 dur 1.0 transpose=+7 mute=[2]
USE walk_0     at 0.0 dur 32.0 loc=actor.old_man

# v0.3: gesture transitions on note USEs
USE note_D4 at bar 2 dur 2.0 gesture=legato_warm
                              transition_from=m_loudest
```

USE creates an *instance* of an entity in a context. Each USE produces
an implicit instance — see §4.2.

**Overrides** (the parameter block on USE) apply only to this instance.
They never affect the definition or other uses. This is the ephemeral
case in §4.1: lightweight per-use variation that is not worth naming.

**v0.3: `transition_from=`** is a USE override that gives the receiving
entity's dialect the *previous* USE's gesture identity, so the dialect
can negotiate the handoff (a bow change, an envelope crossfade, a
finger lift). SPINE just carries the marker — the dialect decides what
each (from, to) pair means. Slur becomes a special case:
`transition_from=prev_note` with the cello dialect resolving to
"continuous bow." Other transitions (martélé→legato, pizz→arco,
streaming-patch→silence) use the same notation. See §4.5 and the
cello-dialect chat for the worked examples.

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
MOD building_5fl   = building_0 set floors 5
MOD walk_mirrored  = walk_0 mirror left_right

# v0.3: gesture composition (cello dialect, see §4.5)
MOD warm_decel    = vibrato_warm decelerando 0.7 humanize 0.05
MOD pressure_rise = détaché with_pressure rise 0.0 0.3
MOD pressure_ref  = détaché with_pressure ref(swell_then_settle)
```

MOD always produces a **new named entity** derived from a source. The
source is untouched. The derived entity is first-class: it can be USEd,
MODded again, LNKed, included in reachability analysis, rolled up.

**Commitment from v0.2:** MOD is never anonymous, never destructive,
never attached to a "next USE." If you want per-use variation, use USE
overrides (§3.2). If you want a reusable variant, use MOD.

The available **operators** (transpose, stretch, mirror, set, damp,
mute, decelerando, humanize, with_pressure, …) are defined by domain
dialects, not by SPINE core. Core only records
`MOD id = src op args [op args ...]`.

Operator stacking applies left-to-right: in `MOD x2 = x1 transpose +7
stretch 0.5`, the transpose runs first, then the stretch. This is the
load-bearing mechanism for **gesture composition** (§4.5): every
gesture variant is a MOD chain of base-gesture + transformations.

**v0.3: operator arity is mixed.** Some operators take one argument
(`transpose +7`), some take two (`set cutoff 2400`, from v0.2's patch
dialect), some take a *verb form* with a small numeric tail
(`with_pressure rise 0.0 0.3`). The parser uses a small arity table
(see `_MOD_OP_ARITY` in `expand.py`) populated by dialects. Verb-form
arguments are themselves dialect-defined sugar that desugars to
references to standard curve entities (§4.4).

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
GRP <id> [seed <N>] { statements }
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

# v0.3: a scene-level seed propagates to all humanize-bearing children
GRP scene_intro seed 2718 {
  USE cello_phrase_a at bar 1
  USE cello_phrase_b at bar 4
}
```

GRP creates a named scope. Groups have **local time** (see §4.3) and
local coordinate context. A group can contain DEF, USE, SET, MOD, LNK,
and nested GRP statements.

A group is itself an entity: it can be USEd, MODded, LNKed, referenced.

**v0.3: `seed <N>` attribute.** A GRP may carry an integer seed. The
seed propagates through reachability to descendant entities that
declare themselves seed-consuming (in v0.3, the humanize MOD operator).
A descendant may override by carrying its own seed. See §4.5 for the
three-level resolution model.

The seed attribute is grammar-level rather than a nested SET. This
is the first deliberate exception to "everything goes through the six
ops." The rationale: a seed is GRP-intrinsic, not a value SET on
something; it scopes naturally with the GRP's reachability boundary;
and it appears often enough in cello-grade scores that the syntactic
weight matters. Three plausible alternatives were considered (SET on
the GRP id, a dedicated meta-entity, equivalent grammar attribute);
the GRP attribute is the choice (recorded as such in
`spine_open_questions.md` §7.1 update).

---

## 4. Pinned decisions

These are the load-bearing semantic choices. §§4.1–4.4 were pinned in
v0.2 and remain unchanged. §4.5 is new in v0.3.

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

### 4.4 Parameter value types

**Decision:** the interpreter accepts seven value types in v0.3.
Anything beyond these is deferred.

| Type      | Syntax                | Notes                                  |
|-----------|-----------------------|----------------------------------------|
| int       | `42`, `-7`            | 32-bit signed                          |
| float     | `0.72`, `-1.5e-3`     | 64-bit float; quantized later          |
| symbol    | `sine`, `sul_tasto`   | Bare identifier, dialect-defined enum  |
| reference | `ref(bow_env_0)`      | Points at another entity by id         |
| vector    | `[0.1, 0.2, 0.3]`     | Fixed-length array of int/float        |
| string    | `"hello world"`       | UTF-8; sparingly used                  |
| curve     | verb + args, *or* `ref(curve_entity)` | v0.3 addition; see below      |

**The `curve` value type.** A curve is a sparse continuous trajectory
attached to a controller parameter. Two surface forms in v0.3, both
desugaring to the same underlying representation:

```text
# Canonical: reference to a named curve entity
MOD swell = vibrato_warm with_depth ref(swell_then_settle)

# Verb sugar: a small standard library of curve verbs
MOD swell = vibrato_warm with_depth rise 0.0 0.7
MOD fade  = vibrato_warm with_depth fall 0.3 0.0
MOD decel = vibrato_warm decelerando 0.7
```

The verb names (`rise`, `fall`, `decelerando`, `crescendo`, `hold`, …)
are dialect-defined and map to standard curve shapes. Each verb takes
a small fixed number of numeric arguments. The dialect's curve library
provides the actual shape data (the spiro/wavelet basis coefficients);
authors write verbs and never see the basis.

**Inline curve points** (e.g. `[(0.0, 0.0), (0.5, 0.7), (1.0, 0.3)]`)
are deferred to v0.4 pending authoring evidence that the canonical
and verb forms together aren't enough.

**Explicitly deferred:** blobs (large coefficient arrays), expressions
(`a + b * 2`), and any computed values. These matter, but no current
prototype needs them, and committing now risks guessing wrong.

**Coefficient arrays.** A wavelet envelope's coefficient list is a
`vector` for v0.3. If a vector grows past, say, 64 elements, it
graduates to a blob in v0.4.

### 4.5 Gesture composition and seed inheritance

**Surfaced by:** the cello-dialect chat. A real instrument cannot be
notated as discrete note events — a single bow stroke is a bundle of
continuous parameter trajectories (bow force, velocity, contact point,
vibrato rate/depth). The score notates *which gesture, when, on what
pitch, with what sparse deviations*; the instrument provides the
gesture trajectory templates and the synthesis machinery. This split
is analogous to font glyphs vs text: SPINE notates the text, the
dialect implements the glyphs.

**Decision: gestures are first-class entities and compose via MOD.**

A gesture is a typed entity (`cello.gesture.détaché`, etc.). A score
references gestures by name on note USEs (`gesture=détaché`). Score-
authored variants come from MOD operator stacking on a base gesture:

```text
# Base gestures (instrument-provided, not authored by score writer):
#   cello.gesture.détaché, cello.gesture.martelé,
#   cello.gesture.vibrato_warm, ...

# Score-side derived gestures:
MOD legato_arc      = détaché slur_from_prev
MOD legato_swell    = legato_arc with_pressure rise 0.0 0.3
MOD vib_swell       = vibrato_warm with_depth ref(swell_then_settle)
MOD vib_decel       = vibrato_warm decelerando 0.7
                                   with_depth fall 0.7 0.3
```

Each MOD produces a named entity that can be USEd, MODded further,
LNKed, included in reachability, and rolled up. The instrument
catalogue stays small (a few dozen base gestures plus a few dozen
transformations); scores compose richly from this vocabulary without
the catalogue exploding.

**Decision: humanization is a MOD operator that takes a seed.**

Real performance is not deterministic to the sub-millisecond level.
Cellists vary attack timing, vibrato phase, bow noise. SPINE expresses
this via a `humanize` MOD operator with an explicit seed:

```text
MOD vib_swell_h = vib_swell humanize 0.05 seed 1234
```

Same input + same seed → byte-identical performance. This satisfies
the demoscene reproducibility constraint.

**Decision: seeds inherit through three levels.**

Authors rarely want to write `seed=N` on every humanize. Instead, a
seed declared higher in the entity tree propagates downward by
hashing:

```text
GRP scene_intro seed 2718 {
  USE phrase_a at bar 1     # phrase_a's humanize MODs derive their
  USE phrase_a at bar 4     # effective seed from (2718, phrase_a, 0)
                            # and (2718, phrase_a, 1) respectively
}
```

The three levels:

1. **Score-level** — a `seed` attribute on a GRP. Sets the root for
   everything reachable from that GRP.
2. **MOD-derivation-level** — an explicit `seed` argument to humanize
   in a MOD declaration. Overrides the inherited score-level seed
   for that named variant and everything derived from it.
3. **USE-level** — an explicit `seed=N` USE override. Overrides
   inherited seeds for this instance only.

Resolution: hash `(inherited_seed, entity_id, instance_counter)` to
derive an effective seed for each humanize invocation. Resolution is
**offline**: the build tool walks every humanize-bearing entity,
computes its effective seed, and embeds it in the binary form. The
runtime never walks the entity tree at humanize evaluation time. See
`spine_runtime_model.md` §6.

**Constraint on roll-up.** The roll-up tool may NOT merge two USEs
with different effective seeds, even if their surface MOD chain is
identical. Two notes both written `gesture=vib_swell_h` produce
different jitter because their instance counters differ; this is the
audible content, not implementation detail.

**Decision: gesture transitions are score-level markers.**

A note USE may declare what gesture it transitions *from* via
`transition_from=`. SPINE carries the marker; the dialect resolves
the handoff. Slur is the special case where the previous and current
gestures both expose a "continue the bow" affordance and the dialect
chooses to use it.

```text
phrase ending {
  note D4 dur 0.5 gesture=m_loudest_h
  note D4 dur 2.0 gesture=legato_h  transition_from=m_loudest_h
}
```

The dialect's transition resolver may need runtime state in some
cases (humanize-perturbed bow position at the moment of transition);
see `spine_runtime_model.md` §9.6.

---

## 5. The dialect contract

SPINE core does not know what a cello is. A **dialect** does. To prevent
ad-hoc drift as dialects accumulate, each dialect is defined by a
one-page contract — see `spine_dialect_template.md` for the empty form.

A dialect declares:

- **Domain name** (`audio`, `music`, `motion`, `graphics`, `cello`, …)
- **Type ids** — the entities the dialect understands
  (`audio.resonator.cello`, `cello.gesture.détaché`)
- **Parameters** — for each type, the parameter names and value types
- **Ports** — for each type, the named input and output endpoints LNK
  can target, with shapes (signal / value / event)
- **Lifetimes** — for each type, runtime classification
  (streaming / event-driven / precomputed / sink). Surfaced by
  Prototype C. See `spine_dialect_template.md` §1.7.
- **Operators** — the MOD operators the dialect supports
  (`transpose`, `humanize`, `with_pressure`, …) with their arities
- **Verb-form arguments** — for operators that accept curve sugar,
  the verb vocabulary and what each verb desugars to
- **Override keys** — which operators are also valid as USE overrides
- **Transition table** — for dialects with gesture transitions, how
  (from, to) gesture pairs resolve (cello dialect; new in v0.3)
- **Time interpretation** — how the dialect uses local time on groups
  it produces

A dialect interpreter is a piece of code (initially Python, eventually
C/asm) that consumes the SPINE event stream and produces domain output:
audio samples, frame events, geometry, text.

**Starter dialects to date:** `music` (Prototype A), `patch` extended
(Prototypes B and C), `cello` sketch (Prototype D). See the dialect
template for filled examples.

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
GRP id [seed N] { statements }
```

Whitespace and newlines are not significant except as separators.
Comments use `#` to end of line. Strings are double-quoted.

**New in v0.3:**
- GRP may carry a `seed N` attribute (see §3.6 and §4.5).
- USE overrides may include `transition_from=ENTITY` (see §3.2).
- MOD operators may take verb-form arguments (`with_depth rise 0.0 0.7`).
- The `curve` value type accepts `ref(curve_entity)` or verb sugar.

Example covering all six ops plus v0.3 additions:

```text
# A small score fragment with gesture composition and humanization.

DEF arpeggio_0 : music.phrase {
  notes = [C3, E3, G3, C4]
  step  = 0.25
}

DEF cello_voice : audio.instrument.cello {
  brightness = 0.54
}

LNK arpeggio_0.out -> cello_voice.in

# Score-derived gesture variants (cello dialect):
MOD legato_arc   = détaché slur_from_prev
MOD legato_swell = legato_arc with_pressure rise 0.0 0.3
MOD vib_swell    = vibrato_warm with_depth ref(swell_then_settle)
MOD vib_decel    = vibrato_warm decelerando 0.7

# Music-side transposition variant:
MOD arpeggio_t7 = arpeggio_0 transpose +7

# Scene with a phrase-level seed. All humanize MODs reachable from
# scene_intro inherit their effective seed from 2718.
GRP scene_intro seed 2718 {
  USE arpeggio_0   at 0.0  dur 2.0
  USE arpeggio_t7  at 2.0  dur 2.0
  USE arpeggio_0   at 4.0  dur 1.0 { mute=[2] }
}

GRP demo_root {
  USE scene_intro at 0.0
}
```

**Grammar.** A formal grammar is still deferred. The expander parses
by hand — regex plus a small tokenizer. When the format stabilizes
through Prototype D and beyond, the grammar gets written down.

---

## 8. Prototypes to date

The SPINE design is validated incrementally by small prototypes. Each
one adds working code that exercises new design surface and provides a
regression baseline for the next.

| Prototype | Domain                       | Key validation                | Status   |
|-----------|------------------------------|-------------------------------|----------|
| A         | Music, structural compression | DEF/USE/MOD/GRP, reachability, roll-up baseline | done |
| B         | Patch graph resolution        | LNK with port-shape checking, MOD on graph nodes | done |
| C         | Streaming patches, simulator  | Lifetime classes, feedback loops, multi-source ports | done |
| D         | Cello dialect sketch          | Gesture composition, seed inheritance, transitions | this prototype |

Earlier prototype specs (A scope, B scope, C scope) live in their
respective `PROTOTYPE_*.md` files under `tools/spine/docs/`. See those
for historical context.

### 8.5 Prototype D — cello dialect sketch

**Scope.** A cello-dialect sketch sufficient to parse, resolve, and
validate the v0.3 additions: gesture composition, three-level seed
inheritance, sparse-curve verb sugar, and gesture transitions. No
audio synthesis — that lives in the cello chat plus eventual softsynth
work.

**Deliverables.**

| File                                          | Role                                  |
|-----------------------------------------------|---------------------------------------|
| `examples/cello_phrases.spine`                | Two phrases: legato + martélé→legato  |
| `examples/cello_phrases.resolved.txt`         | Reference resolution dump             |
| `tools/spine/src/expand.py`                   | Extended with cello dialect           |
| `tools/spine/tests/test_prototype_d.py`       | Smoke test                            |

**What Prototype D must exercise.**

- Composable gesture MOD chains (stacking three+ operators)
- Verb-form sparse curves (`with_pressure rise 0.0 0.3`)
- Reference-form sparse curves (`with_depth ref(swell)`)
- Score-level seed via `GRP <id> seed N { ... }`
- Per-MOD seed override (`humanize 0.05 seed 1234`)
- `transition_from=` USE override
- Cello dialect declaration with lifetimes, transition table
- Both Prototype A and music phrases continue to expand identically
- All previous tests still pass

**What Prototype D explicitly does not need.**

- Any audio output. The sketch resolves and validates; synthesis
  belongs to the cello chat.
- A complete cello dialect. ~6 base gestures, ~4 transformations,
  ~4 verbs is enough to write the two example phrases.
- Seed resolution end-to-end. Resolving humanize seeds offline (per
  §4.5) is a stub: Prototype D records that each humanize-bearing
  entity *would* have an effective seed; computing that seed is
  scheduled for a later prototype with actual audio.

**Success criterion.** The two example phrases parse cleanly, resolve
through the dialect, produce a deterministic reference dump, and pass
all assertions about the design (gesture chain composition, seed
inheritance correctness, transition markers preserved). Music and
patch prototypes continue passing.

---

## 9. What is deferred and why

| Topic                       | Why deferred                              | Re-open after                  |
|-----------------------------|-------------------------------------------|--------------------------------|
| Binary format               | Text format still evolving                | Prototype E or first compo demo |
| Formal grammar (EBNF)       | Hand-tokenizer working; grammar would lag | Same                            |
| C interpreter struct        | Python expander stable; C is a port       | First demo on K3                |
| Near-repetition roll-up     | Hard; needs evidence of value             | Exact-repetition measured win   |
| Inline curve points         | Verb sugar + ref() cover Prototype D      | Authoring fatigue with current  |
| Phrase-spanning operators (`crescendo over N`) | Author writes verbose form for now | Real score authoring stress     |
| Blob payloads               | Vectors suffice up to ~64 elements        | First real coefficient array    |
| Non-linear time             | Linear is enough so far                   | First motion or motif phasing   |
| Multi-domain time           | One time per group is enough              | Cross-domain demo               |
| Streaming evaluation        | Whole-program load is fine for demos      | Procedural / generative demo    |
| Probabilistic operators     | Seeded humanize lands in v0.3             | After more humanize-using work  |
| Type checking in dialects   | Trust authors for now                     | After dialects accumulate       |
| End-to-end seed resolution  | Prototype D records intent; resolution stub | First audio-producing prototype |
| Audio synthesis             | Out of scope; lives in cello chat + softsynth | Softsynth lands                 |

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
                                          arity-mixed operators, stackable
LNK   connect endpoints                   dataflow, cross-domain wiring
                                          multi-source ports sum or OR
GRP   group with local time               reusable scope
                                          optional seed attribute (v0.3)
```

Two variation mechanisms:

- **USE overrides** for ephemeral tweaks (including `transition_from=`).
- **MOD** for variants worth naming. Roll-up promotes overrides to MOD
  when warranted.

v0.3 adds:
- Gesture composition via MOD operator stacking, with verb-sugared
  curve arguments
- Three-level seed inheritance (GRP → MOD → USE), resolved offline
- Gesture transitions as score-level markers

Three layers: core / dialect / binary.

One principle: structural compression before entropy coding.

Library may explode. Core stays small. Reachability prunes. Roll-up
folds. Entropy coding comes last.

That is SPINE.
