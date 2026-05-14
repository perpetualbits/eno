# lib/wavelet

The ENO wavelet library. Builds to `build/libwavelet.a`.

## Current state

- CDF 5/3 lifting transform (float32, in-place)
- WaveletSquare data structure: 4096-sample squares at 48 kHz, 13 bands
  (12 detail + 1 scaling), I/Q channels
- Arena allocator with save/restore for scene transitions
- Stamping primitive: time-shift with two-cell linear splat and I/Q phase
  rotation, gain, optional per-band gain
- Cross-square spill for stamps that extend past the end of a square
- 26-test suite covering structure, round-trip exactness, stamping,
  superposition, cross-square spill, pre-echo (negative delay), I/Q
  rotation, and band-frequency coverage

## Planned

- Daubechies-4 / Daubechies-8 (lifting form for both)
- Chirplet basis evaluator (Gaussian-windowed complex exponential)
- 2D wavelets (separable, then non-separable)
- 3D wavelets for volumetric effects
- Polar wavelets for reflector-bank reverbs
- RVV assembly kernels behind the existing C API

## Layout

```
include/wavelet.h     Public API.
src/wavelet.c         C reference implementation.
tests/test_wavelet.c  Test suite.
Makefile              Build and test.
```

## Build

```
make            Build libwavelet.a and the test binary.
make test       Run the test suite.
make riscv      Cross-compile for RISC-V.
make clean      Remove build/.
```

## Using from other libraries / productions

```c
#include "wavelet.h"
```

Link `lib/wavelet/build/libwavelet.a` and `-lm`.
