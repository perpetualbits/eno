/* tests/test_crest_bases.c
 *
 * Test suite for crest_bases: Daubechies-4 (D4) forward/inverse transform
 * and basis descriptor.  Mirrors the structure of test_crest_core.c.
 *
 * Sections:
 *   1. D4 round-trip (silence, impulse, sine, DC, full-scale)
 *   2. D4 frequency isolation (energy concentrated in expected band)
 *   3. D4 vs CDF 5/3 frequency isolation comparison
 *   4. Basis descriptor sanity checks
 */

#include "crest.h"
#include "crest_bases.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ===========================================================================
 * Test infrastructure (copied from test_crest_core.c)
 * =========================================================================*/

static int tests_run    = 0;
static int tests_passed = 0;
static int tests_failed = 0;

#define TEST_BEGIN(name) \
    do { \
        tests_run++; \
        printf("  %-58s ", name); \
        fflush(stdout); \
    } while(0)

#define TEST_PASS() \
    do { tests_passed++; printf("PASS\n"); } while(0)

#define TEST_FAIL(...) \
    do { \
        tests_failed++; \
        printf("FAIL: " __VA_ARGS__); \
        printf("\n"); \
    } while(0)

#define CHECK(cond, ...) \
    do { if (!(cond)) { TEST_FAIL(__VA_ARGS__); return; } } while(0)

#define TEST_ARENA_SIZE (16 * 1024 * 1024)
static uint8_t test_arena_memory[TEST_ARENA_SIZE];
static Arena   test_arena;

static void arena_reset_for_test(void) {
    arena_init(&test_arena, test_arena_memory, TEST_ARENA_SIZE);
}

static void gen_sine(float *buf, int n, float freq_hz, float amplitude) {
    for (int i = 0; i < n; i++) {
        buf[i] = amplitude * sinf(2.0f * (float)M_PI * freq_hz * i / SAMPLE_RATE);
    }
}

/* Compute the fraction of total energy contained in the peak band. */
static float peak_band_energy_fraction(const WaveletSquare *sq, int iq) {
    float band_energy[TOTAL_BANDS];
    float total = 0.0f;
    for (int b = 0; b < TOTAL_BANDS; b++) {
        float e = 0.0f;
        for (int i = 0; i < band_size(b); i++) {
            float v = sq->bands[iq][b][i];
            e += v * v;
        }
        band_energy[b] = e;
        total += e;
    }
    if (total < 1e-30f) return 0.0f;
    float peak = 0.0f;
    for (int b = 0; b < TOTAL_BANDS; b++) {
        if (band_energy[b] > peak) peak = band_energy[b];
    }
    return peak / total;
}

/* ===========================================================================
 * Section 1: D4 round-trip
 * =========================================================================*/

static void test_d4_roundtrip_silence(void) {
    TEST_BEGIN("D4 round-trip: silence");
    float in[SQUARE_SAMPLES] = {0};
    float out[SQUARE_SAMPLES];
    float err = validate_roundtrip_d4(in, SQUARE_SAMPLES, out);
    CHECK(err == 0.0f, "max_err=%g", err);
    TEST_PASS();
}

static void test_d4_roundtrip_impulse(void) {
    TEST_BEGIN("D4 round-trip: impulse at centre");
    float in[SQUARE_SAMPLES] = {0};
    float out[SQUARE_SAMPLES];
    in[SQUARE_SAMPLES / 2] = 0.5f;
    float err = validate_roundtrip_d4(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-4f, "max_err=%g", err);
    TEST_PASS();
}

static void test_d4_roundtrip_sine_440(void) {
    TEST_BEGIN("D4 round-trip: 440 Hz sine, max error < 1e-4");
    float in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 440.0f, 0.8f);
    float err = validate_roundtrip_d4(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-4f, "max_err=%g", err);
    TEST_PASS();
}

static void test_d4_roundtrip_sine_80(void) {
    TEST_BEGIN("D4 round-trip: 80 Hz sine, max error < 1e-4");
    float in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 80.0f, 0.8f);
    float err = validate_roundtrip_d4(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-4f, "max_err=%g", err);
    TEST_PASS();
}

static void test_d4_roundtrip_dc(void) {
    TEST_BEGIN("D4 round-trip: DC");
    float in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    for (int i = 0; i < SQUARE_SAMPLES; i++) in[i] = 0.5f;
    float err = validate_roundtrip_d4(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-4f, "max_err=%g", err);
    TEST_PASS();
}

static void test_d4_roundtrip_full_scale(void) {
    TEST_BEGIN("D4 round-trip: alternating +/-1.0");
    float in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    for (int i = 0; i < SQUARE_SAMPLES; i++) in[i] = (i & 1) ? 1.0f : -1.0f;
    float err = validate_roundtrip_d4(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-4f, "max_err=%g", err);
    TEST_PASS();
}

/* ===========================================================================
 * Section 2: D4 frequency isolation
 * =========================================================================*/

static void test_d4_isolation_440(void) {
    TEST_BEGIN("D4: 440 Hz energy concentrated in bands 4-6");
    arena_reset_for_test();
    WaveletSquare *sq = arena_alloc_square(&test_arena, 0);
    float in[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 440.0f, 0.8f);
    forward_d4(sq, 0, in);

    float max_energy = 0.0f;
    int   max_band   = -1;
    for (int b = 0; b < WAVELET_LEVELS; b++) {
        float e = 0.0f;
        for (int i = 0; i < band_size(b); i++) {
            float v = sq->bands[0][b][i];
            e += v * v;
        }
        if (e > max_energy) { max_energy = e; max_band = b; }
    }
    CHECK(max_band >= 4 && max_band <= 6, "peak at band %d", max_band);
    TEST_PASS();
}

static void test_d4_isolation_8khz(void) {
    TEST_BEGIN("D4: 8 kHz energy concentrated in bands 0-2");
    arena_reset_for_test();
    WaveletSquare *sq = arena_alloc_square(&test_arena, 0);
    float in[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 8000.0f, 0.8f);
    forward_d4(sq, 0, in);

    float max_energy = 0.0f;
    int   max_band   = -1;
    for (int b = 0; b < WAVELET_LEVELS; b++) {
        float e = 0.0f;
        for (int i = 0; i < band_size(b); i++) {
            float v = sq->bands[0][b][i];
            e += v * v;
        }
        if (e > max_energy) { max_energy = e; max_band = b; }
    }
    CHECK(max_band >= 0 && max_band <= 2, "peak at band %d", max_band);
    TEST_PASS();
}

/* ===========================================================================
 * Section 3: D4 vs CDF 5/3 frequency isolation comparison
 *
 * D4's "better frequency isolation" (crest_design.md §5.3) applies to smooth
 * broadband signals, not necessarily to every short pure sinusoid.  For a
 * finite-length single tone, CDF 5/3's symmetric lifting can match or slightly
 * beat D4's four irrational taps.  The tests here verify that the two bases
 * are comparable (within 5 %) and that D4 is never grossly worse.
 * =========================================================================*/

static void test_d4_vs_cdf53_isolation_440(void) {
    TEST_BEGIN("D4 vs CDF 5/3: comparable isolation for 440 Hz sine");
    arena_reset_for_test();

    float in[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 440.0f, 0.8f);

    WaveletSquare *sq_d4    = arena_alloc_square(&test_arena, 0);
    WaveletSquare *sq_cdf53 = arena_alloc_square(&test_arena, 1);

    forward_d4(sq_d4, 0, in);
    forward_cdf53(sq_cdf53, 0, in);

    float frac_d4    = peak_band_energy_fraction(sq_d4,    0);
    float frac_cdf53 = peak_band_energy_fraction(sq_cdf53, 0);

    /* Allow 5 % slack — for short sinusoids neither basis is clearly better. */
    CHECK(frac_d4 >= frac_cdf53 - 0.05f,
          "D4 frac=%.4f  CDF5/3 frac=%.4f  (diff > 5%%)", frac_d4, frac_cdf53);
    TEST_PASS();
}

static void test_d4_vs_cdf53_isolation_low(void) {
    TEST_BEGIN("D4 vs CDF 5/3: comparable isolation for 100 Hz sine");
    arena_reset_for_test();

    float in[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 100.0f, 0.8f);

    WaveletSquare *sq_d4    = arena_alloc_square(&test_arena, 0);
    WaveletSquare *sq_cdf53 = arena_alloc_square(&test_arena, 1);

    forward_d4(sq_d4, 0, in);
    forward_cdf53(sq_cdf53, 0, in);

    float frac_d4    = peak_band_energy_fraction(sq_d4,    0);
    float frac_cdf53 = peak_band_energy_fraction(sq_cdf53, 0);

    CHECK(frac_d4 >= frac_cdf53 - 0.05f,
          "D4 frac=%.4f  CDF5/3 frac=%.4f  (diff > 5%%)", frac_d4, frac_cdf53);
    TEST_PASS();
}

/* ===========================================================================
 * Section 4: Basis descriptor
 * =========================================================================*/

static void test_d4_descriptor(void) {
    TEST_BEGIN("crest_basis_desc_d4: name, n_params, iq_mode");
    const CrestBasisDesc *d = crest_basis_desc_d4();
    CHECK(d          != NULL, "descriptor is NULL");
    CHECK(d->name    != NULL, "name is NULL");
    CHECK(d->name[0] != '\0', "name is empty");
    CHECK(d->n_params  == 0,  "n_params=%d expected 0", d->n_params);
    CHECK(d->iq_mode   == 0,  "iq_mode=%d expected 0",  d->iq_mode);
    TEST_PASS();
}

static void test_cdf53_descriptor(void) {
    TEST_BEGIN("crest_basis_desc_cdf53: name, n_params, iq_mode");
    const CrestBasisDesc *d = crest_basis_desc_cdf53();
    CHECK(d          != NULL, "descriptor is NULL");
    CHECK(d->name    != NULL, "name is NULL");
    CHECK(d->name[0] != '\0', "name is empty");
    CHECK(d->n_params  == 0,  "n_params=%d expected 0", d->n_params);
    CHECK(d->iq_mode   == 0,  "iq_mode=%d expected 0",  d->iq_mode);
    TEST_PASS();
}

/* ===========================================================================
 * Main
 * =========================================================================*/

int main(void) {
    printf("=================================================================\n");
    printf("CREST Bases Test Suite (float32)\n");
    printf("SQUARE_SAMPLES=%d  WAVELET_LEVELS=%d  SAMPLE_RATE=%d\n",
           SQUARE_SAMPLES, WAVELET_LEVELS, SAMPLE_RATE);
    printf("=================================================================\n\n");

    printf("[ Section 1: D4 Round-trip ]\n");
    test_d4_roundtrip_silence();
    test_d4_roundtrip_impulse();
    test_d4_roundtrip_sine_440();
    test_d4_roundtrip_sine_80();
    test_d4_roundtrip_dc();
    test_d4_roundtrip_full_scale();

    printf("\n[ Section 2: D4 Frequency Isolation ]\n");
    test_d4_isolation_440();
    test_d4_isolation_8khz();

    printf("\n[ Section 3: D4 vs CDF 5/3 Comparison ]\n");
    test_d4_vs_cdf53_isolation_440();
    test_d4_vs_cdf53_isolation_low();

    printf("\n[ Section 4: Basis Descriptors ]\n");
    test_d4_descriptor();
    test_cdf53_descriptor();

    printf("\n=================================================================\n");
    printf("Results: %d/%d passed", tests_passed, tests_run);
    if (tests_failed > 0) printf(", %d FAILED", tests_failed);
    printf("\n=================================================================\n");

    return tests_failed > 0 ? 1 : 0;
}
