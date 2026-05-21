#ifndef CREST_BASES_H
#define CREST_BASES_H

/* crest_bases.h
 *
 * Forward/inverse transform pairs for every audio.basis.* family.
 * All bases share the WaveletSquare storage type from crest.h.
 *
 * Basis contract (§5.1 of crest_design.md):
 *   forward_<basis>(sq, iq, samples)  — decompose samples into sq->bands[iq]
 *   inverse_<basis>(sq, iq, samples)  — reconstruct samples from sq->bands[iq]
 *   crest_basis_desc_<basis>()        — return static CrestBasisDesc pointer
 */

#include "crest.h"

/* ---------------------------------------------------------------------------
 * Daubechies-4 (D4)
 *
 * Orthogonal 4-tap wavelet transform.  Better frequency isolation than
 * CDF 5/3 for smooth and noise-like signals (wind, rain, consonants).
 * Worse time localisation than CDF 5/3 for sharp transients.
 *
 * Filter coefficients (h₀..h₃, IEEE 754 float32):
 *   h0 = (1+√3)/(4√2)  ≈  0.4829629131
 *   h1 = (3+√3)/(4√2)  ≈  0.8365163037
 *   h2 = (3−√3)/(4√2)  ≈  0.2241438680
 *   h3 = (1−√3)/(4√2)  ≈ −0.1294095226
 * Wavelet filter: g0=h3, g1=−h2, g2=h1, g3=−h0.
 *
 * Round-trip error: < 1e-4 for all tested signals (looser than CDF 5/3's
 * < 1e-5 because D4 uses four irrational float32 taps per level).
 * --------------------------------------------------------------------------*/
void forward_d4(WaveletSquare *sq, int iq, const float *samples);
void inverse_d4(const WaveletSquare *sq, int iq, float *samples);
const CrestBasisDesc *crest_basis_desc_d4(void);

/* Round-trip validation helper (same contract as validate_roundtrip in crest.h
 * but using the D4 basis). */
float validate_roundtrip_d4(const float *samples, int n, float *samples_out);

#endif /* CREST_BASES_H */
