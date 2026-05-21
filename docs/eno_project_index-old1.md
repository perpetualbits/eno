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
  appropriate main doc and strike it through here. See its §11
  re-entry checklist.

### `spine_audio_dialect.md`

- **Scope:** the `audio` dialect. Instrument types (segments, bases,
  trajectory templates), spatial types (point clouds, microphones,
  listeners), effects (polar wavelet reverb), parameter quantization
  tables.
- **Status:** working draft (v0.1, sketch)
- **Notes:** consumed by CARVE (which authors `audio.trajectory_template`
  entities) and by NERVE (which renders them). Cross-references
  `spine_runtime_model.md` for runtime-side capabilities.

---

## 3. NERVE — the runtime

### `spine_runtime_model.md`

- **Scope:** runtime model for SPINE-based demos on RISC-V. Lifetime
  classes, threading, core affinity, seed resolution, frame budgets,
  allocation strategy, open runtime questions.
- **Status:** skeleton v0.1
- **Notes:** the runtime is named **NERVE** as of 2026-05-17. The
  filename will be renamed to `nerve_runtime_model.md` in a future
  cleanup pass; until then, the document carries a one-line note at
  the top recording the name.

---

## 4. SMOLR — the sizecoding linker

### `Smolr_Design_And_Plan.md`

- **Scope:** RISC-V-native minsize linker and runtime import system
  for tiny dynamically linked Linux executables. Atom discipline, free-
  hash imports, code/data split, call transform, section-reordering.
- **Status:** working design, Phase 1 in progress
- **Notes:** companion to `Smolr_Embedded_Disassembler_Design.md`.

---

## 5. smold — the byte-level disassembler

### `Smolr_Embedded_Disassembler_Design.md`

- **Scope:** atom-composed RISC-V disassembler. Dual personality:
  development tool and embedded artistic effect. M1 (fallback walker)
  complete; M2 (RV64I decode) is next.
- **Status:** working design, M1 implemented
- **Notes:** byte classification reporter feeds SMOLR's transform passes.

---

## 6. CARVE — the wavelet/coefficient authoring tool

### `carve_design.md`

- **Scope:** offline authoring tool for `audio.trajectory_template`
  entities and 3D scene definitions. ML fitting of instrument samples
  to wavelet bases, node-graph UI, IR baking for polar wavelet reverb.
  Eventually unified across 1D audio and 2D/3D graphics.
- **Status:** working draft v0.1 (2026-05-18)
- **Notes:** two-tier implementation — portable C core (Tier 1,
  Linux x86 first, then RISC-V) and Python ML fitting subsystem
  (Tier 2, GPU dev servers). Dialect-pluggable node-graph core with
  audio and 3D-scene plugins in v0.1. Produces dialect-canonical
  entities only, never a parallel format. Consumed by the SPINE build
  pipeline. Cyberpunk-style UI. Phase plan in §8 (7 phases).
  Depends on a wavelet library subsystem yet to be initiated.

---

## 7. Project-wide

### `eno_project_index.md` (this file)

- **Scope:** the map. Lists every project document.
- **Status:** living document

### `eno_decision_log.md`

- **Scope:** append-only log of load-bearing decisions, dated, with
  one-line summaries and pointers to where reasoning lives.
- **Status:** living document
- **Notes:** new chats should read this immediately after the index.
  Not a substitute for the full design documents — just the headline
  list.

---

## 8. Future documents (placeholders)

These do not exist yet but are known to be coming. Listed here so the
naming is reserved.

- `spine_cello_dialect.md` — when the cello dialect graduates from
  sketch (currently in `spine_dialect_template.md` §3) to its own
  document.
- `spine_graphics_dialect.md` — for procedural graphics, shaders,
  geometry atoms.
- `spine_motion_dialect.md` — for gesture, gait, cloth, body motion.
- `spine_text_dialect.md` — for UTF-8 strings, layout, glyph masks.
- `nerve_audio_engine.md` — when NERVE's audio pipeline grows enough
  detail to need its own document.
- `nerve_graphics_engine.md` — same for rendering.
- `carve_ml_fitting.md` — when the ML fitting pipeline grows enough
  to need its own document.
- *(wavelet library)* — CARVE depends on a wavelet library
  subsystem (forward / inverse transforms per basis, coefficient-
  space arithmetic, eventual RVV kernels). The subsystem is not yet
  named and not yet initiated; will be done in its own chat with its
  own design document. When that document arrives, it joins this
  index with its chosen filename and `carve_design.md` §2.6 gains a
  named cross-reference.

When any of these graduates from placeholder to real document, update
this index and the decision log in the same session.

---

## 9. How chats should use this

**At the start of a chat:** read this file. Read `eno_decision_log.md`.
Identify which subsystem the chat is about. Read that subsystem's
documents.

**During a chat:** when a load-bearing decision is made, log it in
`eno_decision_log.md` in the same session.

**At the end of a chat:** if new documents were created or existing
ones changed, produce a session summary file listing the changes and
the upload steps. See the project-wide conventions for details.
