# PROTOTYPE_D.md

Prototype D for SPINE v0.3 — cello dialect sketch.

## What it does

A SPINE document using the new v0.3 cello dialect parses, resolves
gesture MOD chains, propagates seeds through GRP nesting, captures
gesture transitions, and emits a per-note resolution dump suitable
for downstream consumption by a (yet-to-be-built) softsynth.

This is **design validation only**. No audio is produced. The real
cello instrument lives in a separate cello-dialect chat plus eventual
softsynth work.

## What's new since Prototype C

| Concern                          | Prototype C | Prototype D |
|----------------------------------|-------------|-------------|
| Dialects implemented             | music, patch | + cello sketch |
| MOD operator arities             | 1 or 2 (set) | + 0 (flags), + verb-form variable |
| Curve modifier sugar             | n/a | verb form + ref form |
| GRP-level attributes             | none | `seed N` |
| USE override semantics           | params only | + `transition_from=ref(prev)` |
| Reachability                     | USE/MOD/LNK | + ref() in DEF/USE param values |
| Line continuation                | none | `\` at end of line |
| Lifetimes                        | streaming/event/sink | + precomputed (cello gestures) |
| Output modes                     | music events, patch graph | + cello resolution |

## The cello dialect (v0.3 sketch)

Documented fully in `docs/spine_dialect_template.md` §3. Summary:

**Base gestures** (precomputed, instrument-side trajectory templates):
- `cello.gesture.détaché`, `martelé`, `legato`, `vibrato_warm`,
  `vibrato_narrow`, `sul_tasto`, `pizzicato`

**MOD operators** (composable):
- Arity 0: `slur_from_prev` (flag)
- Arity 1: `decelerando`, `accelerando`, `humanize` (with optional `seed N`)
- Verb-form: `with_pressure`, `with_depth`, `with_attack`,
  `with_bow_pressure` — each accepts verbs like `rise`, `fall`, `hold`,
  `grow`, `sharper`, `softer` plus numeric args, OR a `ref(curve)`

**Note type**: `cello.note` with `pitch` and `gesture=ref(...)` parameters.

**Transition table** maps (from_base, to_base) pairs to handoff
resolvers like `continue_bow`, `lift_and_settle`, `reattack`. Some
resolvers carry a `runtime_state_needed` flag that warns the runtime
that the resolution cannot be fully precomputed.

## The example: `cello_phrases.spine`

Two phrases exercising every new v0.3 surface:

**Phrase 1 (scene_a, seed=1234)** — three legato notes followed by
three vibrato notes. The legato builds via `slur_from_prev` and
`with_pressure rise 0.0 0.3`. The vibrato uses one `ref(swell_then_settle)`
modifier and one stacked `decelerando 0.7 with_depth ref(fall_smooth) humanize 0.05`.
All humanize MODs in this scene inherit their seed from the GRP.

**Phrase 2 (scene_b, no GRP seed)** — four martélé notes with rising
bow pressure crescendo, terminated by a legato note that explicitly
declares `transition_from=ref(m_loudest_h)`. The humanize MODs in this
scene carry explicit `seed 2718`, demonstrating per-MOD seed override
rather than GRP inheritance.

## Reading the resolution output

```
# cello resolution: 21 gestures, 11 notes

# gesture variants (sorted by id):
gesture base_détaché base=cello.gesture.détaché

gesture legato_swell base=cello.gesture.détaché
    slur_from_prev None
    with_pressure ('rise', 0.0, 0.3)
...
gesture vib_swell_h base=cello.gesture.vibrato_warm
    with_depth ('ref', 'swell_then_settle')
    humanize 0.05 seed=inherited
...

# note events (in performance order):
t=  0.0000  pitch=A3    dur=1.5000  gesture=base_détaché
t=  4.0000  pitch=D4    dur=2.0000  gesture=vib_swell_h  seed_tuple=(1234, 'vib_swell_h', 0)
...
t= 14.0000  pitch=D4    dur=2.0000  gesture=legato_h  transition_from=m_loudest_h resolver=lift_and_settle (runtime_state)  seed_tuple=(2718, 'legato_h', 0)
```

Each gesture variant lists its base gesture plus the accumulated MOD
operator stack. Each note event carries its global time, pitch,
duration, resolved gesture id, optional transition marker (with
resolver and runtime-state flag), and the seed tuple
`(parent_seed, entity_id, instance_counter)` for humanize resolution.

The seed tuple is what the *next* prototype will hash to a concrete
integer seed; v0.3 records the tuple and stops there.

## Running

From `tools/spine/`:

```sh
# Resolve and print the phrases:
python3 src/expand.py examples/cello_phrases.spine

# Reachability dump:
python3 src/expand.py examples/cello_phrases.spine --dump-reachable

# Just the gesture variants (head the output):
python3 src/expand.py examples/cello_phrases.spine | head -40
```

Or via the Makefile: `make cello`, `make test-d`.

## What this surfaced for the design

Things now folded back into the docs:

1. **Reachability must follow ref() values** in DEF params and USE
   overrides. Without this, `cello.note` DEFs that say
   `gesture=ref(legato_arc)` couldn't pull the gesture variants into
   scope. Fixed in `expand.py`; documented implicitly via test 7.

2. **MOD operator arity is now three-valued** (0, 1, 2+). Flag-style
   operators like `slur_from_prev` take no argument. Verb-form
   operators take a verb token plus N args (where N depends on the
   verb). The parser handles all three via the `_MOD_OP_ARITY` and
   `_MOD_OP_VERBS` tables. Documented in main design doc §3.4.

3. **Line continuation via `\`** is now supported. The parser
   strips backslash-newline before tokenizing. Used in the example
   to break long MOD chains across multiple lines. Documented in
   main design doc §7.

4. **GRP seed attribute is grammar-level**, not a SET. The §7.1
   open question's previous lean (SET-based scoping) was reconsidered
   for readability and pinned as a GRP attribute. Recorded as resolved
   in `spine_open_questions.md` §7.1.

5. **`precomputed` lifetime is now exercised** (cello base gestures).
   Prototype C declared the slot in the dialect contract; D fills it
   for the first time. The runtime model (§3.1) is ready for this.

## Bugs caught during bring-up

1. **Default `local_dur = 1.0`** when a USE has no explicit duration
   gave wildly wrong scaling for nested GRPs of notes. Fixed by adding
   `_natural_cello_dur()` that recursively computes the sum of natural
   durations (same pattern as the music dialect's `_natural_dur`).

2. **`follow_refs()` wasn't recursing into verb-form tuples.** The op
   `with_depth ('ref', 'swell_then_settle')` has the ref tuple
   *inside* the arg, not as the arg itself. Fixed by calling
   `follow_refs(arg)` AND iterating its elements.

3. **Arity-0 operators caused an off-by-one** in `_parse_mod_ops`
   (the check `if i + arity >= len(tokens)` failed when arity=0 and
   the operator was the last token). Fixed by gating with `arity > 0`.

## Open questions newly relevant

- **Transition implicit chaining.** Should a cello.note USE without
  `transition_from=` automatically pick up the previous note's
  gesture as the transition source? Prototype D keeps it explicit —
  authors must write the marker. Implicit chaining was considered and
  deferred (see code comment in `_resolve_cello_note`). Surfaces
  again when real cello scores show what musicians prefer.

- **What happens when a note has no gesture binding?** Currently the
  resolver records `gesture=(none)` and stops. Should this be a
  warning? An error? Tolerated for design fragments? Open.

- **Seed hashing scheme.** The seed_tuple format
  `(parent_seed, entity_id, instance_counter)` is recorded but not
  hashed. The hash function matters for cross-platform reproducibility
  (different Python hash seeds, different RISC-V implementations).
  Probably xxhash or a small custom mixer. Deferred until first
  audio-producing prototype.

## What v0.4 will likely need

Based on this work, candidate v0.4 changes:

- **Phrase-spanning operator families.** `MOD figure = base crescendo over 4 0.4 0.85` to replace the explicit four-variant pattern in the martélé example. Saves bytes, reads like real music. Deferred from v0.3 pending evidence of authoring fatigue.
- **Inline curve points.** `with_depth points [(0,0), (0.5,0.7), (1,0.3)]` as a third sugar form. Deferred until ref + verbs prove insufficient.
- **Seed hashing implementation.** Force the question with a real synthesis prototype.
- **End-to-end reproducibility test.** Two byte-identical renders from the same `.spine` file with the same seed.
