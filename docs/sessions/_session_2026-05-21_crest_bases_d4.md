# Session: CREST crest_bases — file renames + Daubechies-4
**Date:** 2026-05-21
**Branch:** main

---

## Objective

1. Rename the internal `lib/crest/` files from their provisional `wavelet.*`
   names to proper CREST names.
2. Implement the first `crest_bases` module entry: Daubechies-4 (D4).

---

## Part 1: File renames

| Old path | New path |
|----------|----------|
| `lib/crest/include/wavelet.h` | `lib/crest/include/crest.h` |
| `lib/crest/src/wavelet.c` | `lib/crest/src/crest_core.c` |
| `lib/crest/tests/test_wavelet.c` | `lib/crest/tests/test_crest_core.c` |
| build target `libwavelet.a` | build target `libcrest.a` |

### Changes within the renamed files

- `crest.h`: header guard `WAVELET_H` → `CREST_H`; added `CrestBasisDesc` struct and `crest_basis_desc_cdf53()` declaration.
- `crest_core.c`: `#include "wavelet.h"` → `#include "crest.h"`; added `crest_basis_desc_cdf53()` implementation.
- `test_crest_core.c`: updated `#include` and the title string in `main()`.

### Makefile rewrite (`lib/crest/Makefile`)

- Targets now build `libcrest.a` from both `crest_core.o` and `crest_bases.o`.
- Separate test binaries: `test_crest_core` and `test_crest_bases`.
- `make test` runs both suites.
- RISC-V cross-build updated to match new names.

---

## Part 2: D4 implementation

### New files

| File | Contents |
|------|----------|
| `lib/crest/include/crest_bases.h` | `forward_d4`, `inverse_d4`, `validate_roundtrip_d4`, `crest_basis_desc_d4` declarations |
| `lib/crest/src/crest_bases.c` | D4 implementation + `crest_basis_desc_d4()` |
| `lib/crest/tests/test_crest_bases.c` | 12 tests across 4 sections |

### D4 algorithm

Implemented as the Mallat convolution form (not lifting) because D4's four
irrational taps do not factor into a clean two-step lifting scheme.

**Filter coefficients:**
```
h = [0.4829629131, 0.8365163037, 0.2241438680, -0.1294095226]
g = [h3, -h2, h1, -h0] = [-0.1294..., -0.2241..., 0.8365..., -0.4829...]
```

**Forward one level (polyphase gather, periodic extension):**
```
for n = 0..N/2-1:
    s[n] = h0*x[2n] + h1*x[2n+1] + h2*x[2n+2] + h3*x[2n+3]
    d[n] = g0*x[2n] + g1*x[2n+1] + g2*x[2n+2] + g3*x[2n+3]
```

**Inverse one level (transpose scatter — valid because D4 is orthogonal):**
```
x[n] = 0
for k = 0..N/2-1:
    x[(2k+j) mod N] += h[j]*s[k] + g[j]*d[k]   for j=0,1,2,3
```

A single static scratch buffer `d4_tmp[SQUARE_SAMPLES]` holds the temporary
output for each level. The 12-level cascade follows the same structure as
`forward_cdf53`/`inverse_cdf53` in `crest_core.c`.

### D4 vs CDF 5/3 isolation note

The design doc's claim that "D4 has better frequency isolation" applies to
broadband/smooth signals in the infinite-length theory. For short pure
sinusoids, CDF 5/3's symmetric lifting can slightly match or beat D4's
peak-band energy fraction. The comparison tests use ±5% tolerance and include
a comment explaining this. See decision log 2026-05-21.

### CrestBasisDesc

Added `CrestBasisDesc` struct to `crest.h`:
```c
typedef struct {
    const char *name;
    int         n_params;
    int         iq_mode;
    int         rvv_ready;
} CrestBasisDesc;
```

Both `crest_basis_desc_cdf53()` and `crest_basis_desc_d4()` return static
descriptors.  Future bases follow the same pattern.

---

## Test results

| Suite | Result |
|-------|--------|
| `test_crest_core` | **26/26 passed** |
| `test_crest_bases` | **12/12 passed** |

### crest_bases test sections

1. D4 Round-trip: silence, impulse, 440 Hz sine, 80 Hz sine, DC, alternating ±1.0 — all < 1e-4 max error
2. D4 Frequency Isolation: 440 Hz in bands 4–6, 8 kHz in bands 0–2
3. D4 vs CDF 5/3 Comparison: both comparable within 5% for 440 Hz and 100 Hz sines
4. Basis Descriptors: `crest_basis_desc_d4` and `crest_basis_desc_cdf53` return correct non-null descriptors

---

## Design doc updates

- `docs/crest_design.md` §4: updated file names from `wavelet.*` to `crest_core.*`.
- `docs/crest_design.md` §5.2: marked `db4` status as done.
- `docs/crest_design.md` §13.6: marked internal renames as resolved.

---

## What was NOT in scope

- Chirplet, Morlet, Gabor, damped_exp, formant_stack — next bases to implement.
- crest_2d, crest_3d — planned but not started.
- RVV kernels — none yet; `rvv_ready = 0` in all descriptors.
