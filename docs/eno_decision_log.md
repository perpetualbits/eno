# Epsilon Null Operation — Decision Log

**Status:** append-only living document.
**Purpose:** record load-bearing decisions made across chats, with date,
source, and one-line summary. Reasoning stays in subsystem documents;
this log just tells you what was decided and where to read more.

New chats: read this immediately after `eno_project_index.md`.

---

## 2026-05-17 — SPINE v0.3 decisions

*(See `spine_core_v0_3_design.md` for full reasoning.)*

### Gesture composition replaces phrase nesting

- **Source:** SPINE design chat.
- **Affects:** `spine_core_v0_3_design.md`.
- **Reasoning:** gesture composition (`GRP` with typed child slots)
  subsumes phrase nesting and is more expressive for cello articulation.

### Three-level seed inheritance

- **Source:** SPINE design chat.
- **Affects:** `spine_core_v0_3_design.md`.
- **Reasoning:** instrument → style → note. Three levels cover all
  practical cases without over-engineering.

### Sparse continuous modifiers (SCM)

- **Source:** SPINE design chat.
- **Affects:** `spine_core_v0_3_design.md`.
- **Reasoning:** modifiers that apply over a duration rather than at
  a point; needed for continuous expression (vibrato, crescendo).

### Polar wavelet reverb: approach 3, global latency, point cloud scenes

- **Source:** SPINE / audio dialect chat.
- **Affects:** `spine_audio_dialect.md`.
- **Reasoning:** offline IR baking (approach 3) avoids real-time polar
  wavelet computation. Global latency for the first version. Point
  clouds are sufficient for 4k scenes.

### Listener grid IR interpolation: trilinear/barycentric at coarse grid

- **Source:** audio dialect chat.
- **Affects:** `spine_audio_dialect.md`.
- **Reasoning:** the wavelet transform is linear; convex combinations
  of valid IRs are valid. Trilinear weights over a coarse listener grid
  suffice for smooth listener motion in smooth geometry.

---

## 2026-05-17 — Project-management workflow established

### Project documents are the canonical channel between chats

- **Source:** CARVE design chat.
- **Affects:** project-wide.

### One canonical document per subsystem

- **Source:** CARVE design chat.
- **Affects:** all design documents.

### Project index and decision log are mandatory reading for new chats

- **Source:** CARVE design chat.
- **Affects:** `eno_project_index.md`, `eno_decision_log.md`.

### Chats end with a session summary listing uploads

- **Source:** CARVE design chat.
- **Affects:** every chat with design content.

---

## 2026-05-18 — CARVE design decisions

### CARVE is the authoring tool, not the rendering tool

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md`.
- **Reasoning:** CARVE authors SPINE entities (trajectory templates,
  scenes, IRs). NERVE renders them. The line is sharp.

### Two-tier implementation: portable C + Python ML

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §3.1.
- **Reasoning:** Tier 1 (C) must run on RISC-V; Tier 2 (Python, ML
  fitting) must run on GPU servers. File-based handoff keeps both tiers
  independently deployable.

### Coefficient square is the load-bearing visual primitive

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §4.5, §7.2.2.
- **Reasoning:** rows = wavelet bands (finest top, coarsest bottom),
  columns = time, hue = sign, luminance = magnitude. I/Q dual-square
  for analytic signals.

### In-CARVE playback until NERVE is ready; delegate after

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §4.6, §8 Phase 6.

### Dialect version field per node in CARVE projects

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §3.3.3.

### CARVE phase plan: 7 phases, MVP is one cello body end-to-end

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §8.

### CARVE depends on a wavelet library subsystem (CREST)

- **Source:** CARVE design chat (subsystem not yet named at that time).
- **Affects:** `carve_design.md` §2.6, `eno_project_index.md`.
- **Resolution:** subsystem initiated and named CREST on 2026-05-18.
  `carve_design.md` §2.6 now resolves to a named cross-reference.

---

## 2026-05-18 — CREST decisions

*(Full reasoning in `crest_design.md`.)*

### The wavelet library is named CREST

- **Source:** wavelet library chat (user choice).
- **Affects:** `crest_design.md`, `eno_project_index.md`,
  `carve_design.md` §2.6.
- **Reasoning:** "crest of a wave" — the peak, the visible form of
  frequency-time structure. Five letters, one syllable, fits the
  project naming register (SPINE, NERVE, CARVE, SMOLR). Not an
  acronym.

### CREST is float32 throughout; integer lifting rejected

- **Source:** wavelet library chat.
- **Affects:** `crest_design.md` §4.2, all of `crest_core`.
- **Reasoning:** Daubechies, chirplet, and Morlet bases have irrational
  filter coefficients that cannot be represented in integer lifting.
  A unified float32 representation serves all basis families with one
  code path. Float32 gives 144 dB dynamic range (sufficient). Maps
  directly to RVV `vfmul`/`vfmacc`. Integer lifting was prototyped,
  produced specific overflow bugs for coarse bands, and was abandoned.

### CREST has four modules: core, bases, 2d, 3d

- **Source:** wavelet library chat.
- **Affects:** `crest_design.md` §2.
- **Reasoning:** core (done), bases (audio dialect families), 2d
  (terrain/sand/smoke), 3d (volumetric cliff/cave geometry and SDF
  fields). 3D is needed because heightmaps cannot represent overhangs,
  undercuts, or hollow features like eye-socket caves; these require a
  volumetric SDF.

### WaveletSquare is the shared storage type across all 1D bases

- **Source:** wavelet library chat.
- **Affects:** `crest_design.md` §3, §5.1.
- **Reasoning:** all 1D bases (CDF 5/3, Daubechies, chirplet, Morlet,
  etc.) read/write the same `WaveletSquare` structure. NERVE uses one
  code path for storage regardless of which basis authored the content.
  The chirplet 5-tuple packing is an open question (see §13.3).

### The stamp primitive lives in crest_core, not lib/synth

- **Source:** wavelet library chat design.
- **Affects:** `crest_design.md` §4.3, library layout.
- **Reasoning:** stamping is a coefficient-domain operation, not an
  audio synthesis scheduling operation. lib/synth builds the timeline
  and voice model on top of stamp; it does not own stamp itself.

### Repository location: lib/wavelet/ → lib/crest/ (deferred migration)

- **Source:** wavelet library chat.
- **Affects:** `crest_design.md` §9.
- **Reasoning:** renaming is one atomic commit. Not urgent; current
  code works where it is. Trigger: when crest_bases is started and
  needs a clear home.

### Polar wavelet basis lives in CREST; polar reverb effect lives in lib/fx

- **Source:** wavelet library chat.
- **Affects:** `crest_design.md` §8.
- **Reasoning:** CREST provides the transform; lib/fx builds the
  reverb effect on top. Same boundary as: stamp lives in CREST,
  reverb (which calls stamp) lives in lib/fx.

### Next item in CREST: Daubechies-4, then chirplet

- **Source:** wavelet library chat.
- **Affects:** `crest_design.md` §5.2.
- **Reasoning:** D4 is first because it adds capability for noise-like
  signals (water, wind, consonants) with minimum implementation
  complexity (4 taps, standard Mallat algorithm). Chirplet is next
  because it is the basis for the cello body segment — the primary
  instrument in Desert Monument.

---

## 2026-05-21 — SMOLA v0.3 (hard cut from v0.2)

**Context:** v0.2 worked but its surface was ugly. Every SMOLA
construct started with `_`. Variable declarations needed `_var.t int
counter`. The language read more like a macro DSL than an assembly
dialect. The proximate decision was whether to keep evolving v0.2
incrementally or do a clean v0.3 rewrite. Chose rewrite. Hard cut,
not source-compatible.

### Direction: content-classified syntax

**Decided:** lines are classified by *what their first token is*, not
by syntactic prefix.

- A known SMOLA keyword → SMOLA construct
- A known RISC-V mnemonic (RVA23 table) → instruction passthrough
- A GAS directive (starts with `.`) → directive passthrough
- A label (`<ident>:` or `.L<id>:`) → label passthrough
- A comment (`#` or `//`) → comment (transferred to `.s`)
- Anything else → error: unknown mnemonic

This requires SMOLA to *know what instructions exist*. A mnemonic
table in `mnemonics.py` is the source of truth. v0.2 was deliberately
ignorant of the instruction set; v0.3 is deliberately well-informed.
The tradeoff: maintenance burden when new extensions ship, vs. strict
typo detection at preprocess time. Accepted the burden; the table is
plain Python data, one file, alphabetized, reviewable in normal diffs.

### Syntax simplifications

**Decided:** drop the `_` prefix from every SMOLA construct.

| v0.2                          | v0.3                                |
|-------------------------------|-------------------------------------|
| `_func name`                  | `func name`                         |
| `_endfunc` / `_endmethod`     | `end`                               |
| `_method Struct.name`         | `func Struct.name` (auto-detect)    |
| `_struct S { ... }`           | `struct S { ... }`                  |
| `_scope` / `_endscope`        | `scope` / `endscope`                |
| `_var.t int x`                | `int x`                             |
| `_var.s int x`                | `int.s x`                           |
| `_var.a int x`                | `int.a x`                           |
| `_var.a int x = a3`           | `int.a x = a3`                      |
| `_free name`                  | `zap name`                          |
| `_load_field` etc.            | `load_field` etc.                   |
| `_la_field`                   | `addr_field` (renamed)              |
| `! raw line`                  | `raw line`                          |

Default storage is T (caller-saved temporary); no suffix needed.
The .s/.a suffixes are the deviation from default.

### `func Foo.bar` auto-detects methods

**Decided:** if `Foo` is a previously-declared struct, `func Foo.bar`
implicitly binds `self` to `a0`. If `Foo` is not a declared struct,
the dot still becomes an underscore in the emitted symbol name but
no `self` binding is created. Removes the need for a separate
`_method` keyword.

### Initialization shorthand

**Decided:** typed declarations can include an initializer.

- `int counter 10` emits `li counter, 10`
- `int counter 0xDEAD` emits `li counter, 0xdead`
- `flt gain 0.75` emits the integer-bit-pattern + `fmv.w.x` sequence
  (f32 default) or a literal-pool entry + `la` + `fld` (f64)

This is the first SMOLA construct that emits an instruction at
declaration. v0.2 declarations were pure bookkeeping. The new
behavior is still zero-cost-beyond-what-you'd-have-written, but
declarations can now have side effects. Documented explicitly in
spec §2.4.

### `zap` replaces `_free`

**Decided:** keyword renamed for cleaner reading. Semantics unchanged:
T-storage returns to pool, S-storage releases name but keeps the
prologue commitment, A-storage releases name but ABI position is
unchanged.

### Anonymous temporaries reserved for v0.4

**Decided:** the form `int 10` (a type and an initializer with no
name) is reserved syntax. v0.3 errors on it with a hint to name
the binding. This holds the namespace without committing to
semantics. The right semantics for anonymous temporaries (single-
use? scoped to next mnemonic? expression-like?) is a design
question that needs concrete use cases to resolve. Defer entirely.

### Comment transfer

**Decided:** comments from source transfer to the generated `.s`.

- Block comments before a `func` flush to the `.s` *immediately
  before* the function's section header (so they precede the
  visible function unit).
- Block comments inside a function body flush at the position they
  appear in source.
- End-of-line comments on instruction lines transfer to the
  substituted instruction.
- Comments outside any function appear in order at top-level
  output.

Plus an auto-generated bindings table: immediately after each
function label (and prologue), SMOLA emits a block comment listing
every named variable in the function with its physical register and
storage class. Suppressed by `--no-provenance`. This is what makes
the generated `.s` debuggable: a reader can map abstract names back
to physical registers without scrolling.

Comments containing `//` are normalized to `#` for GAS compatibility.

### `raw` escape hatch

**Decided:** for the rare case where the user wants to emit an
instruction SMOLA's mnemonic table doesn't know about (a brand-new
extension, a vendor extension), a `raw <line>` keyword passes the
tail through verbatim with no checks. Provenance comment notes the
rawness. Replaces v0.2's `!` prefix.

### Mnemonic table coverage

**Decided:** the table covers the RVA23 baseline:
- RV32I, RV64I (base integer)
- M (mul/div), A (atomics)
- F, D (single/double float)
- C (compressed)
- Zicsr, Zifencei
- Zba, Zbb, Zbc, Zbs (bit manipulation)
- V (RVV 1.0)
- Standard pseudo-instructions (`li`, `mv`, `ret`, `j`, `jr`,
  `beqz`, `bnez`, `call`, `tail`, FP unary pseudos, etc.)

Roughly 500 mnemonics. Test asserts the total stays in a reasonable
range (350–1000) so an accidental large removal fails loudly. Adding
a new extension means editing one file (`mnemonics.py`).

Deliberate omissions: Zfh (half-precision), Sv* (supervisor), H
(hypervisor), debug, vendor extensions. Add when a real use case
appears.

### Implementation tree

```
tools/smola/
    src/smola/__init__.py        v0.3.0
    src/smola/mnemonics.py       NEW — closed RV mnemonic table
    src/smola/errors.py          unchanged in shape
    src/smola/lexer.py           rewritten — content classification
    src/smola/symbols.py         lightly edited; added has_struct()
    src/smola/regalloc.py        rename free → zap; bug fixes; add
                                  Allocator.history for the bindings
                                  table
    src/smola/frame.py           unchanged
    src/smola/translator.py      rewritten — new dispatch, comment
                                  transfer, bindings table, init
                                  emission
    src/smola/cli.py             unchanged
    src/bin/smola                unchanged
    tests/                       89 tests; new test_mnemonics.py
    examples/point.smola         ported to v0.3
    examples/render_square.smola NEW — demonstrates init shorthand
    examples/insn_length.smola   ported to v0.3
    Makefile                     unchanged
    README.md                    rewritten for v0.3
```

89 tests passing on the host. Assembly verification with
`riscv64-linux-gnu-as` is pending toolchain availability (the
sandbox where SMOLA was developed lacks the cross toolchain;
`make check-assembles` is the target Roland runs locally).

### Status of v0.2 artifacts

v0.2 implementation and v0.2 spec are discarded. The v0.3
`smola_design.md` §10 migration table is the historical record.
v0.2 was not shipped to anything; nothing depends on it.

---

## 2026-05-21 — Naming round and migration trigger

*(Made in preparation for handoff to Claude Code. The repo needs
consistent naming before an autonomous coding agent starts working
in it.)*

### The GLSL shader minifier/packer is named GLINT

- **Source:** Claude Code handoff prep chat (user choice).
- **Affects:** `eno_project_index.md`, future `glint_design.md`,
  `tools/shaderbake/` → `tools/glint/` rename.
- **Reasoning:** five letters, evocative of small flashes of light
  (shaders, highlights), fits the project naming register. Replaces
  the placeholder name "shaderbake."

### The softsynth is named SIFTR

- **Source:** Claude Code handoff prep chat (user choice).
- **Affects:** `eno_project_index.md`, future `siftr_design.md`,
  `lib/siftr/` rename.
- **Reasoning:** five letters, evokes filtering/sifting (which is
  what wavelet-coefficient-space processing does), non-word, fits
  the project naming register. SIFTR is built on CREST and operates
  in coefficient space. "SYNTH" was rejected as too generic.

### Trigger the deferred renames now

The 2026-05-18 CREST log entry deferred `lib/wavelet/` → `lib/crest/`
with the trigger condition "when crest_bases is started and needs a
clear home." That trigger is superseded by a stronger one: handoff
to Claude Code. Renames are best done before an autonomous agent
starts referring to paths in code, docs, and decision log entries.

All five renames executed 2026-05-21 in one atomic migration commit:
- `lib/wavelet/` → `lib/crest/`
- `tools/waveviz/` → `tools/carve/`
- `tools/shaderbake/` → `tools/glint/`
- `lib/synth/` → `lib/siftr/`
- `docs/spine_runtime_model.md` → `docs/nerve_runtime_model.md`

- **Affects:** repo layout, all docs that cross-reference paths,
  `eno_project_index.md`.
- **Reasoning:** see `docs/eno_repo_migration_2026-05-21.md`.

### Doc-layer drift resolved in the same migration

- `eno_decision_log_smola_v03_append.md` merged into canonical log and
  archived.
- `eno_decision_log_2026-05-17.md` archived (content already covered in
  canonical log).
- `eno_project_index-old1.md` archived.
- `spine_core_v0_2_design.md` archived (v0.3 supersedes it).
- Session summaries moved to `docs/sessions/`.

- **Affects:** `docs/` layout.
- **Reasoning:** Rule 2 (one canonical document per subsystem) and
  Rule 3 (one decision log) are now honored.

### Handoff to Claude Code as a coding role

- **Source:** Claude Code handoff prep chat.
- **Affects:** project-wide workflow. New file: `CLAUDE.md` at repo
  root (to be drafted in a follow-up session).
- **Reasoning:** the chat-project workflow now becomes management,
  ideation, and design review. Claude Code owns code production,
  appends its own decision log entries, and maintains a diary. The
  repo is the canonical substrate; chat-project files are a snapshot.

---

## 2026-05-21 — SMOLA external-tooling commitments

*(Full reasoning in `docs/smola_design.md` §13.)*

### SMOLA's design accommodates external tooling integration

- **Source:** SMOLA / ENO continuity chat.
- **Affects:** `docs/smola_design.md` (new §13), future Rust port.
- **Reasoning:** SMOLA was conceived for hand-written demo code, but
  its determinism, strict grammar, and provenance machinery also
  make it suitable as a stage in automated pipelines (CI, fuzzing,
  batch compilation, ML candidate-assembly generation). Four hooks
  are committed to as design requirements: structured JSON
  diagnostics, batch invocation mode, machine-queryable provenance
  maps, and determinism as a public guarantee. None ship in v0.3.
  The Rust port must preserve them; §13.6 carries the checklist.
  This decision does not change SMOLA's language or behavior — it
  constrains implementation structure so external use stays open.

### SMOLA added as its own subsystem entry in the project index

- **Source:** SMOLA / ENO continuity chat.
- **Affects:** `docs/eno_project_index.md`.
- **Reasoning:** `smola_design.md` is a canonical subsystem document
  but was previously only referenced obliquely from the SMOLR
  section. SMOLA gets its own index entry with a notes line
  referencing §13.

---

## 2026-05-21 — SMOLA v0.3.1 decisions

*(See `docs/smola_design.md` §2.13 for full spec.)*

### String keywords: str, cstr, txt

- **Source:** Claude Code session (smola_design.md v0.3.1 work).
- **Affects:** `tools/smola/`, `docs/smola_design.md`.
- **Decision:** Add three string-data keywords for use in data sections:
  `str "…"` (bare byte string), `cstr "…"` (NUL-terminated), and
  `txt`/`eot` (multi-line heredoc). All require a preceding label.
  `.size` is emitted automatically. `str`/`cstr` support `\"`, `\\`,
  `\n`, `\t`, `\0`, `\xHH` escapes. `txt` content is raw (no escape
  processing; `\` and `"` are escaped for GAS automatically).
- **Reasoning:** the wavelet and audio demos need string constants for
  error messages, banners, and protocol tags. Inline string syntax is
  far less error-prone than hand-writing `.ascii` + `.size`.

### f16/bf16 stubs

- **Source:** Claude Code session.
- **Affects:** `tools/smola/`.
- **Decision:** `f16`, `bf16`, and their `.s`/`.a` variants are added to
  `SMOLA_KEYWORDS` so the lexer does not reject them as unknown. The
  translator raises "not yet implemented" if they are used. This locks
  in the keyword names before any demos use them as identifiers.

### Sub-byte and exotic FP reserved keywords

- **Source:** Claude Code session.
- **Affects:** `tools/smola/`.
- **Decision:** `fp8`, `fp4`, `i4`/`u4`, `i2`/`u2`, `i1`/`u1`,
  `b1p58` (with `.s`/`.a`), and `packed` are reserved in
  `SMOLA_KEYWORDS`. Using them raises "reserved — not yet implemented".
  They are claimed now to prevent user code from relying on these
  tokens for identifiers/labels.

### txt lexer is stateful in lex_source, not lex_line

- **Source:** Claude Code session.
- **Affects:** `tools/smola/src/smola/lexer.py`.
- **Decision:** `lex_line` remains stateless. `lex_source` holds a
  `txt_active` bool and re-classifies txt-block interior lines as
  `TXT_LINE` / `TXT_END`. The `txt` opener line is re-classified as
  `TXT_BLOCK`. This keeps single-line classification simple and puts
  the heredoc state where it belongs: the source-level pass.

### _split_trailing_comment made quote-aware

- **Source:** Claude Code session.
- **Affects:** `tools/smola/src/smola/lexer.py`.
- **Decision:** fixed to track an `in_str` flag so `#` and `//` inside
  a double-quoted string are not treated as comment markers. Required
  by `str`/`cstr` operands that contain `#` (e.g. URL fragments).

### Version bump to 0.3.1

- **Source:** Claude Code session.
- **Affects:** `tools/smola/src/smola/__init__.py`.
- **Decision:** bumped from `0.3.0` to `0.3.1`. Minor increment: adds
  features, no source incompatibilities with v0.3.
