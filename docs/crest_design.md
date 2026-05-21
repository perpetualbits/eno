# CREST — Coefficient-domain transform library

**Subsystem:** CREST
**Project:** Epsilon Null Operation (ε₀)
**Document:** `crest_design.md`
**Status:** working draft v0.1 (2026-05-18)
**Canonical location:** project files

---

## 0. Purpose of this document

This is the single design document for CREST. It is re-entrant: you
can return to it after weeks away and recover the design intent without
reading chat history.

CREST is the wavelet and coefficient-domain transform library for ε₀.
It is the mathematical foundation that every other audio, graphics, and
spatial subsystem builds on. It does not produce sound, render pixels,
or author SPINE entities — it provides the transforms and coefficient-
space primitives that those subsystems use.

Readers:

- **This chat** — implements CREST.
- **CARVE** — uses CREST for fitting, hand-tuning, and 3D scene
  transforms. See `carve_design.md` §2.6, which reserves a named
  cross-reference for when CREST came online.
- **NERVE** — uses CREST for runtime rendering of audio segments and
  wavelet-domain graphics effects.
- **Productions** (e.g. Desert Monument) — use CREST indirectly through
  `lib/siftr`, `lib/fx`, and `lib/gfx`.

---

## 1. Name and register

**CREST.** One syllable. Five letters. A concrete noun: the crest of a
wave — the peak, the visible form of the frequency-time structure that
wavelet analysis reveals. Fits the project naming register alongside
SPINE, NERVE, CARVE, SMOLR.

The name is not an acronym. Do not expand it.

---

## 2. What CREST provides

CREST is organized into four modules, each a separate source file and
eventually a separate RVV-optimized assembly companion:

```
crest_core      WaveletSquare, Arena, band layout, float32 CDF 5/3.
                The already-working foundation. Renamed from lib/wavelet.

crest_bases     Forward and inverse transforms for each audio.basis.*
                family: Daubechies, chirplet, Morlet, Gabor,
                damped exponential, formant stack, noise, impulse.
                Each basis is a self-contained forward/inverse pair
                sharing the WaveletSquare storage type.

crest_2d        2D wavelet transforms for terrain, sand, smoke, and
                2D graphics fields. Separable tensor product of 1D
                transforms over 2D arrays. Coefficient-domain verbs
                (stamp, scale, diffuse) extended to 2D grids.

crest_3d        3D wavelet transforms for volumetric geometry and
                density fields. Used for cliff faces with undercuts,
                cave mouths, skull-like hollow features — any geometry
                that cannot be expressed as a heightmap. Also used for
                volumetric reverb field estimation.
```

What CREST does **not** do:

- Synthesis scheduling (that is `lib/siftr`).
- Audio effects chains (that is `lib/fx`).
- WAV I/O (that is `lib/io`).
- SPINE authoring or emission (that is CARVE).
- Runtime demo orchestration (that is NERVE).
- Visualization UI (that is CARVE's node-graph editor).

---

## 3. The core data structure: WaveletSquare

The `WaveletSquare` is CREST's primary storage unit. It is already
implemented and tested in `crest_core`.

### 3.1 1D square (audio)

```
SQUARE_SAMPLES = 4096  samples at 48 000 Hz = ~85.3 ms
WAVELET_LEVELS = 12    detail bands
TOTAL_BANDS    = 13    (12 detail + 1 scaling)
IQ_CHANNELS    = 2     (I = in-phase, Q = quadrature)
```

Each square is 2 × 4096 × 4 bytes = **32 KB**. 256 squares = 8 MB,
well within the K1/K3 memory budget.

Band layout (finest to coarsest):

| Band | Cells | Cell width | Time width  | Freq range (approx)  |
|------|-------|------------|-------------|----------------------|
|    0 |  2048 |          2 |    41.7 µs  | 12 000–24 000 Hz     |
|    1 |  1024 |          4 |    83.3 µs  |  6 000–12 000 Hz     |
|    2 |   512 |          8 |   166.7 µs  |  3 000–6 000 Hz      |
|    3 |   256 |         16 |   333.3 µs  |  1 500–3 000 Hz      |
|    4 |   128 |         32 |   666.7 µs  |    750–1 500 Hz      |
|    5 |    64 |         64 |    1.33 ms  |    375–750 Hz        |
|    6 |    32 |        128 |    2.67 ms  |    188–375 Hz        |
|    7 |    16 |        256 |    5.33 ms  |     94–188 Hz        |
|    8 |     8 |        512 |   10.67 ms  |     47–94 Hz         |
|    9 |     4 |       1024 |   21.33 ms  |     23–47 Hz         |
|   10 |     2 |       2048 |   42.67 ms  |     12–23 Hz         |
|   11 |     1 |       4096 |   85.33 ms  |      6–12 Hz (detail)|
|   12 |     1 |       4096 |   85.33 ms  |       0–6 Hz (scaling)|

The I/Q pair represents the analytic signal. For CDF 5/3 (the
default, non-analytic basis), Q is simply a second independent channel
carrying the right audio channel. For chirplet and Morlet bases, I and
Q carry the real and imaginary parts of the complex coefficient, and
phase progression appears as rotation in the (I, Q) plane.

### 3.2 2D square

A 2D wavelet square covers a spatial patch. The natural choice for
terrain is a 256×256 or 512×512 float32 grid transformed with a
separable 2D CDF 5/3 (one 1D transform per row, then per column).

```
SQUARE_2D_CELLS_X  configurable: 256, 512, 1024 (power of two)
SQUARE_2D_CELLS_Y  configurable: 256, 512, 1024
WAVELET_LEVELS_2D  log2(min(X, Y)) - 1
```

Memory: 512×512 × 4 bytes = 1 MB per 2D square. Multiple 2D squares
tile the full terrain.

### 3.3 3D square

A 3D wavelet square covers a volumetric region.

```
SQUARE_3D_X  configurable: 64, 128, 256 (power of two)
SQUARE_3D_Y  configurable: 64, 128, 256
SQUARE_3D_Z  configurable: 64, 128, 256
```

Memory: 128×128×128 × 4 bytes = 8 MB per 3D volume. This is tight on
the K1/K3 (4–8 GB RAM total, shared with graphics). Typical usage:
one or two 3D volumes per scene, covering distinct regions (a cliff
face, a cave interior). Not the entire world — large-scale geometry
uses heightmaps (2D) with 3D details injected locally.

**The 3D case for Desert Monument specifically:** a cliff face with
hollow, eye-socket-like features or a cave mouth shaped like a skull.
These features have:
- overhangs and undercuts (not expressible in a heightmap)
- interior volume (the hollow itself matters for reverb and for camera
  traversal)
- smooth large-scale form with sharp detail (exactly the wavelet
  frequency-space tradeoff)

A 3D wavelet volume provides: coarse bands for the large-scale cliff
shape, fine bands for surface texture and edge detail, independent
coefficient manipulation per scale for artistic control.

---

## 4. Module: crest_core (existing)

**Files:** `lib/crest/src/crest_core.c`, `lib/crest/include/crest.h`,
`lib/crest/tests/test_crest_core.c` (renamed from `wavelet.*` 2026-05-21).

**Status: implemented and tested (26 tests passing).**

### 4.1 What is done

- Arena allocator (64-byte aligned, save/restore for scene transitions).
- `WaveletSquare` structure with flat float32 storage and band pointer
  arrays.
- CDF 5/3 lifting transform (forward and inverse, float32, 12-level
  cascade). Round-trip error < 1e-5 for all tested signals.
- `stamp()` primitive: time-shift a source square into a destination
  square with gain, I/Q phase rotation, two-cell linear splat, per-band
  gain, and cross-square spill.
- `stamp_simple()` convenience wrapper.
- WAV I/O and slicing in `lib/io`.
- Timeline, voice, and mix bus in `lib/siftr`.
- BandGain, Reverb (reflector bank), Chorus in `lib/fx`.

### 4.2 CDF 5/3 lifting: the reference transform

CDF 5/3 is the default basis for audio because:

- Integer lifting steps (0.5× and 0.25× in the float version) —
  simple, fast, no irrational coefficients.
- Perfect reconstruction.
- Good time-frequency balance for general audio.
- The same transform used in lossless JPEG-2000.

**The lifting steps (float version):**

```
Predict:  d[n] -= 0.5  × (s[n] + s[n+1])
Update:   s[n] += 0.25 × (d[n-1] + d[n])
Boundary: symmetric mirror extension (x[len] = x[len-2]).
```

Inverse is exact reversal of predict and update, in reverse order.

**Why float32 and not integer:** CREST must support Daubechies, chirplet,
and Morlet bases which have irrational filter coefficients. Committing
to integer lifting would require separate code paths and cannot serve
those bases. Float32 gives 144 dB dynamic range (well above the 110 dB
audible ceiling) and maps directly to RVV `vfmul`/`vfmacc` lanes.
Integer lifting for CDF 5/3 was considered and rejected; see the
session history for the full chain of reasoning and the specific
overflow bugs that killed the int32 approach.

### 4.3 The stamp primitive

The stamp is the central synthesis and mixing operation. Everything
else is a sequence of stamps.

For each band b:
```
cell_width  = 2^(b+1) samples
cell_shift  = delay_samples / cell_width
k           = floor(cell_shift)          integer cell offset
f           = cell_shift - k             fractional (0..1)
phi         = 2π × f_center(b) × (f × cell_width) / SAMPLE_RATE
I' = I cos(φ) − Q sin(φ)                phase rotation
Q' = I sin(φ) + Q cos(φ)

dst[i+k]   += rotated × gain × (1 − f)  tap 0
dst[i+k+1] += rotated × gain × f        tap 1
```

The inner loop is structured as two passes (tap 0 then tap 1),
giving contiguous memory access in each pass — the RVV-friendly
shape.

Per-band gains (`use_per_band_gain = 1`) give stamp a built-in EQ
or damping model. The polar wavelet reverb uses this for frequency-
dependent air absorption.

---

## 5. Module: crest_bases (to be built)

Each `audio.basis.*` family from the SPINE audio dialect needs a
forward and inverse transform pair that writes to/reads from a
`WaveletSquare`. All share the same storage structure; they differ in
how they interpret the coefficients.

### 5.1 Basis contract

Every basis implementation provides:

```c
/* Forward: decompose samples into coefficients in sq->bands[iq].
 * Semantics match forward_cdf53 but the decomposition is basis-specific. */
void forward_<basis>(WaveletSquare *sq, int iq, const float *samples);

/* Inverse: reconstruct samples from sq->bands[iq].
 * Must be the exact left-inverse of forward_<basis> to within float rounding. */
void inverse_<basis>(const WaveletSquare *sq, int iq, float *samples);

/* Descriptor: name, parameter shape, RVV support status. */
const CrestBasisDesc *crest_basis_desc_<basis>(void);
```

The `CrestBasisDesc` struct:

```c
typedef struct {
    const char *name;           /* "cdf53", "db4", "chirplet", ... */
    int         n_params;       /* parameters per wavelet (beyond position) */
    int         iq_mode;        /* 0=mono storage, 1=analytic (I+Q pair) */
    int         rvv_ready;      /* 1 if RVV kernel exists */
} CrestBasisDesc;
```

### 5.2 Planned bases and status

| Basis id              | SPINE type                  | Priority | Status     | Notes |
|-----------------------|-----------------------------|----------|------------|-------|
| `cdf53`               | (default, not dialect-named) | done     | ✓ done     | The reference basis; descriptor in `crest_core.c` |
| `db4`                 | —                           | high     | ✓ done     | Daubechies-4; `src/crest_bases.c`, 12 tests passing |
| `morlet`              | `audio.basis.morlet`        | high     | to do      | Complex Gabor; onset transients |
| `chirplet`            | `audio.basis.chirplet`      | high     | to do      | Linear-chirp Gaussian; cello body |
| `gabor`               | `audio.basis.gabor`         | medium   | to do      | Real-valued Morlet; cheaper |
| `damped_exp`          | `audio.basis.damped_exp`    | medium   | to do      | ESPRIT/Prony for release tails |
| `formant_stack`       | `audio.basis.formant_stack` | medium   | to do      | Vowel synthesis; stacked sinusoids |
| `noise_fricative`     | `audio.basis.noise_fricative`| low     | to do      | /s/, /f/, bow noise |
| `impulse`             | `audio.basis.impulse`       | low      | to do      | /k/, /t/, plucked-string click |

**Priority rationale:** Daubechies-4 is first because it improves on
CDF 5/3 for smooth signals (better frequency localization) and adds
the capability needed for noise-like sounds (water, wind, consonants
as discussed by the user). Chirplet is first among the audio dialect
bases because it is the right basis for sustained bowed or blown tones
— the primary instrument in Desert Monument.

### 5.3 Daubechies-4 (next to implement)

Daubechies-4 (D4) uses four tap filter coefficients derived from the
Daubechies vanishing-moment construction. Unlike CDF 5/3, D4 has
irrational coefficients — this is exactly why float32 is the right
representation.

The D4 scaling filter coefficients (h₀..h₃):

```
h0 = (1 + √3) / (4√2)  ≈  0.4829629131
h1 = (3 + √3) / (4√2)  ≈  0.8365163037
h2 = (3 - √3) / (4√2)  ≈  0.2241438680
h3 = (1 - √3) / (4√2)  ≈ -0.1294095226
```

The wavelet filter (g₀..g₃) is the alternating-sign reversal of h:

```
g0 =  h3, g1 = -h2, g2 =  h1, g3 = -h0
```

D4 has 2 vanishing moments (CDF 5/3 has 2 primal, 2 dual). It is
orthogonal rather than biorthogonal. The transform is not as simple
as the CDF 5/3 lifting steps — it requires a convolution-based
approach or the Mallat algorithm — but it achieves better frequency
localization, which matters for noise-like signals.

**When to prefer D4 over CDF 5/3:**
- Wind, rain, ocean: broadband noise benefits from D4's better
  frequency isolation.
- Consonants in speech and singing.
- Smooth slow-varying signals (tremolo body, sustained vowels): D4
  leaks less across bands.

**When to prefer CDF 5/3:**
- Transients and percussive attacks (better time localization).
- Any case where perfect integer reconstruction matters (none in
  this project — we are float32 throughout).
- When code simplicity matters more than basis quality.

### 5.4 Chirplet basis sketch

A chirplet is a Gaussian-windowed complex exponential with a linearly
varying instantaneous frequency:

```
ψ(t) = exp(−t²/2σ²) × exp(i(ω₀t + ½αt²))
```

where:
- `σ` is the Gaussian width (duration)
- `ω₀` is the center frequency
- `α` is the chirp rate (frequency change per unit time)

For the cello body segment, `α ≠ 0` captures the natural pitch drift
during a sustained bow stroke.

The chirplet basis is *not* a dyadic filter bank like CDF 5/3 or D4.
Instead, each coefficient is a 5-tuple `(scale, translate, amplitude,
phase, chirp_rate)` locating one chirplet atom in the time-frequency
plane. The forward transform is a sparse pursuit (matching pursuit or
OMP): greedily select the chirplet that best explains the residual,
subtract it, repeat.

This is the basis where CARVE's ML fitting (Tier 2, Python/GPU) does
the heaviest work. CREST provides:
- The chirplet atom evaluator `chirplet_atom(t, sigma, omega0, alpha)`.
- The sparse synthesis path (sum of chirplet atoms into time-domain
  samples) — this is NERVE's hot path at runtime.
- The coefficient storage layout in `WaveletSquare` bands for chirplet
  coefficients (packing the 5-tuples into the flat float32 storage).

CARVE's Tier 2 handles the analysis (fitting); CREST handles the
synthesis (decoding).

### 5.5 Morlet / Gabor sketch

Morlet is a chirplet with `α = 0` (no chirp rate). It is the natural
basis for onset transients: short, broadband bursts that occupy a small
time window across many frequency bands simultaneously.

The real-valued version (Gabor) is cheaper and sufficient for many
onset types. The complex version (Morlet) is needed when phase
information matters (vibrato, tremolo onset, string harmonics).

Storage: same as chirplet but 4-tuples `(scale, translate, amplitude,
phase)` — one fewer parameter per atom.

---

## 6. Module: crest_2d (to be built)

### 6.1 Purpose and use cases

2D wavelet transforms operate on float32 grids `W × H`. They are used
for:

- **Terrain:** a heightmap of the desert floor. CDF 5/3 in 2D gives
  multi-resolution terrain: coarse coefficients for the large-scale
  dunes, fine coefficients for sand ripple texture. The stamp primitive
  in 2D stamps a detail feature (a dune ridge, a crack) into the
  terrain grid.
- **Sand / smoke / dust fields:** 2D density grids. Diffuse and
  stamp verbs create physically plausible-looking motion.
- **2D graphics fields:** any per-pixel quantity that benefits from
  multi-resolution representation.

### 6.2 Separable transform

The 2D CDF 5/3 is separable: apply the 1D transform to each row,
then to each column (or vice versa — the order does not matter for
reconstruction). This is O(W×H) time and reuses the 1D kernel exactly.

```
forward_cdf53_2d(grid, W, H):
  for each row y:   forward_cdf53_row(grid[y*W .. y*W+W])
  for each col x:   forward_cdf53_col(grid[x, x+W, x+2W, ...])
```

The 2D coefficient layout after the separable transform is the
standard quadrant decomposition:

```
  LL | LH          LL = low-freq × low-freq (scaling approximation)
  ---+---          LH = low-freq × high-freq (horizontal edges)
  HL | HH          HL = high-freq × low-freq (vertical edges)
                   HH = high-freq × high-freq (diagonals)
```

After N levels, the LL quadrant is subdivided again, producing a
recursive quad-tree structure. This is the standard 2D DWT.

### 6.3 2D data structure: WaveletGrid2D

```c
typedef struct {
    float   *data;          /* W × H float32, row-major          */
    int      W, H;          /* dimensions (power of two each)    */
    int      levels;        /* transform depth                   */
    int      grid_index;    /* for tiling: which patch           */
} WaveletGrid2D;
```

Memory cost: 512 × 512 × 4 = 1 MB. Typical terrain uses a 4 × 4
tile grid of 512 × 512 patches = 16 MB. Fits on the K1/K3.

### 6.4 2D stamp verb

Analogous to the 1D stamp: place a feature (a ridge, a crater, a sand
ripple pattern) into a grid at a given 2D offset with a gain. The
feature is itself a `WaveletGrid2D` containing the feature's
coefficient structure.

```c
void stamp2d(WaveletGrid2D *dst,
             const WaveletGrid2D *src,
             float offset_x, float offset_y,
             float gain, float scale);
```

The `scale` parameter zooms the feature: a dune at 2× scale has the
same spectral shape but spans twice the spatial area.

### 6.5 2D diffuse verb

Distributes energy from each coefficient cell into its neighbors.
Simulates the physical spreading of sand or smoke. In coefficient space,
this is a per-band spatial low-pass: fine-band coefficients diffuse
quickly (sand ripples smooth out), coarse-band coefficients diffuse
slowly (large dune forms persist).

```c
void diffuse2d(WaveletGrid2D *grid, float dt, float rate_per_band[N_LEVELS]);
```

---

## 7. Module: crest_3d (to be built)

### 7.1 Purpose and use cases

3D wavelet transforms operate on float32 volumes `W × H × D`. They are
used for:

- **Volumetric cliff geometry:** a cliff face with overhangs, undercuts,
  and hollow features (eye-socket caves, skull-like formations). The
  volume stores a signed distance field (SDF) or an occupancy field.
  Wavelet bands capture the large-scale cliff shape (coarse) and the
  fine surface texture and hollow detail (fine). Hollow features appear
  as coefficient clusters at the right scale in the interior volume.
- **Cave interiors:** a cave mouth, tunnel, or chamber. The volume
  stores the air/rock boundary. NERVE's ray marcher queries the SDF;
  CARVE's IR baker uses the volume geometry for reverb modeling.
- **Smoke / dust / sand in 3D:** volumetric density fields for visual
  effects in the desert storm.
- **Volumetric reverb field:** the impulse response field indexed by
  listener position. A 3D grid of IR samples; wavelet compression reduces
  the storage cost significantly for smooth-varying rooms.

### 7.2 Why 3D and not just 2D + height displacement

A heightmap `z = f(x, y)` can represent a terrain surface but:
- Cannot represent overhangs (two z-values for the same x, y).
- Cannot represent the interior of a hollow (the eye socket is a
  closed cavity).
- Cannot represent a tunnel (topology change: a hole through a solid).

A 3D signed distance field (SDF) stored in a wavelet volume handles
all of these. The wavelet compression is especially effective because
SDF values vary slowly in most of the volume and sharply only near
the surface — exactly the structure that sparse wavelet representations
exploit.

**Concretely for Desert Monument:** the cliff face is large (say
200m × 80m × 60m). At a grid resolution of 128³, one voxel = 1.5m ×
0.6m × 0.5m — enough for NERVE's ray marcher. The wavelet compression
at 3–4 significant bands could store the whole cliff in a few hundred
KB before entropy coding.

### 7.3 Separable 3D transform

Like the 2D case, the 3D CDF 5/3 is separable: apply the 1D transform
to each row (X), then each column (Y), then each depth slice (Z).

The coefficient layout after N levels is the standard 3D octant
decomposition (8 sub-bands per level: LLL, LLH, LHL, LHH, HLL, HLH,
HHL, HHH).

### 7.4 3D data structure: WaveletVolume3D

```c
typedef struct {
    float  *data;           /* W × H × D float32, row-major (x+W*(y+H*z)) */
    int     W, H, D;        /* dimensions (power of two each)              */
    int     levels;         /* transform depth                             */
    int     volume_index;
} WaveletVolume3D;
```

Memory: 128³ × 4 = 8 MB. One or two volumes per scene. Tight but
feasible on K1/K3.

### 7.5 3D stamp and diffuse verbs

Same pattern as 2D: place a volumetric feature (a hollow, a protrusion,
a cave mouth template) into a volume at a 3D offset with gain and
scale. Diffuse smooths the volume over time (for smoke, density fields).

---

## 8. Polar wavelet basis (future, related to fx reverb)

The polar wavelet basis decomposes a 2D or 3D field in polar/spherical
coordinates rather than Cartesian. It is used for:

- **Polar wavelet reverb** (audio dialect `audio.effect.polar_wavelet_reverb`):
  the impulse response of a room, indexed by direction and distance from
  the source. Sparse in the polar domain because most energy arrives
  from a small number of directions.
- **Spherical harmonic audio** (Ambisonics-adjacent): encoding
  directional audio in a rotationally-invariant coefficient basis.

The polar wavelet basis is more specialized than the Cartesian 2D/3D
bases and will be developed when the polar wavelet reverb effect is
implemented in `lib/fx`. CREST provides the underlying transform;
`lib/fx` builds the reverb on top.

The boundary between CREST and `lib/fx` for the polar reverb:
- **CREST** provides: the polar forward and inverse transform,
  coefficient-domain correlation (for computing IRs from geometry).
- **lib/fx** provides: the reverb effect that calls into CREST,
  combines it with a listener position, and stamps results into the mix
  bus.

---

## 9. Repository location

The library lives at `lib/crest/`. The directory rename from `lib/wavelet/`
was completed 2026-05-21 as part of the Claude Code handoff migration.

Internal file names (`wavelet.h`, `wavelet.c`, `test_wavelet.c`,
`libwavelet.a`) retain the `wavelet` prefix for now. The next crest_bases
work session is the natural moment to rename them to `crest.h`,
`crest_core.c`, `test_crest_core.c`, `libcrest.a` along with the first
`#include "crest.h"` consumers in `lib/siftr` and `lib/fx`.

---

## 10. Build and dependency structure

```
crest_core  (no dependencies within CREST)
    │
    ├── crest_bases   (depends on crest_core)
    ├── crest_2d      (depends on crest_core)
    └── crest_3d      (depends on crest_core, optionally crest_2d)

lib/io      (depends on crest_core)
lib/siftr   (depends on crest_core, lib/io)
lib/fx      (depends on crest_core, crest_bases, lib/siftr, lib/io)
lib/gfx     (depends on crest_core, crest_2d, crest_3d)

CARVE       (depends on all CREST modules)
NERVE       (depends on crest_core, crest_bases — subset per reachability)
```

Each CREST module builds to a static `.a` archive. Productions link
only the archives they use; SMOLR handles dead-code elimination at the
atom level for the final binary.

---

## 11. RVV acceleration plan

The hot loops in CREST are:

1. **CDF 5/3 forward/inverse** (crest_core): the predict and update
   steps operate on interleaved even/odd samples. RVV approach: strided
   `vle32.v` loads of even and odd elements, vectorized arithmetic,
   strided `vse32.v` stores. The two-pass structure (predict then
   update) has no cross-iteration dependency within a pass — ideal for
   wide SIMD.

2. **Stamp inner loop** (crest_core): two passes of contiguous
   accumulate. Each pass: `vle32.v` (src), `vfmul.vf` (× gain×weight),
   `vle32.v` (dst), `vfadd.vv`, `vse32.v`. About 5 instructions per
   vector of 4–8 floats.

3. **D4 filter convolution** (crest_bases): 4-tap FIR convolution in
   the Mallat algorithm. `vfmacc.vf` with 4 scalar filter coefficients.

4. **2D separable transform** (crest_2d): row pass then column pass,
   each identical to the 1D case. Column pass has non-unit stride
   (accessing every W-th element); `vle32.v` with stride handles this.

5. **3D separable transform** (crest_3d): three passes (X, Y, Z). Each
   identical to 2D. The Z pass has stride W×H.

The RVV assembly kernels will be written after each C reference
implementation passes its test suite. The C version is retained as a
reference and as a fallback for non-RVV targets (x86_64 dev machines,
the early phases of CARVE).

The kernel naming convention:
```
crest_fwd_cdf53_rvv_f32()   — forward CDF 5/3, float32, RVV
crest_stamp_rvv_f32()       — stamp inner loop, float32, RVV
crest_fwd_d4_rvv_f32()      — forward D4, float32, RVV
...
```

Each kernel has a corresponding C scalar version and a test that
verifies their outputs match to within 1 ULP.

---

## 12. Testing strategy

### 12.1 What already exists (26 tests in test_crest_core.c)

- Band size and pointer layout.
- Arena alignment and save/restore.
- CDF 5/3 round-trip for silence, impulse, sines at multiple frequencies,
  DC, full-scale Nyquist signal.
- Energy preservation.
- Stamp: zero delay, integer delay, fractional delay, gain scaling,
  superposition, cross-square spill, null dst_next, negative delay,
  I/Q phase rotation.
- Band frequency isolation for 440 Hz and 8 kHz.

### 12.2 Tests to add per module

**crest_bases:**
- D4 forward/inverse round-trip (multiple signals, error < 1e-4).
- D4 vs CDF 5/3: D4 has better frequency isolation for smooth signals
  (quantify with a measure of energy leakage across bands).
- Chirplet: atom evaluator produces correct shape (Gaussian envelope,
  linear frequency sweep, verify via spectrogram).
- Chirplet synthesis: N atoms → samples → within residual tolerance.
- Morlet: complex analytic signal properties (instantaneous frequency
  and envelope extraction).
- Formant stack: vowel-like signal synthesizes recognisable formant
  pattern.

**crest_2d:**
- 2D CDF 5/3 round-trip for flat field, single impulse, sine plane wave.
- Stamp2D: feature placed at correct offset, energy at expected location.
- Diffuse2D: energy spreads over time, total power approximately
  conserved.

**crest_3d:**
- 3D CDF 5/3 round-trip for constant volume, impulse at centre.
- Stamp3D: spherical feature placed at offset.
- SDF representation: a sphere SDF survives forward/inverse within
  tolerance for NERVE's ray-marcher use case.

### 12.3 Cross-module integration tests

- Load a WAV file → decompose into 1D squares → reconstruct → save WAV.
  Round-trip error < 1 LSB at 16-bit PCM (already passing via lib/io
  and lib/siftr tests).
- Render a CARVE-like workflow: sine atom → timeline → mix bus → reverb
  → WAV. Verify audible content and correct reverb tail (passing via
  lib/fx integration test).
- 2D terrain: generate noise field → 2D CDF 5/3 → stamp a dune feature
  → inverse → verify heightmap contains feature at expected location.

---

## 13. Open questions

1. **D4 vs other Daubechies orders.** D4 (two vanishing moments) may
   not be sufficient for very smooth signals. D6 or D8 have more
   vanishing moments and better frequency isolation, at the cost of
   longer filters (6 or 8 taps). Decision: start with D4, measure
   residuals on real instrument recordings, escalate if needed. D6 is
   the likely landing point for the chirp body segments.

2. **Chirplet pursuit algorithm.** Matching pursuit vs OMP
   (orthogonal matching pursuit) vs continuous-domain NLS (nonlinear
   least squares). Matching pursuit is simpler; OMP is more accurate;
   NLS is best for the chirp-rate parameter but expensive. Decision:
   deferred to CARVE Phase 2 when the first real fits run. Lean toward
   OMP as a starting point.

3. **WaveletSquare storage for chirplet coefficients.** Chirplet atoms
   are 5-tuples `(scale, translate, amplitude, phase, chirp_rate)`;
   they do not map naturally onto the dyadic band structure of
   `WaveletSquare`. Two options: (a) store chirplet atoms in a separate
   flat array and leave `WaveletSquare` for dyadic bases only; (b)
   pack atoms into the `WaveletSquare` bands by binning their scale
   parameter. Option (b) lets NERVE use the same storage and rendering
   paths. Decision: deferred to when chirplet is implemented.

4. **2D/3D square size defaults.** The proposed 512×512 (2D) and 128³
   (3D) are educated guesses. The right sizes depend on the spatial
   resolution needed for Desert Monument's cliff and terrain geometry,
   which is not yet modeled. Decision: prototype with small sizes
   (128×128 2D, 64³ 3D) first; measure and resize when geometry is
   known.

5. **Polar wavelet basis: spherical harmonic decomposition or custom.** The
   IR can be expanded in spherical harmonics (a well-studied basis for
   directional audio) or in a custom polar wavelet. Spherical harmonics
   are a natural choice (tooling exists) but don't capture high-frequency
   directional detail compactly. A radial wavelet + SH angular basis
   is a research-level combination. Decision: deferred until the polar
   wavelet reverb is the active work item. Current lean: use SH up to
   order 4 for the angular part, 1D CDF 5/3 for the radial part.

6. **Repository migration timing.** ~~When does `lib/wavelet/` become
   `lib/crest/`?~~ Resolved 2026-05-21: directory renamed as part of
   the Claude Code handoff migration. ~~Internal file renames deferred
   to crest_bases work session.~~ Resolved 2026-05-21 (crest_bases
   session): `wavelet.h` → `crest.h`, `wavelet.c` → `crest_core.c`,
   `test_wavelet.c` → `test_crest_core.c`, `libwavelet.a` → `libcrest.a`.

---

## 14. Relationship to other subsystems

| Subsystem | Uses CREST for | Does not use CREST for |
|-----------|----------------|------------------------|
| CARVE     | All transforms (fitting, hand-tuning, 2D/3D scene work). Primary consumer of crest_bases. | SPINE emission, node-graph UI, ML fitting (Tier 2 Python). |
| NERVE     | Inverse transforms for audio playback. Subset of crest_bases determined by reachability. Polar wavelet reverb via lib/fx. | SPINE parsing, scheduling, OS interaction. |
| lib/siftr | crest_core: WaveletSquare, stamp, Arena, CDF 5/3. | crest_bases, crest_2d, crest_3d. |
| lib/fx    | crest_core: stamp (for reverb reflector bank). crest_bases: polar basis (when implemented). | Audio effect scheduling. |
| lib/gfx   | crest_2d: terrain, sand, smoke fields. crest_3d: volumetric cliff/cave geometry. | Audio transforms. |
| lib/io    | crest_core: WaveletSquare for audio slicing. | All other modules. |
| SMOLR     | Does not call CREST. Operates on the final binary that contains CREST code. | — |
| SPINE     | Does not call CREST. Defines the `audio.basis.*` types that CREST implements. | — |

---

## 15. One-page reminder

```
CREST is the transform library of ε₀.

PROVIDES:
  crest_core   — WaveletSquare, Arena, CDF 5/3, stamp, mix bus.
                 Done. 26 tests passing.
  crest_bases  — D4, chirplet, Morlet, Gabor, damped-exp, formant,
                 noise, impulse. Each basis: forward + inverse pair.
                 Shared storage: WaveletSquare. Builds to libcrest_bases.a.
  crest_2d     — Separable 2D CDF 5/3. WaveletGrid2D. Stamp, diffuse.
                 For terrain, sand, smoke, 2D graphics fields.
  crest_3d     — Separable 3D CDF 5/3. WaveletVolume3D. Stamp, diffuse.
                 For volumetric cliff/cave geometry, SDF fields.

DOES NOT PROVIDE:
  Synthesis scheduling (lib/siftr)
  Audio effects chains (lib/fx)
  WAV I/O (lib/io)
  SPINE authoring (CARVE)
  Runtime demo orchestration (NERVE)
  Visualization (CARVE editor)

FLOAT32 THROUGHOUT.
  Every coefficient is float32.
  RVV kernels use vfmul / vfadd / vfmacc.
  Integer lifting was considered and rejected (overflows for
  irrational-coefficient bases; see session history).

CALLERS:
  CARVE: all modules.
  NERVE: crest_core + subset of crest_bases (per reachability).
  lib/fx: crest_core (stamp-based reverb) + polar basis (future).
  lib/gfx: crest_2d + crest_3d.
  lib/siftr, lib/io: crest_core only.
```

---

*Document history:*
*v0.1 — 2026-05-18. Subsystem initiated, named CREST. Scope defined:*
*four modules, all basis families from audio dialect, 2D and 3D.*
*carve_design.md §2.6 now has a named cross-reference: CREST.*
