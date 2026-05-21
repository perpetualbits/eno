/* crest_bases.c
 *
 * Forward and inverse wavelet transforms for non-CDF-5/3 bases.
 * Currently implements Daubechies-4 (D4).
 *
 * Each basis shares WaveletSquare storage (defined in crest.h) and provides
 * three entry points: forward_<basis>, inverse_<basis>, crest_basis_desc_<basis>.
 * See crest_design.md §5.1 for the full basis contract.
 */

#include "crest_bases.h"

#include <string.h>
#include <math.h>

/* ===========================================================================
 * Daubechies-4 (D4)
 *
 * D4 is an orthogonal 4-tap wavelet filter bank.  Unlike CDF 5/3 which uses
 * lifting with rational (½, ¼) steps, D4 uses irrational filter coefficients
 * derived from the Daubechies vanishing-moment construction.  The consequence
 * is that D4 cannot be implemented as simple in-place lifting; it needs a
 * temporary scratch buffer per level.
 *
 * Algorithm (Mallat, analysis polyphase form):
 *
 *   Forward one level — length N → (scaling N/2, detail N/2):
 *     For n = 0..N/2-1, with periodic extension (indices mod N):
 *       s[n] = h0*x[2n] + h1*x[2n+1] + h2*x[2n+2] + h3*x[2n+3]
 *       d[n] = g0*x[2n] + g1*x[2n+1] + g2*x[2n+2] + g3*x[2n+3]
 *
 *   Inverse one level — (scaling N/2, detail N/2) → length N:
 *     (transpose of the analysis matrix — valid because D4 is orthogonal)
 *     x[n] = 0  for all n
 *     For k = 0..N/2-1:
 *       x[(2k)   mod N] += h0*s[k] + g0*d[k]
 *       x[(2k+1) mod N] += h1*s[k] + g1*d[k]
 *       x[(2k+2) mod N] += h2*s[k] + g2*d[k]
 *       x[(2k+3) mod N] += h3*s[k] + g3*d[k]
 *
 * Orthogonality guarantees that this scatter pattern exactly inverts the
 * gather pattern above — verified algebraically for the N=4 case in the
 * session notes.
 *
 * The 12-level cascade mirrors forward_cdf53/inverse_cdf53 in crest_core.c.
 * =========================================================================*/

/* D4 scaling-filter taps: h₀..h₃. */
static const float D4_H[4] = {
     0.4829629131f,   /* h0 = (1+√3)/(4√2) */
     0.8365163037f,   /* h1 = (3+√3)/(4√2) */
     0.2241438680f,   /* h2 = (3−√3)/(4√2) */
    -0.1294095226f    /* h3 = (1−√3)/(4√2) */
};

/* D4 wavelet-filter taps: g₀..g₃ = (h₃, −h₂, h₁, −h₀). */
static const float D4_G[4] = {
    -0.1294095226f,   /* g0 =  h3 */
    -0.2241438680f,   /* g1 = −h2 */
     0.8365163037f,   /* g2 =  h1 */
    -0.4829629131f    /* g3 = −h0 */
};

/* Scratch buffer: large enough for one full-size level (N=4096) or one
 * half-size output (N/2=2048 floats).  Single-threaded, so static is safe. */
static float d4_tmp[SQUARE_SAMPLES];

/* Forward step: decompose work[0..len-1] into s (scaling) and d (detail).
 * Scaling values overwrite work[0..len/2-1]; detail written to dest_band. */
static void d4_forward_step(float *work, int len, coeff_t *dest_band) {
    int half = len / 2;
    int mask = len - 1;   /* len is always a power of two */

    for (int n = 0; n < half; n++) {
        float x0 = work[(2*n    ) & mask];
        float x1 = work[(2*n + 1) & mask];
        float x2 = work[(2*n + 2) & mask];
        float x3 = work[(2*n + 3) & mask];
        d4_tmp[n]    = D4_H[0]*x0 + D4_H[1]*x1 + D4_H[2]*x2 + D4_H[3]*x3;
        dest_band[n] = D4_G[0]*x0 + D4_G[1]*x1 + D4_G[2]*x2 + D4_G[3]*x3;
    }
    memcpy(work, d4_tmp, (size_t)half * sizeof(float));
}

/* Inverse step: reconstruct work[0..len-1] from work[0..half-1] (scaling)
 * and src_band[0..half-1] (detail).  Uses the transpose scatter pattern. */
static void d4_inverse_step(float *work, int half, const coeff_t *src_band) {
    int len  = half * 2;
    int mask = len - 1;

    memset(d4_tmp, 0, (size_t)len * sizeof(float));
    for (int k = 0; k < half; k++) {
        float s = work[k];
        float d = src_band[k];
        d4_tmp[(2*k    ) & mask] += D4_H[0]*s + D4_G[0]*d;
        d4_tmp[(2*k + 1) & mask] += D4_H[1]*s + D4_G[1]*d;
        d4_tmp[(2*k + 2) & mask] += D4_H[2]*s + D4_G[2]*d;
        d4_tmp[(2*k + 3) & mask] += D4_H[3]*s + D4_G[3]*d;
    }
    memcpy(work, d4_tmp, (size_t)len * sizeof(float));
}

void forward_d4(WaveletSquare *sq, int iq, const float *samples) {
    float work[SQUARE_SAMPLES];
    memcpy(work, samples, sizeof(work));

    int len = SQUARE_SAMPLES;
    for (int level = 0; level < WAVELET_LEVELS; level++) {
        d4_forward_step(work, len, sq->bands[iq][level]);
        len >>= 1;
    }
    sq->bands[iq][WAVELET_LEVELS][0] = work[0];
}

void inverse_d4(const WaveletSquare *sq, int iq, float *samples) {
    float work[SQUARE_SAMPLES];
    work[0] = sq->bands[iq][WAVELET_LEVELS][0];

    int half = 1;
    for (int level = WAVELET_LEVELS - 1; level >= 0; level--) {
        d4_inverse_step(work, half, sq->bands[iq][level]);
        half <<= 1;
    }
    memcpy(samples, work, sizeof(work));
}

/* Round-trip helper: forward then inverse, return max absolute error.
 * Uses a static square so the caller does not need to manage storage. */
float validate_roundtrip_d4(const float *samples, int n, float *samples_out) {
    static WaveletSquare sq;
    square_init(&sq, 0);

    forward_d4(&sq, 0, samples);
    inverse_d4(&sq, 0, samples_out);

    float max_err = 0.0f;
    int count = n < SQUARE_SAMPLES ? n : SQUARE_SAMPLES;
    for (int i = 0; i < count; i++) {
        float e = fabsf(samples_out[i] - samples[i]);
        if (e > max_err) max_err = e;
    }
    return max_err;
}

/* ===========================================================================
 * Basis descriptors
 * =========================================================================*/

const CrestBasisDesc *crest_basis_desc_d4(void) {
    static const CrestBasisDesc desc = {
        .name      = "db4",
        .n_params  = 0,
        .iq_mode   = 0,
        .rvv_ready = 0,
    };
    return &desc;
}
