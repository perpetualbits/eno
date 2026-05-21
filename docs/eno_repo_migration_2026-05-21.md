# ENO repo migration — 2026-05-21

**Purpose:** clean the repo before handing the coding role to Claude
Code. Settle naming, archive stale docs, consolidate the decision log,
and move session summaries out of the canonical docs directory.

This document is meant to be executed top-to-bottom. Each section
describes a discrete change. Use it as a checklist; tick items as you
go. The Claude Code handoff cannot land cleanly until this is done.

**Scope:** repo layout and documentation only. No code rewriting. The
wavelet and waveviz renames touch `Makefile` paths and `#include`
paths, which is the only invasive part.

**Related decision log entry:** see the 2026-05-21 naming round in
`eno_decision_log.md`.

---

## 1. Naming decisions to apply

| Old | New | Type |
|-----|-----|------|
| `lib/wavelet/` | `lib/crest/` | rename (deferred since 2026-05-18) |
| `tools/waveviz/` | `tools/carve/` | rename + scope correction |
| `tools/shaderbake/` | `tools/glint/` | rename (new name today) |
| `lib/synth/` | `lib/siftr/` | rename (new name today) |
| `docs/spine_runtime_model.md` | `docs/nerve_runtime_model.md` | rename |

Notes on each:

- **lib/crest/** — the wavelet library. `lib/wavelet/` is the current
  name; the design document already calls the library CREST and
  cross-references `lib/crest/`. This rename closes that gap.
- **tools/carve/** — the SPINE authoring/visualization tool. The
  current `tools/waveviz/` is just a stale stub README; CARVE is the
  real successor and already has `docs/carve_design.md`. The new
  directory should be structured for the node-graph UI plus tile
  system that CARVE will host.
- **tools/glint/** — the GLSL shader minifier/packer. `tools/shaderbake/`
  is a stub.
- **lib/siftr/** — the softsynth, built on CREST, coefficient-space
  processing. `lib/synth/` is a stub README only.
- **nerve_runtime_model.md** — the runtime was named NERVE on
  2026-05-17. The filename has been lagging. The body of the file
  may also need a pass to ensure it consistently refers to NERVE,
  not "the runtime" or "SPINE runtime."

---

## 2. Docs to consolidate or archive

### 2.1 One decision log

The repo currently has three:

- `docs/eno_decision_log.md` (canonical)
- `docs/eno_decision_log_2026-05-17.md` (probably already merged?)
- `docs/eno_decision_log_smola_v03_append.md` (append-style file
  that may or may not have been merged)

Action:

1. Verify whether the 2026-05-17 and SMOLA-v0.3-append files have
   already been folded into the canonical `eno_decision_log.md`.
2. If they have, move them to `docs/archive/` (don't delete — they
   may carry richer reasoning than the canonical log captures).
3. If they have not, fold them in chronologically, then archive.
4. Then append the 2026-05-21 naming round entry from
   `eno_decision_log_2026-05-21_naming.md` (this session's output).

### 2.2 One project index

- `docs/eno_project_index.md` (canonical)
- `docs/eno_project_index-old1.md` (stale)

Action: move `eno_project_index-old1.md` to `docs/archive/`. Update
the canonical index to reflect today's changes (see §3 below).

### 2.3 SPINE v0.2 supersession

- `docs/spine_core_v0_2_design.md` — superseded by v0.3
- `docs/spine_core_v0_3_design.md` — canonical

Action: move v0.2 to `docs/archive/`. The decision-log v0.3 entry
covers the supersession.

### 2.4 Session summaries

Currently in `docs/`:

- `_session_2026-05-17_summary.md`
- `_session_2026-05-18_summary.md`
- `_session_2026-05-21_afternoon_summary.md`
- `_session_2026-05-21_summary.md`

Action: create `docs/sessions/` and move all four (plus today's,
when produced) into it. `docs/` should hold only canonical design
documents and the project index/log.

### 2.5 Install notes at repo root

- `INSTALL_smola_v0.3.md`
- `INSTALL_smola_v0.3_refinements.md`

Action: move to `tools/smola/docs/` (closer to the code) or to
`docs/install/`. Either is fine; `tools/smola/docs/` is more cohesive.

---

## 3. Project index updates

After the moves above land, update `eno_project_index.md`:

1. Update §7 CREST: change "Canonical code location: `lib/wavelet/`
   (to be renamed `lib/crest/`...)" to plain "Canonical code
   location: `lib/crest/`."
2. Update §3 NERVE: rename the doc reference from
   `spine_runtime_model.md` to `nerve_runtime_model.md`. Drop the
   "to be renamed" note.
3. Add §11 GLINT (stub entry; `glint_design.md` does not yet exist).
   Pattern after the CREST entry.
4. Add §12 SIFTR (stub entry; `siftr_design.md` does not yet exist).
5. Add §13 SMOLA — there is no entry for SMOLA in the current
   index even though `docs/smola_design.md` exists.
6. Renumber §8 (Project-wide) and §9 (Future documents) as needed.

The future-documents list at §9 should also gain stubs for
`glint_design.md` and `siftr_design.md`.

---

## 4. Cruft to evaluate

- `tmp/1.md`, `tmp/files (1).zip` — almost certainly delete. Verify
  nothing inside is needed first.
- `tars/` — eight tarballs. Add a `tars/README.md` explaining what
  each snapshot is for and which are still relevant; or move all to
  `archive/snapshots/` if they are purely historical.
- `lib/core/README.md`, `lib/fx/README.md`, `lib/gfx/README.md`,
  `lib/io/README.md` — stub READMEs in empty directories. Decide
  whether each is a real future subsystem or a placeholder that
  should be removed until needed.

---

## 5. New directories to create (empty for now)

- `docs/archive/` — for superseded design docs and merged log
  fragments.
- `docs/sessions/` — for session summaries.
- `tools/nerve/` — NERVE has no code yet but is a named pillar; an
  empty directory with a stub README signals scope and prevents
  later "where does NERVE live?" confusion. Optional; can be
  deferred until first code lands.

---

## 6. After this migration

When the above is done, the repo is ready for the next two steps:

1. Draft `CLAUDE.md` at repo root. This is the system prompt for
   Claude Code: project pillars, comment discipline, decision-log
   protocol, diary protocol, repo layout, what to escalate.
2. Define the diary location and initial format.

These are deliberately separate from this migration. Migration is
mechanical (renames, moves, consolidations). The `CLAUDE.md` draft
is a content task that benefits from a clean repo to point at.

---

## 7. Checklist

Tick as you go.

### Naming and renames

- [ ] `lib/wavelet/` → `lib/crest/` (update Makefile, header paths,
      any `#include "wavelet.h"` references)
- [ ] `tools/waveviz/` → `tools/carve/`
- [ ] `tools/shaderbake/` → `tools/glint/`
- [ ] `lib/synth/` → `lib/siftr/`
- [ ] `docs/spine_runtime_model.md` → `docs/nerve_runtime_model.md`
- [ ] Body pass on `nerve_runtime_model.md` to ensure consistent
      NERVE references

### Doc consolidation

- [ ] Verify and merge `eno_decision_log_2026-05-17.md` if needed,
      archive
- [ ] Verify and merge `eno_decision_log_smola_v03_append.md` if
      needed, archive
- [ ] Append the 2026-05-21 naming entry to `eno_decision_log.md`
- [ ] Archive `eno_project_index-old1.md`
- [ ] Archive `spine_core_v0_2_design.md`
- [ ] Create `docs/archive/` and `docs/sessions/`
- [ ] Move all `_session_*` files into `docs/sessions/`
- [ ] Move `INSTALL_smola_v0.3*.md` into `tools/smola/docs/`

### Project index update

- [ ] CREST entry: drop the "to be renamed" parenthetical
- [ ] NERVE entry: rename to `nerve_runtime_model.md`
- [ ] Add GLINT stub entry
- [ ] Add SIFTR stub entry
- [ ] Add SMOLA entry (currently missing)
- [ ] Add GLINT and SIFTR design docs to the future-documents list

### Cruft

- [ ] Evaluate and clean `tmp/`
- [ ] Decide: `tars/` README or move to `archive/snapshots/`
- [ ] Decide on stub READMEs in `lib/core`, `lib/fx`, `lib/gfx`,
      `lib/io`

### Optional

- [ ] Create empty `tools/nerve/` with stub README
