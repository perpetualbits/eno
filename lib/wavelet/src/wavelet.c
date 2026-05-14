#include "wavelet.h"

#include <string.h>
#include <math.h>
#include <stdio.h>

/* ===========================================================================
 * Arena
 * =========================================================================*/

void arena_init(Arena *a, void *memory, size_t capacity) {
    /* Align the base pointer up to ARENA_ALIGN. This lets callers pass any
     * static buffer without worrying about its natural alignment.        */
    uintptr_t raw     = (uintptr_t)memory;
    uintptr_t aligned = (raw + ARENA_ALIGN - 1) & ~(uintptr_t)(ARENA_ALIGN - 1);
    size_t    pad     = (size_t)(aligned - raw);
    assert(pad < capacity && "arena memory too small for alignment");

    a->base     = (uint8_t *)(uintptr_t)aligned;
    a->top      = 0;
    a->capacity = capacity - pad;
}

void *arena_alloc(Arena *a, size_t size) {
    size_t aligned_top = (a->top + ARENA_ALIGN - 1) & ~(size_t)(ARENA_ALIGN - 1);
    assert(aligned_top + size <= a->capacity && "arena exhausted");
    void *ptr = a->base + aligned_top;
    a->top = aligned_top + size;
    return ptr;
}

size_t arena_save(const Arena *a) { return a->top; }

void arena_restore(Arena *a, size_t saved_top) {
    assert(saved_top <= a->top);
    a->top = saved_top;
}

WaveletSquare *arena_alloc_square(Arena *a, int square_index) {
    WaveletSquare *sq = (WaveletSquare *)arena_alloc(a, sizeof(WaveletSquare));
    square_init(sq, square_index);
    return sq;
}

/* ===========================================================================
 * WaveletSquare init / clear
 * =========================================================================*/

void square_init(WaveletSquare *sq, int square_index) {
    sq->square_index = square_index;
    square_clear(sq);

    for (int iq = 0; iq < IQ_CHANNELS; iq++) {
        int offset = 0;
        for (int b = 0; b < TOTAL_BANDS; b++) {
            sq->bands[iq][b] = sq->storage[iq] + offset;
            offset += band_size(b);
        }
        assert(offset == COEFFS_PER_CHANNEL);
    }
}

void square_clear(WaveletSquare *sq) {
    memset(sq->storage, 0, sizeof(sq->storage));
}

/* ===========================================================================
 * CDF 5/3 forward lifting step (one level).
 *
 * Input:  work[0..len-1]   (sample-like or scaling values)
 * Output: detail values written to dest_band[0..len/2-1]
 *         scaling values compacted to work[0..len/2-1]
 *
 * The two passes are independent across n (each n only writes its own
 * work[2n+1] or work[2n]), which is exactly the structure RVV wants:
 * gather even, gather odd, gather even-right; compute; scatter.
 * =========================================================================*/
static void cdf53_forward_step(float *work, int len, coeff_t *dest_band) {
    int half = len / 2;

    /* Predict: d[n] -= 0.5 * (s[n] + s[n+1])
     * Boundary at the right edge: s[half] mirrors s[half-1], i.e.
     * work[len] = work[len - 2] (symmetric extension of the sample sequence). */
    for (int n = 0; n < half; n++) {
        float sL = work[2 * n];
        float sR = (2 * n + 2 < len) ? work[2 * n + 2] : work[len - 2];
        work[2 * n + 1] -= 0.5f * (sL + sR);
    }

    /* Update: s[n] += 0.25 * (d[n-1] + d[n])
     * Boundary at the left edge: d[-1] mirrors d[0], i.e. work[-1] = work[1]. */
    for (int n = 0; n < half; n++) {
        float dL = (n > 0) ? work[2 * n - 1] : work[1];
        float dR = work[2 * n + 1];
        work[2 * n] += 0.25f * (dL + dR);
    }

    /* Pack: detail to band, scaling compacted to front. */
    for (int n = 0; n < half; n++) {
        dest_band[n] = work[2 * n + 1];
        work[n]      = work[2 * n];
    }
}

/* CDF 5/3 inverse lifting step (one level).
 *
 * Input:  work[0..half-1]  (scaling values from coarser level)
 *         src_band[0..half-1] (detail values for this level)
 * Output: work[0..len-1]   (samples / scaling for next-finer level)
 * =========================================================================*/
static void cdf53_inverse_step(float *work, int half, const coeff_t *src_band) {
    int len = half * 2;

    /* Unpack: interleave scaling (even) and detail (odd) into work.
     * Reverse order avoids clobbering values that haven't been moved yet. */
    for (int n = half - 1; n >= 0; n--) {
        work[2 * n]     = work[n];
        work[2 * n + 1] = src_band[n];
    }

    /* Undo update: s[n] -= 0.25 * (d[n-1] + d[n]) */
    for (int n = 0; n < half; n++) {
        float dL = (n > 0) ? work[2 * n - 1] : work[1];
        float dR = work[2 * n + 1];
        work[2 * n] -= 0.25f * (dL + dR);
    }

    /* Undo predict: d[n] += 0.5 * (s[n] + s[n+1]) */
    for (int n = 0; n < half; n++) {
        float sL = work[2 * n];
        float sR = (2 * n + 2 < len) ? work[2 * n + 2] : work[len - 2];
        work[2 * n + 1] += 0.5f * (sL + sR);
    }
}

/* ===========================================================================
 * Forward / inverse, float32 entry points
 * =========================================================================*/

void forward_cdf53(WaveletSquare *sq, int iq, const float *samples) {
    float work[SQUARE_SAMPLES];
    memcpy(work, samples, sizeof(work));

    int len = SQUARE_SAMPLES;
    for (int level = 0; level < WAVELET_LEVELS; level++) {
        cdf53_forward_step(work, len, sq->bands[iq][level]);
        len >>= 1;
    }
    sq->bands[iq][WAVELET_LEVELS][0] = work[0];
}

void inverse_cdf53(const WaveletSquare *sq, int iq, float *samples) {
    float work[SQUARE_SAMPLES];
    work[0] = sq->bands[iq][WAVELET_LEVELS][0];

    int half = 1;
    for (int level = WAVELET_LEVELS - 1; level >= 0; level--) {
        cdf53_inverse_step(work, half, sq->bands[iq][level]);
        half <<= 1;
    }
    memcpy(samples, work, sizeof(work));
}

/* int16 wrappers: normalise by 1/32768 in, *32767 + clamp out. */
void forward_cdf53_i16(WaveletSquare *sq, int iq, const int16_t *samples) {
    float buf[SQUARE_SAMPLES];
    const float kScale = 1.0f / 32768.0f;
    for (int i = 0; i < SQUARE_SAMPLES; i++) {
        buf[i] = (float)samples[i] * kScale;
    }
    forward_cdf53(sq, iq, buf);
}

void inverse_cdf53_i16(const WaveletSquare *sq, int iq, int16_t *samples) {
    float buf[SQUARE_SAMPLES];
    inverse_cdf53(sq, iq, buf);
    for (int i = 0; i < SQUARE_SAMPLES; i++) {
        float v = buf[i] * 32767.0f;
        if (v >  32767.0f) v =  32767.0f;
        if (v < -32768.0f) v = -32768.0f;
        samples[i] = (int16_t)lrintf(v);
    }
}

/* Short-buffer convenience: zero-pad if input is shorter than SQUARE_SAMPLES. */
void forward_cdf53_f32(WaveletSquare *sq, int iq,
                       const float *samples, int n_samples) {
    float buf[SQUARE_SAMPLES];
    int count = n_samples < SQUARE_SAMPLES ? n_samples : SQUARE_SAMPLES;
    memcpy(buf, samples, count * sizeof(float));
    if (count < SQUARE_SAMPLES) {
        memset(buf + count, 0, (SQUARE_SAMPLES - count) * sizeof(float));
    }
    forward_cdf53(sq, iq, buf);
}

void inverse_cdf53_f32(const WaveletSquare *sq, int iq,
                       float *samples, int n_samples) {
    float buf[SQUARE_SAMPLES];
    inverse_cdf53(sq, iq, buf);
    int count = n_samples < SQUARE_SAMPLES ? n_samples : SQUARE_SAMPLES;
    memcpy(samples, buf, count * sizeof(float));
}

/* ===========================================================================
 * Stamping
 *
 * The inner loop is laid out as two passes per band (tap0 then tap1) so it
 * vectorises cleanly. Each pass is a contiguous read of src and a contiguous
 * accumulating write to dst (with a single offset k or k+1).
 *
 * The per-band setup (k, f, w0, w1, cos_phi, sin_phi) involves a floorf,
 * a cosf, and a sinf — at most 13 of each per stamp() call, regardless of
 * the number of coefficients processed. The hot loop has no libm calls.
 * =========================================================================*/

typedef struct {
    int   k;
    float w0, w1;
    float cos_phi, sin_phi;
    float gain;
} BandStampParams;

static void compute_band_params(BandStampParams out[TOTAL_BANDS],
                                const StampParams *p) {
    for (int b = 0; b < TOTAL_BANDS; b++) {
        int   cell_samples = band_cell_samples(b);
        float cell_shift   = p->delay_samples / (float)cell_samples;

        int   k = (int)floorf(cell_shift);
        float f = cell_shift - (float)k;

        float f_center    = band_center_freq(b);
        float sub_delay_s = (f * (float)cell_samples) / (float)SAMPLE_RATE;
        float phi         = 2.0f * (float)M_PI * f_center * sub_delay_s;

        float gain = p->gain;
        if (p->use_per_band_gain) gain *= p->gain_per_band[b];

        out[b].k       = k;
        out[b].w0      = 1.0f - f;
        out[b].w1      = f;
        out[b].cos_phi = cosf(phi);
        out[b].sin_phi = sinf(phi);
        out[b].gain    = gain;
    }
}

/* Two-pass stamp inner loop.
 *
 * Pass 1: for each src coeff i in 0..n-1, write rotated*gain*w0 into dst[i+k].
 * Pass 2: for each src coeff i in 0..n-1, write rotated*gain*w1 into dst[i+k+1].
 *
 * The rotation is computed inline per coefficient (cheap: 4 multiplies, 2 adds).
 * This is the RVV-friendly shape. */
static void stamp_band_two_pass(coeff_t       *dst_i,
                                coeff_t       *dst_q,
                                coeff_t       *dst_next_i,
                                coeff_t       *dst_next_q,
                                int            dst_size,
                                const coeff_t *src_i,
                                const coeff_t *src_q,
                                int            n,
                                const BandStampParams *p) {
    const float cos_phi = p->cos_phi;
    const float sin_phi = p->sin_phi;
    const float gw0 = p->gain * p->w0;
    const float gw1 = p->gain * p->w1;
    const int   k   = p->k;

    /* Pass 1: tap0 -> dst[i + k] */
    for (int i = 0; i < n; i++) {
        float ci = src_i[i];
        float cq = src_q[i];
        float ri = ci * cos_phi - cq * sin_phi;
        float rq = ci * sin_phi + cq * cos_phi;

        int pos = i + k;
        if (pos >= 0 && pos < dst_size) {
            dst_i[pos] += ri * gw0;
            dst_q[pos] += rq * gw0;
        } else if (pos >= dst_size && dst_next_i != NULL) {
            int np = pos - dst_size;
            if (np < dst_size) {
                dst_next_i[np] += ri * gw0;
                dst_next_q[np] += rq * gw0;
            }
        }
    }

    /* Pass 2: tap1 -> dst[i + k + 1] */
    for (int i = 0; i < n; i++) {
        float ci = src_i[i];
        float cq = src_q[i];
        float ri = ci * cos_phi - cq * sin_phi;
        float rq = ci * sin_phi + cq * cos_phi;

        int pos = i + k + 1;
        if (pos >= 0 && pos < dst_size) {
            dst_i[pos] += ri * gw1;
            dst_q[pos] += rq * gw1;
        } else if (pos >= dst_size && dst_next_i != NULL) {
            int np = pos - dst_size;
            if (np < dst_size) {
                dst_next_i[np] += ri * gw1;
                dst_next_q[np] += rq * gw1;
            }
        }
    }
}

void stamp(WaveletSquare       *dst,
           WaveletSquare       *dst_next,
           const WaveletSquare *src,
           const StampParams   *p) {
    BandStampParams bp[TOTAL_BANDS];
    compute_band_params(bp, p);

    for (int b = 0; b < TOTAL_BANDS; b++) {
        int n = band_size(b);
        stamp_band_two_pass(
            dst->bands[0][b], dst->bands[1][b],
            dst_next ? dst_next->bands[0][b] : NULL,
            dst_next ? dst_next->bands[1][b] : NULL,
            n,
            src->bands[0][b], src->bands[1][b],
            n,
            &bp[b]);
    }
}

void stamp_simple(WaveletSquare       *dst,
                  const WaveletSquare *src,
                  control_t            delay_samples,
                  control_t            gain) {
    StampParams p = {0};
    p.delay_samples     = delay_samples;
    p.gain              = gain;
    p.use_per_band_gain = 0;
    stamp(dst, NULL, src, &p);
}

/* ===========================================================================
 * Round-trip validation
 * =========================================================================*/

float validate_roundtrip(const float *samples, int n, float *samples_out) {
    static WaveletSquare sq;
    square_init(&sq, 0);

    forward_cdf53(&sq, 0, samples);
    inverse_cdf53(&sq, 0, samples_out);

    float max_err = 0.0f;
    int count = n < SQUARE_SAMPLES ? n : SQUARE_SAMPLES;
    for (int i = 0; i < count; i++) {
        float e = fabsf(samples_out[i] - samples[i]);
        if (e > max_err) max_err = e;
    }
    return max_err;
}
