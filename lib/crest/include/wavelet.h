#ifndef WAVELET_H
#define WAVELET_H

#include <stdint.h>
#include <stddef.h>
#include <assert.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ---------------------------------------------------------------------------
 * Numeric representation
 *
 * All coefficients are float32. This is a deliberate choice for a library
 * that must span CDF 5/3, Daubechies, chirplets, polar wavelets, and 2D/3D
 * tensor extensions — integer fixed-point was workable for CDF 5/3 alone
 * but breaks down for irrational filter coefficients and complex-exponential
 * bases. Float32 unifies all of these and maps cleanly onto RVV via vfmul /
 * vfadd / vfmacc.
 *
 * Precision: 24-bit mantissa = 144 dB dynamic range, well above the ~110 dB
 * audible ceiling.
 *
 * Sample-domain I/O convention:
 *   float samples are in [-1.0, +1.0].
 *   int16 PCM is normalised by /32768 on input, *32767 + clamp on output.
 * --------------------------------------------------------------------------*/

typedef float coeff_t;
typedef float control_t;

/* ---------------------------------------------------------------------------
 * Wavelet square layout
 *
 * 4096 samples at 48000 Hz = ~85.3 ms.
 * 12 detail bands + 1 scaling = 13 bands.
 *
 * Band | Cells | Cell width | Time width  | Freq range (approx)
 * -----|-------|------------|-------------|--------------------
 *   0  |  2048 |     2      |   41.7 µs   | 12000–24000 Hz
 *   1  |  1024 |     4      |   83.3 µs   |  6000–12000 Hz
 *   2  |   512 |     8      |  166.7 µs   |  3000–6000  Hz
 *   3  |   256 |    16      |  333.3 µs   |  1500–3000  Hz
 *   4  |   128 |    32      |  666.7 µs   |   750–1500  Hz
 *   5  |    64 |    64      |    1.33 ms  |   375–750   Hz
 *   6  |    32 |   128      |    2.67 ms  |   188–375   Hz
 *   7  |    16 |   256      |    5.33 ms  |    94–188   Hz
 *   8  |     8 |   512      |   10.67 ms  |    47–94    Hz
 *   9  |     4 |  1024      |   21.33 ms  |    23–47    Hz
 *  10  |     2 |  2048      |   42.67 ms  |    12–23    Hz
 *  11  |     1 |  4096      |   85.33 ms  |     6–12    Hz (detail)
 *  12  |     1 |  4096      |   85.33 ms  |     0–6     Hz (scaling)
 * --------------------------------------------------------------------------*/

#define SQUARE_SAMPLES     4096
#define WAVELET_LEVELS     12
#define TOTAL_BANDS        13
#define SAMPLE_RATE        48000
#define COEFFS_PER_CHANNEL 4096      /* 4095 detail + 1 scaling */
#define IQ_CHANNELS        2

static inline int band_size(int b) {
    if (b >= WAVELET_LEVELS) return 1;
    return SQUARE_SAMPLES >> (b + 1);
}

static inline int band_cell_samples(int b) {
    if (b >= WAVELET_LEVELS) return SQUARE_SAMPLES;
    return 1 << (b + 1);
}

static inline float band_center_freq(int b) {
    float hi = (float)SAMPLE_RATE / (float)(1 << (b + 1));
    float lo = hi * 0.5f;
    return (lo + hi) * 0.5f;
}

/* ---------------------------------------------------------------------------
 * WaveletSquare: flat float32 storage, two channels (I, Q).
 * Memory: 2 * 4096 * 4 = 32 KB per square.
 * --------------------------------------------------------------------------*/
typedef struct {
    coeff_t  storage[IQ_CHANNELS][COEFFS_PER_CHANNEL];
    coeff_t *bands[IQ_CHANNELS][TOTAL_BANDS];
    int      square_index;
} WaveletSquare;

void square_init (WaveletSquare *sq, int square_index);
void square_clear(WaveletSquare *sq);

/* ---------------------------------------------------------------------------
 * Arena allocator: single contiguous block, no free, 64-byte aligned.
 * --------------------------------------------------------------------------*/

#define ARENA_ALIGN 64

typedef struct {
    uint8_t *base;
    size_t   top;
    size_t   capacity;
} Arena;

void    arena_init    (Arena *a, void *memory, size_t capacity);
void   *arena_alloc   (Arena *a, size_t size);
size_t  arena_save    (const Arena *a);
void    arena_restore (Arena *a, size_t saved_top);

WaveletSquare *arena_alloc_square(Arena *a, int square_index);

/* ---------------------------------------------------------------------------
 * CDF 5/3 lifting transform (float32, in-place)
 *
 * Forward:
 *   Predict:  d[n] -= 0.5  * (s[n] + s[n+1])      (odd minus average)
 *   Update:   s[n] += 0.25 * (d[n-1] + d[n])      (even plus quarter-sum)
 *
 * Inverse (reverse order, opposite signs):
 *   Undo update:  s[n] -= 0.25 * (d[n-1] + d[n])
 *   Undo predict: d[n] += 0.5  * (s[n] + s[n+1])
 *
 * Boundary: symmetric (mirror) extension. The right edge uses x[len] = x[len-2].
 * Round-trip error is bounded by ~1 ULP per level; over 12 levels this stays
 * well under audible quantisation for any normal audio input.
 * --------------------------------------------------------------------------*/

void forward_cdf53(WaveletSquare *sq, int iq, const float *samples);
void inverse_cdf53(const WaveletSquare *sq, int iq, float *samples);

void forward_cdf53_i16(WaveletSquare *sq, int iq, const int16_t *samples);
void inverse_cdf53_i16(const WaveletSquare *sq, int iq, int16_t *samples);

/* Short-buffer wrappers; zero-pad inputs shorter than SQUARE_SAMPLES. */
void forward_cdf53_f32(WaveletSquare *sq, int iq, const float *samples,
                       int n_samples);
void inverse_cdf53_f32(const WaveletSquare *sq, int iq, float *samples,
                       int n_samples);

/* ---------------------------------------------------------------------------
 * Stamping: the core synthesis primitive.
 *
 * Stamps src into dst with time offset delay_samples and gain.
 * For each band b:
 *   cell_width    = 2^(b+1) samples
 *   cell_shift    = delay_samples / cell_width
 *   k             = floor(cell_shift)
 *   f             = cell_shift - k
 *   phi           = 2π * f_center(b) * (f * cell_width) / SAMPLE_RATE
 *   I/Q rotated by phi.
 *
 * For each src coefficient i:
 *   dst[i + k]     += rotated * gain * (1 - f)
 *   dst[i + k + 1] += rotated * gain * f
 *
 * Cross-square spill into dst_next; pass NULL to drop spilled coefficients.
 * --------------------------------------------------------------------------*/

typedef struct {
    control_t delay_samples;
    control_t gain;
    control_t gain_per_band[TOTAL_BANDS];
    int       use_per_band_gain;
} StampParams;

void stamp(WaveletSquare       *dst,
           WaveletSquare       *dst_next,
           const WaveletSquare *src,
           const StampParams   *p);

void stamp_simple(WaveletSquare       *dst,
                  const WaveletSquare *src,
                  control_t            delay_samples,
                  control_t            gain);

/* ---------------------------------------------------------------------------
 * Round-trip validation helper.
 * Returns max absolute error in float sample units (should be < 1e-5).
 * --------------------------------------------------------------------------*/
float validate_roundtrip(const float *samples, int n, float *samples_out);

#endif /* WAVELET_H */
