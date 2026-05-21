# Epsilon Null Operation — Decision Log

**Status:** living document, append-only
**Purpose:** one-line summaries of load-bearing project decisions.
Reasoning lives in the subsystem documents; this log lists what was
decided and where to read.

Every chat in this project should read this file (and
`eno_project_index.md`) before starting work.

---

## How to read this file

Entries are in reverse chronological order (newest first). Each entry
gives: date, decision (one line), source chat or document, and the
documents the decision affects.

When a new decision is made in any chat, an entry is appended in the
same session. The log is not a discussion forum — debate happens in
the design documents.

---

## 2026-05-18 — CARVE design document (this session)

### CARVE is implemented in two tiers

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §3.1, §8 (phase plan).
- **Reasoning:** Tier 1 (portable C) handles the node-graph editor,
  IR baker, project I/O, and SPINE text emission; must be small
  enough to run on RISC-V eventually. Tier 2 (Python) handles ML
  fitting of segments to wavelet bases on the GPU dev servers
  (RTX A2000 / A5000). Communication is file-based JSON, not live
  IPC, so Tier 1 can run with stale fits when Tier 2 is unavailable.

### CARVE node-graph core is dialect-pluggable

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §3.2.
- **Reasoning:** the audio and 3D scene plugins are separate from
  the core in v0.1; the future graphics plugin will plug in the same
  way. Adding a dialect means writing a plugin, not modifying the
  core. Plugin boundary becomes more load-bearing in Phase 7.

### CARVE native project format is JSON

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §3.3.
- **Reasoning:** open standard, widely tooled, schema-validatable,
  human-readable in a pinch. Round-trips with SPINE text emission;
  the project format is the editor's internal state, SPINE text is
  the export. (Adjacent SPINE-side question — should SPINE itself
  adopt JSON — flagged for the SPINE design chat, not decided here.)

### CARVE supports both pruned and flat emission modes

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §3.4.
- **Reasoning:** pruned is the default (tiny binaries are the
  project goal); flat is opt-in for distributing instrument
  libraries. The SPINE build pipeline performs authoritative
  reachability pruning either way; CARVE's mode just affects what
  gets handed off.

### Coefficient square is the load-bearing visual primitive for wavelet editing

- **Source:** CARVE design chat (user contributed the design from
  prior wavelet visualization work, with example image).
- **Affects:** `carve_design.md` §4.5, §7.2.2.
- **Reasoning:** a 2D grid with `level · count_per_level` rows
  (finest at top, coarsest at bottom), time on the horizontal axis,
  two opposing hues for coefficient sign, luminance for magnitude.
  Three view modes — static, timeline, scrolling. I/Q dual-square
  mode for periodic signals where phase progression becomes a
  rotation in the (I, Q) plane. Sliders supplement the square for
  named coefficients (chirp rate, formant frequency); the square is
  the primary surface.

### In-CARVE playback until NERVE is ready; delegate after

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §4.6, §8 Phase 6.
- **Reasoning:** Phases 1–4 ship a small ALSA playback path inside
  CARVE so trajectory templates can be auditioned while editing.
  Once NERVE renders trajectory templates end-to-end, the cutover
  happens (Phase 6); the in-CARVE path is either removed or
  repurposed as a thin client.

### Dialect version field per node in CARVE projects

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §3.3.3.
- **Reasoning:** the audio dialect (and eventually the graphics
  dialect) will evolve. CARVE projects record the dialect version
  each emitting node was authored against; on load, mismatches
  warn the user about possible re-emission, but the project loads
  regardless. Avoids silently breaking old projects.

### CARVE depends on a wavelet library subsystem (not yet initiated)

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §2.6, `eno_project_index.md` §8.
- **Reasoning:** wavelet forward/inverse transforms per basis,
  coefficient-space arithmetic, and (eventually) RVV kernels are
  used by CARVE but should not be owned by CARVE. The library is
  initiated as its own subsystem in a separate chat with its own
  design document. CARVE specifies the interface it needs; the
  library design owns the rest. Index lists it as a placeholder
  pending name and initiation.

### CARVE phase plan: 7 phases, MVP is one cello body end-to-end

- **Source:** CARVE design chat.
- **Affects:** `carve_design.md` §8.
- **Reasoning:** Phase 1 ships a CLI fit-and-emit-and-preview for
  one cello D4 body segment; Phase 2 adds the empty node-graph
  editor; Phase 3 wires the full 1D pipeline into the editor;
  Phase 4 adds 3D scenes and the IR baker; Phase 5 covers a full
  cello note with all gestures; Phase 6 ports Tier 1 to RISC-V and
  applies cyberpunk polish; Phase 7 adds a second instrument and
  the graphics-dialect handshake. RISC-V port deliberately late so
  Phase 1–5 isn't slowed by dual-platform concerns.

---

## 2026-05-17 — earlier CARVE design chat

### The runtime is named NERVE

- **Source:** CARVE chat, after considering options.
- **Affects:** `spine_runtime_model.md` (gets a one-line top note;
  filename will be renamed to `nerve_runtime_model.md` in a future
  cleanup pass).
- **Reasoning:** anatomically integral to SPINE, short, distinctive
  in logs, fits the project's naming family without being cute.

### CARVE is the offline authoring tool for instrument trajectory templates

- **Source:** CARVE chat.
- **Affects:** `carve_design.md` (new, to be written),
  `spine_audio_dialect.md` (new).
- **Reasoning:** SPINE v0.3 already decided gestures are opaque to the
  score and that trajectory templates live instrument-side. CARVE fills
  the gap of "where do trajectory templates come from." CARVE does NOT
  produce SPINE atoms directly — it produces `audio.trajectory_template`
  entities that SPINE gestures reference.

### Binary SPINE format uses per-dialect dictionaries with per-stream pruning

- **Source:** CARVE chat (bitstring discussion).
- **Affects:** `spine_open_questions.md` §2.1 and §2.2 (resolved in
  intent; formal move into `spine_core_v0_3_design.md` deferred until
  binary format implementation begins).
- **Reasoning:** structural compression before entropy coding; reuse of
  the reachability-pruning idea from SMOLR atom discipline. Names are
  readable in the text form; the binary form encodes them via
  dialect-scoped, per-stream-pruned dictionaries. Free-hash trick from
  SMOLR §8.3 may apply as a Phase 6+ refinement.

### Audio dialect requires a parameter quantization table

- **Source:** CARVE chat.
- **Affects:** `spine_audio_dialect.md` (new), future updates to
  `spine_dialect_template.md` adding a quantization-table field per
  type.
- **Reasoning:** the binary form needs to know how many bits each
  parameter occupies and how they are encoded. This is a dialect-side
  concern, not a CARVE concern.

### Polar wavelet reverb: approach 3 (separate direct path from precomputed reverb IR)

- **Source:** CARVE chat (reverb design discussion).
- **Affects:** `spine_audio_dialect.md` (new).
- **Reasoning:** approach 1 (fixed source position) kills spatialization.
  Approach 2 (parameterized IRs per source position) is too expensive
  for 4k. Approach 3 splits the problem cleanly: the direct
  source-to-microphone path is computed at runtime from source position;
  the room's reverb IR is precomputed offline, per microphone, and is
  source-independent in the diffuse-field approximation. Matches standard
  game audio practice.

### Polar wavelet reverb: pre-echoes via global audio latency L

- **Source:** CARVE chat.
- **Affects:** `spine_audio_dialect.md` (new),
  `spine_runtime_model.md` (NERVE) §9.1 will gain a note when next
  updated.
- **Reasoning:** "negative R" notation is a bookkeeping convenience.
  At runtime, NERVE introduces a fixed playback latency (probably
  100–300 ms). Pre-echo taps live at negative offsets relative to the
  dry signal but at non-negative absolute output time. Causality
  preserved; "freaky pre-echoes" remain expressible.

### Polar wavelet reverb: point cloud + radial bucketing for 4k

- **Source:** CARVE chat.
- **Affects:** `spine_audio_dialect.md` (new).
- **Reasoning:** a real 3D wavelet decomposition of room geometry is
  research-grade complexity. Point cloud + radial bucketing is simple,
  small, and good enough for the diffuse late tail plus a handful of
  explicit early reflections. 64k+ demos can revisit with richer
  spatial bases.

### CARVE's 3D scene representation is shared between audio and graphics

- **Source:** CARVE chat (SDF/raycasting analogy).
- **Affects:** `carve_design.md` (new), eventually
  `spine_graphics_dialect.md` (future).
- **Reasoning:** SDF, raycasting, and polar wavelet reverb share the
  same substrate (3D scene + query point + radial accumulation). One
  scene definition feeds both audio reverb IRs and visual rendering.
  Cross-domain reuse is exactly SPINE's reachability story; one RVV
  kernel can serve both purposes.

### IR interpolation across microphone positions is permitted

- **Source:** CARVE chat (linearity question).
- **Affects:** `spine_audio_dialect.md` (new).
- **Reasoning:** the wavelet transform is linear; convex combinations
  of valid IRs are valid IRs. For smooth listener motion through smooth
  geometry, interpolating between precomputed IRs at coarse listener
  grid points is perceptually correct. Trilinear or barycentric weights
  are fine.

---

## 2026-05-17 — Project-management workflow established

### Project documents are the canonical channel between chats

- **Source:** CARVE chat (coherence gap discussion).
- **Affects:** project-wide.
- **Reasoning:** chats cannot share state directly. Project files are
  the only shared substrate. Design decisions belong in project
  documents, not in chat history. The user uploads downloadable files
  from `/mnt/user-data/outputs/` into project files; new chats then see
  them automatically.

### Project-wide directives apply automatically to all chats

- **Source:** user request, CARVE chat.
- **Affects:** project-wide directives (added to the project's master
  instructions, not in document files).
- **Reasoning:** the workflow conventions need to be inherited by every
  chat without each chat having to discover them. Convention text lives
  in the project's master instructions; this log just records that the
  decision was made.

### Convention: one canonical document per subsystem

- **Source:** CARVE chat.
- **Affects:** all design documents.
- **Reasoning:** prevents drift. Each subsystem has exactly one document
  of record. Cross-references between documents are named and explicit.

### Convention: project index and decision log are mandatory

- **Source:** CARVE chat.
- **Affects:** `eno_project_index.md`, `eno_decision_log.md`
  (both new).
- **Reasoning:** the cheapest possible coherence mechanism. New chats
  read the index to know what exists and the log to know what was
  decided.

### Convention: chats end with a session summary listing uploads

- **Source:** CARVE chat.
- **Affects:** every chat with design content.
- **Reasoning:** the user uploads files manually; without an explicit
  list, files get lost. Every chat that produces or modifies documents
  ends with a session summary file listing what to upload.
