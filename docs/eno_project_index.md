# Epsilon Null Operation — Project Index

**Status:** living document
**Purpose:** the map. Lists every project document, its scope, its status,
and the subsystem it belongs to.

Every chat in this project should read this file and `eno_decision_log.md`
first. The index tells you what exists. The log tells you what was decided.

---

## 1. How to read this file

Documents are grouped by subsystem. Each entry gives:

- **File:** the canonical filename in project files
- **Scope:** one line on what the document covers
- **Status:** `stable` / `working draft` / `stub` / `to be written`
- **Last load-bearing change:** date and brief description, when known

When a document is added or renamed, update this file in the same session.

---

## 2. SPINE — the symbolic backbone

### `spine_core_v0_3_design.md`

- **Scope:** the six core operations (DEF, USE, SET, MOD, LNK, GRP),
  the dialect contract, time model, reachability, roll-up, textual
  format.
- **Status:** working draft v0.3
- **Notes:** v0.3 adds gesture composition, three-level seed inheritance,
  sparse continuous modifiers, gesture transitions. Companion to
  `spine_dialect_template.md`.

### `spine_dialect_template.md`

- **Scope:** template for defining a new SPINE dialect. Includes worked
  examples for the `music` dialect (v0.2) and the `cello` dialect
  (v0.3 sketch).
- **Status:** working draft
- **Notes:** every new dialect is specified by filling in this template
  and adding the result as a separate document in project files.

### `spine_open_questions.md`

- **Scope:** deferred design questions, with shape
  (question / deferred because / force a decision when / current lean).
- **Status:** living document
- **Notes:** when a question resolves, move the resolution into the
  appropriate main doc and strike it through here.

### `spine_audio_dialect.md`

- **Scope:** the `audio` dialect. Instrument types (segments, bases,
  trajectory templates), spatial types (point clouds, microphones,
  listeners), effects (polar wavelet reverb), parameter quantization
  tables.
- **Status:** working draft v0.1 sketch
- **Notes:** consumed by CARVE and NERVE. Cross-references
  `nerve_runtime_model.md` and `crest_design.md`.

---

## 3. NERVE — the runtime

### `nerve_runtime_model.md`

- **Scope:** runtime model for SPINE-based demos on RISC-V. Lifetime
  classes, threading, core affinity, seed resolution, frame budgets,
  allocation strategy, open runtime questions.
- **Status:** skeleton v0.1
- **Notes:** the runtime is named **NERVE** (named 2026-05-17).
  Filename updated 2026-05-21.

---

## 4. SMOLR — the sizecoding linker

### `Smolr_Design_And_Plan.md`

- **Scope:** RISC-V-native minsize linker and runtime import system
  for tiny dynamically linked Linux executables.
- **Status:** working design, Phase 1 in progress
- **Notes:** companion to `Smolr_Embedded_Disassembler_Design.md` and
  `smola_design.md`.

---

## 5. smold — the byte-level disassembler

### `Smolr_Embedded_Disassembler_Design.md`

- **Scope:** atom-composed RISC-V disassembler. Dual personality:
  development tool and embedded artistic effect.
- **Status:** working design, M1 implemented

---

## 6. SMOLA — the assembly macro preprocessor

### `smola_design.md`

- **Scope:** Python preprocessor for RISC-V GAS assembly. Adds typed
  variable declarations (`int`, `ptr`, `flt`, `vec` with optional
  `.s`/`.a` storage suffixes), struct field access (`load_field`,
  `store_field`, `addr_field`), function-frame planning, scope-based
  register lifetime (`scope`/`endscope`), comment transfer from
  source to `.s`, and strict typo detection via a closed RV mnemonic
  table. Emits GAS-compatible `.s`. The discriminator is content-based,
  not prefix-based: a line is recognized by whether its first token is
  a known SMOLA keyword, a known RISC-V mnemonic, a GAS directive, a
  label, or a comment — anything else is an error.
- **Status:** working draft v0.3 (2026-05-21). Implementation
  prototype in `tools/smola/` (89 unit tests passing on host;
  assembly verification with `riscv64-linux-gnu-as` pending toolchain
  availability).
- **Notes:** companion to SMOLR and smold. Used to write `.s` for
  those subsystems' assembly. v0.3 is a hard cut from v0.2; see
  `smola_design.md` §10 for the migration table. The auto-generated
  bindings table at the top of each function maps SMOLA variable
  names back to physical registers in the `.s`, keeping the
  generated output readable when debugging. Anonymous temporaries
  (`int 10` without a name) are *reserved syntax* — they error in
  v0.3 with a hint, holding the namespace for v0.4 semantics.

---

## 7. CARVE — the wavelet/coefficient authoring tool

### `carve_design.md`

- **Scope:** offline authoring tool for `audio.trajectory_template`
  entities and 3D scene definitions. ML fitting, node-graph UI, IR
  baking for polar wavelet reverb.
- **Status:** working draft v0.1 (2026-05-18)
- **Notes:** depends on CREST (§2.6 now has a named cross-reference).
  Two-tier implementation. 7-phase plan. Cyberpunk UI.

---

## 8. CREST — the wavelet transform library

### `crest_design.md`

- **Scope:** coefficient-domain transform library. Four modules:
  `crest_core` (CDF 5/3, WaveletSquare, stamp, Arena — done),
  `crest_bases` (Daubechies, chirplet, Morlet, Gabor, damped-exp,
  formant stack, noise, impulse), `crest_2d` (terrain, sand, smoke
  fields), `crest_3d` (volumetric cliff/cave geometry, SDF volumes).
- **Status:** working draft v0.1 (2026-05-18)
- **Canonical code location:** `lib/crest/`
- **Notes:** float32 throughout. RVV kernels planned per module.
  26 tests passing in `crest_core`. Named CREST 2026-05-18; directory
  renamed 2026-05-21.

---

## 9. GLINT — the GLSL shader minifier/packer

- **Scope:** GLSL shader minification and packing for size-coded
  productions.
- **Status:** stub (directory exists: `tools/glint/`)
- **Notes:** named GLINT 2026-05-21. Replaces placeholder `tools/shaderbake/`.
  Design document (`glint_design.md`) not yet written.

---

## 10. SIFTR — the softsynth

- **Scope:** wavelet-coefficient-space softsynth built on CREST. Stamps,
  envelopes, oscillator banks, voice management, note triggers.
- **Status:** stub (directory exists: `lib/siftr/`)
- **Notes:** named SIFTR 2026-05-21. Replaces placeholder `lib/synth/`.
  Design document (`siftr_design.md`) not yet written.

---

## 11. Project-wide

### `eno_project_index.md` (this file)

- **Scope:** the map. Lists every project document.
- **Status:** living document

### `eno_decision_log.md`

- **Scope:** append-only log of load-bearing decisions, dated.
- **Status:** living document

---

## 12. Future documents (placeholders)

- `glint_design.md` — GLINT design document (when enough scoping exists).
- `siftr_design.md` — SIFTR design document (when enough scoping exists).
- `spine_cello_dialect.md` — when the cello dialect graduates from
  sketch to its own document.
- `spine_graphics_dialect.md` — for procedural graphics, shaders.
- `spine_motion_dialect.md` — for gesture, gait, cloth, body motion.
- `spine_text_dialect.md` — for UTF-8 strings, layout, glyph masks.
- `nerve_audio_engine.md` — when NERVE's audio pipeline grows enough.
- `nerve_graphics_engine.md` — same for rendering.
- `carve_ml_fitting.md` — when the ML fitting pipeline grows enough.
- `smola_rvv_dialect.md` — when the curated vector vocabulary graduates
  from sketch to its own document (planned v0.4).

---

## 13. How chats should use this

**At the start of a chat:** read this file. Read `eno_decision_log.md`.
Identify which subsystem the chat is about. Read that subsystem's
documents.

**During a chat:** when a load-bearing decision is made, log it in
`eno_decision_log.md` in the same session.

**At the end of a chat:** produce a session summary file listing all
files to upload and what each changes.
