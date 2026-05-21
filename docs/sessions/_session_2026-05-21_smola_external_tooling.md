# Session summary — 2026-05-21 (SMOLA external-tooling integration)

## Context

User shared `howto.md`, a blueprint for a local RLAIF/GRPO pipeline
that fine-tunes a quantized LLM to emit optimized RVV assembly. The
pipeline is part of the user's AI server / AI course work, not ε₀.
However, SMOLA is intended as a stage in that pipeline (the model
emits `.smola`; SMOLA produces `.s`; the sandbox compiles and
scores).

This session did **not** add the pipeline as an ε₀ pillar. It only
recorded the implications for SMOLA's design — specifically, the
hooks SMOLA must keep available so it can serve as a pipeline stage
without redesign, especially through the future Rust port.

A side-effect catch: SMOLA had no entry in the project index. Fixed.

## Files to upload

Upload these three files to project files, replacing the existing
copies:

### 1. `smola_design.md`

**Change:** added §13 "External tooling integration considerations".

The new section names four hooks the design accommodates:

- §13.1 Structured diagnostics (`--diagnostics-json`)
- §13.2 Batch invocation and fast startup (`--batch`)
- §13.3 Machine-queryable provenance (`--provenance-map`)
- §13.4 Determinism as a public guarantee

Plus:
- §13.5 What is explicitly out of scope (no API library in the
  Python prototype, no daemon mode, no scoring/profiling, no
  non-RISC-V targets)
- §13.6 Rust-port checklist (informational, 8 items)

None of these ship in v0.3. The section exists so the Rust port
does not foreclose them.

### 2. `eno_decision_log.md`

**Change:** two new entries under a 2026-05-21 heading:

- "SMOLA's design accommodates external tooling integration" —
  commits to the four hooks as design requirements.
- "SMOLA is added as its own subsystem entry in the project index" —
  records the index restructure.

### 3. `eno_project_index.md`

**Change:** added §5 "SMOLA — the macro language above RISC-V
assembly" between SMOLR (§4) and smold (now §6). Renumbered
subsequent sections: smold §6, CARVE §7, CREST §8, Project-wide §9,
Future documents §10, How chats should use this §11. SMOLR's notes
line now cross-references `smola_design.md` as well.

## Other subsystems touched

None. No SMOLR, smold, SPINE, NERVE, CARVE, or CREST documents
were modified. The SMOLR entry in the project index gained a
cross-reference to SMOLA, but this is incidental and does not
require uploading `Smolr_Design_And_Plan.md`.

## Open questions / deferred

None opened or closed this session. The §13 hooks are commitments,
not open questions — they ship when the Rust port happens.

## What was deliberately not done

- No file or section was added describing the AI pipeline itself.
  That work belongs to the user's AI course / server project, not
  ε₀.
- No SMOLA prototype code was touched. §13 is design-only.
- `howto.md` was not added to project files. It's an external
  reference document for context only.

## Suggested next focus

Two reasonable continuations:

- **Main path:** return to whatever ε₀ pillar was active before this
  digression (the session-summary file from 2026-05-17 plus the
  decision log suggest SPINE / audio dialect / CARVE were the live
  threads).
- **Optional side path:** if SMOLA prototyping is the active focus,
  the natural next small step is M1 (assembly verification with
  `riscv64-linux-gnu-as` on the host) per `smola_design.md` §8 —
  unrelated to §13, but the right size of next step for SMOLA itself.
