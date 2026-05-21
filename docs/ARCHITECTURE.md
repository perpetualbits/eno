# ENO Architecture

This document describes how the ENO codebase is organised and why.

## Top-level layout

```
lib/        Reusable libraries. Each builds to a .a static library.
tools/      Host-side tools (don't run on the demo target unless noted).
prods/      Demoscene productions. Each is self-contained and links libs.
docs/       Design notes, theory, post-mortems.
third_party/  Vendored external code (libsndfile, SDL2 headers, etc.).
```

## Principles

1. **Monorepo, not submodules.** Productions share a fast-moving library
   core. Submodules add friction here. Each production pins a commit if it
   needs reproducibility for a release.

2. **One Makefile per directory.** Subdirs are independently buildable so
   you can iterate fast on one part without rebuilding the world.

3. **Libraries are static .a archives.** No shared libraries internally.
   Final demo binaries link statically (except for system libraries like
   libm, libc, libGL, SDL2 — those are dynamic, as is normal for Linux
   demoscene productions).

4. **No dependencies pointing upward.** Productions depend on libs.
   Tools may depend on libs. Libs depend on each other in a strict order:
   core → crest → io → siftr → fx → gfx. No cycles.

5. **C11 for portability + asm where it matters.** The prototype is plain
   C. Performance-critical kernels (CDF 5/3 lifting, stamping inner loop)
   will be replaced with RVV assembly behind the same API. The C version
   stays as a reference and fallback.

## Library responsibilities

### lib/core
- Arena allocator
- Fixed-size containers (no malloc)
- Math primitives (fast sin/cos tables, fixed-point helpers if needed)
- Logging / assertions for development builds

### lib/crest — CREST
- 1D wavelets: CDF 5/3, Daubechies-N (planned)
- Chirplets (planned)
- 2D and 3D wavelet transforms (planned)
- Polar wavelets for reflector banks (planned)
- WaveletSquare data structure and arena integration

### lib/io
- WAV file I/O via libsndfile
- Raw asset bundling for the final demo (turning files into linkable blobs)
- Possibly OGG decoding for full-length audio in dev builds

### lib/siftr — SIFTR
- Stamp-based synthesis built on lib/crest
- Envelope generators
- Oscillator banks
- Voice management

### lib/fx
- Reverb (reflector-bank model using polar wavelets)
- Chorus, flanger via stamp clusters
- Filters

### lib/gfx
- GLSL helpers, shader loading
- SDF primitives for cave/monument geometry
- Post-processing (bloom, tone-mapping)
- Wavelet-domain visual effects (sand, smoke, terrain)

## Tool responsibilities

### tools/carve — CARVE
The offline authoring tool for instrument trajectory templates and 3D scene
definitions. ML fitting, node-graph UI, IR baking for polar wavelet reverb.
See `carve_design.md` for the full design.

### tools/glint — GLINT
GLSL shader minifier and packer for size-coded productions.

### tools/smolr
Planned: Linux/RISC-V executable packer, analogous to crinkler (Windows)
or smol (Linux/x86). Segher's territory.

## Production structure

Each production under `prods/` has:
```
prods/<name>/
├── src/        Production-specific C/asm code
├── assets/     Source assets (audio, textures, etc.)
├── docs/       Storyboard, design notes
└── Makefile    Builds linking against ../../lib/*
```

## Build flow

```
make           Everything in dependency order.
make libs      Just the libraries.
make tools     Libraries + tools.
make prods     Libraries + productions.
make test      All test suites (each library has its own).
make riscv     Cross-compile everything for RISC-V.
make clean     Wipe build artifacts.
```

## Adding new code

- New library: create `lib/<name>/`, add a Makefile, add `<name>` to LIBS in
  the top-level Makefile. Document its responsibility here.
- New tool: same pattern under `tools/`.
- New production: `prods/<slug>/`. Its Makefile should reference libraries
  via `../../lib/<name>/include` and `../../lib/<name>/build/lib<name>.a`.

## Current library dependency chain

```
lib/core  ←  lib/crest  ←  lib/io  ←  lib/siftr  ←  lib/fx  ←  lib/gfx
```
