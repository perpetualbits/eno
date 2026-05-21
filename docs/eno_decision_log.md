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
