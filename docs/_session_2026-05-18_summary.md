# Session Summary — 2026-05-18 (wavelet library / CREST)

**Chat topic:** Naming and design document for the wavelet transform library.

---

## Files to upload

Upload all three files to project files. The session summary itself
does not need to be uploaded.

### 1. `crest_design.md` — **NEW DOCUMENT**

The canonical design document for CREST, the wavelet transform library.
This resolves the placeholder in `eno_project_index.md` §8 and the
unnamed dependency in `carve_design.md` §2.6.

Contents:
- Subsystem name: **CREST** (five letters, one syllable, "crest of a wave").
- Four modules: `crest_core` (done), `crest_bases` (to build),
  `crest_2d` (to build), `crest_3d` (to build).
- Full scope: 1D audio bases (CDF 5/3 done; D4, chirplet, Morlet,
  Gabor, damped-exp, formant stack, noise, impulse planned), 2D
  wavelet transforms for terrain/sand/smoke, 3D wavelet transforms
  for volumetric cliff/cave geometry and SDF fields.
- Design rationale for float32 (integer lifting rejected — see §4.2).
- Stamp primitive description and its RVV-friendly two-pass structure.
- Per-module data structures (WaveletSquare, WaveletGrid2D,
  WaveletVolume3D).
- Repository migration plan (lib/wavelet/ → lib/crest/).
- RVV acceleration plan per hot loop.
- Testing strategy (existing 26 tests + planned additions per module).
- 6 open questions.
- Relationship table to all other subsystems.
- One-page reminder.

### 2. `eno_project_index.md` — **UPDATED**

Added CREST as a new entry in §7 (between CARVE and the project-wide
section). Removed CREST from §8 (future documents placeholder — it is
now real). Added `crest_design.md` as a named cross-reference. Minor
cleanup.

### 3. `eno_decision_log.md` — **UPDATED**

Added a new section "2026-05-18 — CREST decisions" with entries for:
- Subsystem named CREST.
- Float32 throughout; integer lifting rejected.
- Four modules (core, bases, 2d, 3d); 3D justified by hollow/undercut
  geometry needs.
- WaveletSquare as shared storage across all 1D bases.
- Stamp lives in crest_core (not lib/synth).
- Repository migration deferred.
- Polar basis in CREST, polar reverb effect in lib/fx.
- Next items: D4 then chirplet.

Also clarified the CARVE entry: "depends on CREST" now names CREST
instead of "a wavelet library subsystem not yet named".

---

## Documents that need a cross-reference update (cannot upload directly)

`carve_design.md` §2.6 currently ends with "when the library subsystem
comes online, this section gets a named cross-reference." That condition
is now met. The section should read:

> CARVE depends on **CREST** (`crest_design.md`), the wavelet transform
> library for ε₀. CREST provides forward and inverse transforms in each
> `audio.basis.*` family, coefficient-space arithmetic, 2D and 3D
> wavelet transforms, and (eventually) RVV-accelerated kernels.

This edit requires opening the CARVE chat or uploading a revised
`carve_design.md`. It is low urgency — the index and decision log
already record the relationship.

---

## Current CREST implementation status

Working, tested, located in `lib/wavelet/` (not yet renamed):
- `crest_core`: WaveletSquare, Arena, CDF 5/3, stamp. 26 tests.
- `lib/io`: AudioBuffer, WAV I/O, square slicing. 12 tests.
- `lib/synth`: Timeline, voices, atoms, mix bus. 11 tests.
- `lib/fx`: BandGain, reverb reflector bank, chorus, FX chain. 9 tests.

Total: 58 tests passing.

Next implementation work in CREST: Daubechies-4 lifting (crest_bases).
