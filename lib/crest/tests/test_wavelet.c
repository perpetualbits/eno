#include "wavelet.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* ===========================================================================
 * Test infrastructure
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

static float rms(const float *buf, int n) {
    float sum = 0.0f;
    for (int i = 0; i < n; i++) sum += buf[i] * buf[i];
    return sqrtf(sum / (float)n);
}

static float max_diff_f32(const float *a, const float *b, int n) {
    float m = 0.0f;
    for (int i = 0; i < n; i++) {
        float d = fabsf(a[i] - b[i]);
        if (d > m) m = d;
    }
    return m;
}

/* ===========================================================================
 * Section 1: Structure and Arena
 * =========================================================================*/

static void test_band_sizes(void) {
    TEST_BEGIN("band_size() sum equals COEFFS_PER_CHANNEL");
    int total = 0;
    for (int b = 0; b < TOTAL_BANDS; b++) total += band_size(b);
    CHECK(total == COEFFS_PER_CHANNEL,
          "sum=%d expected=%d", total, COEFFS_PER_CHANNEL);
    TEST_PASS();
}

static void test_band_size_values(void) {
    TEST_BEGIN("band_size() values are correct power-of-two sequence");
    CHECK(band_size(0) == SQUARE_SAMPLES / 2,
          "band 0: %d expected %d", band_size(0), SQUARE_SAMPLES / 2);
    for (int b = 1; b < WAVELET_LEVELS; b++) {
        CHECK(band_size(b) == band_size(b - 1) / 2,
              "band %d: %d", b, band_size(b));
    }
    CHECK(band_size(WAVELET_LEVELS) == 1, "scaling band size");
    TEST_PASS();
}

static void test_square_init_zeros(void) {
    TEST_BEGIN("square_init() zeroes all coefficients");
    arena_reset_for_test();
    WaveletSquare *sq = arena_alloc_square(&test_arena, 0);
    for (int iq = 0; iq < IQ_CHANNELS; iq++)
        for (int b = 0; b < TOTAL_BANDS; b++)
            for (int i = 0; i < band_size(b); i++)
                CHECK(sq->bands[iq][b][i] == 0.0f,
                      "bands[%d][%d][%d] nonzero", iq, b, i);
    TEST_PASS();
}

static void test_square_band_pointers(void) {
    TEST_BEGIN("band pointers are contiguous and non-overlapping");
    arena_reset_for_test();
    WaveletSquare *sq = arena_alloc_square(&test_arena, 0);
    for (int iq = 0; iq < IQ_CHANNELS; iq++) {
        coeff_t *expected = sq->storage[iq];
        for (int b = 0; b < TOTAL_BANDS; b++) {
            CHECK(sq->bands[iq][b] == expected, "bands[%d][%d]", iq, b);
            expected += band_size(b);
        }
    }
    TEST_PASS();
}

static void test_arena_alignment(void) {
    TEST_BEGIN("arena_alloc() returns 64-byte aligned pointers");
    arena_reset_for_test();
    for (int i = 0; i < 8; i++) {
        void *p = arena_alloc(&test_arena, 13);
        uintptr_t a = (uintptr_t)p;
        CHECK((a & (ARENA_ALIGN - 1)) == 0,
              "alloc %d: %p not aligned", i, p);
    }
    TEST_PASS();
}

static void test_arena_save_restore(void) {
    TEST_BEGIN("arena save/restore");
    arena_reset_for_test();
    size_t saved = arena_save(&test_arena);
    arena_alloc(&test_arena, 1024);
    arena_alloc(&test_arena, 2048);
    arena_restore(&test_arena, saved);
    CHECK(test_arena.top == saved, "top=%zu expected %zu",
          test_arena.top, saved);
    TEST_PASS();
}

/* ===========================================================================
 * Section 2: CDF 5/3 transform
 * =========================================================================*/

static void test_roundtrip_silence(void) {
    TEST_BEGIN("round-trip: silence");
    float in[SQUARE_SAMPLES] = {0};
    float out[SQUARE_SAMPLES];
    float err = validate_roundtrip(in, SQUARE_SAMPLES, out);
    CHECK(err == 0.0f, "max_err=%g", err);
    TEST_PASS();
}

static void test_roundtrip_impulse(void) {
    TEST_BEGIN("round-trip: impulse at center");
    float in[SQUARE_SAMPLES] = {0};
    float out[SQUARE_SAMPLES];
    in[SQUARE_SAMPLES / 2] = 0.5f;
    float err = validate_roundtrip(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-5f, "max_err=%g", err);
    TEST_PASS();
}

static void test_roundtrip_sine_440(void) {
    TEST_BEGIN("round-trip: 440 Hz sine, max error < 1e-5");
    float in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 440.0f, 0.8f);
    float err = validate_roundtrip(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-5f, "max_err=%g", err);
    TEST_PASS();
}

static void test_roundtrip_sine_80(void) {
    TEST_BEGIN("round-trip: 80 Hz sine, max error < 1e-5");
    float in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 80.0f, 0.8f);
    float err = validate_roundtrip(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-5f, "max_err=%g", err);
    TEST_PASS();
}

static void test_roundtrip_sine_12000(void) {
    TEST_BEGIN("round-trip: 12 kHz sine (near Nyquist quarter)");
    float in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 12000.0f, 0.8f);
    float err = validate_roundtrip(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-5f, "max_err=%g", err);
    TEST_PASS();
}

static void test_roundtrip_dc(void) {
    TEST_BEGIN("round-trip: DC");
    float in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    for (int i = 0; i < SQUARE_SAMPLES; i++) in[i] = 0.5f;
    float err = validate_roundtrip(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-5f, "max_err=%g", err);
    TEST_PASS();
}

static void test_roundtrip_full_scale(void) {
    TEST_BEGIN("round-trip: full-scale signal (+/-1.0)");
    float in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    for (int i = 0; i < SQUARE_SAMPLES; i++)
        in[i] = (i & 1) ? 1.0f : -1.0f;   /* worst case for predict step */
    float err = validate_roundtrip(in, SQUARE_SAMPLES, out);
    CHECK(err < 1e-5f, "max_err=%g", err);
    TEST_PASS();
}

static void test_energy_preservation(void) {
    TEST_BEGIN("energy preserved in round-trip (within 0.001%%)");
    arena_reset_for_test();
    WaveletSquare *sq = arena_alloc_square(&test_arena, 0);
    float in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 1000.0f, 0.5f);
    forward_cdf53(sq, 0, in);
    inverse_cdf53(sq, 0, out);
    float r_in = rms(in, SQUARE_SAMPLES);
    float r_out = rms(out, SQUARE_SAMPLES);
    float rel = fabsf(r_out - r_in) / (r_in + 1e-12f);
    CHECK(rel < 1e-5f, "rel_err=%g", rel);
    TEST_PASS();
}

static void test_scaling_coefficient_dc(void) {
    TEST_BEGIN("DC: all detail bands ~zero, scaling nonzero");
    arena_reset_for_test();
    WaveletSquare *sq = arena_alloc_square(&test_arena, 0);
    float in[SQUARE_SAMPLES];
    for (int i = 0; i < SQUARE_SAMPLES; i++) in[i] = 0.25f;
    forward_cdf53(sq, 0, in);

    float max_detail = 0.0f;
    for (int b = 0; b < WAVELET_LEVELS; b++) {
        for (int i = 0; i < band_size(b); i++) {
            float v = fabsf(sq->bands[0][b][i]);
            if (v > max_detail) max_detail = v;
        }
    }
    CHECK(max_detail < 1e-5f, "max detail = %g", max_detail);
    CHECK(fabsf(sq->bands[0][WAVELET_LEVELS][0]) > 0.001f,
          "scaling = %g (should be nonzero)",
          sq->bands[0][WAVELET_LEVELS][0]);
    TEST_PASS();
}

static void test_int16_roundtrip(void) {
    TEST_BEGIN("int16 round-trip preserves audio");
    arena_reset_for_test();
    WaveletSquare *sq = arena_alloc_square(&test_arena, 0);
    int16_t in[SQUARE_SAMPLES], out[SQUARE_SAMPLES];
    for (int i = 0; i < SQUARE_SAMPLES; i++) {
        float v = sinf(2.0f * (float)M_PI * 440.0f * i / SAMPLE_RATE) * 0.8f;
        in[i] = (int16_t)(v * 32767.0f);
    }
    forward_cdf53_i16(sq, 0, in);
    inverse_cdf53_i16(sq, 0, out);
    int max_e = 0;
    for (int i = 0; i < SQUARE_SAMPLES; i++) {
        int d = abs((int)out[i] - (int)in[i]);
        if (d > max_e) max_e = d;
    }
    CHECK(max_e <= 1, "max int16 error = %d", max_e);
    TEST_PASS();
}

/* ===========================================================================
 * Section 3: Stamping
 * =========================================================================*/

static void test_stamp_zero_delay(void) {
    TEST_BEGIN("stamp delay=0: dst == src");
    arena_reset_for_test();
    float in[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 440.0f, 0.5f);

    WaveletSquare *src = arena_alloc_square(&test_arena, 0);
    WaveletSquare *dst = arena_alloc_square(&test_arena, 0);
    forward_cdf53(src, 0, in);
    stamp_simple(dst, src, 0.0f, 1.0f);

    float out[SQUARE_SAMPLES];
    inverse_cdf53(dst, 0, out);
    float d = max_diff_f32(in, out, SQUARE_SAMPLES);
    CHECK(d < 1e-5f, "max diff = %g", d);
    TEST_PASS();
}

static void test_stamp_integer_delay(void) {
    TEST_BEGIN("stamp integer delay: impulse arrives at right time");
    arena_reset_for_test();
    float impulse[SQUARE_SAMPLES] = {0};
    impulse[0] = 0.5f;

    WaveletSquare *src = arena_alloc_square(&test_arena, 0);
    WaveletSquare *dst = arena_alloc_square(&test_arena, 0);
    forward_cdf53(src, 0, impulse);
    stamp_simple(dst, src, 256.0f, 1.0f);

    float out[SQUARE_SAMPLES];
    inverse_cdf53(dst, 0, out);

    int peak_pos = 0;
    float peak_val = 0.0f;
    for (int i = 0; i < SQUARE_SAMPLES; i++) {
        float v = fabsf(out[i]);
        if (v > peak_val) { peak_val = v; peak_pos = i; }
    }
    CHECK(abs(peak_pos - 256) <= 8,
          "peak at %d, expected ~256", peak_pos);

    /* Energy near 256 should contain a sizable fraction of original. */
    float energy = 0.0f;
    for (int i = 224; i < 288 && i < SQUARE_SAMPLES; i++)
        if (i >= 0) energy += out[i] * out[i];
    /* Original impulse energy = 0.25. Expect at least 20% nearby. */
    CHECK(energy > 0.25f * 0.2f,
          "energy near peak = %g (expected > %g)",
          energy, 0.25f * 0.2f);
    TEST_PASS();
}

static void test_stamp_gain(void) {
    TEST_BEGIN("stamp gain scales output energy");
    arena_reset_for_test();
    float in[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 440.0f, 0.5f);

    WaveletSquare *src  = arena_alloc_square(&test_arena, 0);
    WaveletSquare *d1   = arena_alloc_square(&test_arena, 0);
    WaveletSquare *d2   = arena_alloc_square(&test_arena, 0);
    forward_cdf53(src, 0, in);
    stamp_simple(d1, src, 0.0f, 1.0f);
    stamp_simple(d2, src, 0.0f, 0.5f);

    float o1[SQUARE_SAMPLES], o2[SQUARE_SAMPLES];
    inverse_cdf53(d1, 0, o1);
    inverse_cdf53(d2, 0, o2);

    float ratio = rms(o2, SQUARE_SAMPLES) / (rms(o1, SQUARE_SAMPLES) + 1e-12f);
    CHECK(fabsf(ratio - 0.5f) < 0.001f, "ratio = %g", ratio);
    TEST_PASS();
}

static void test_stamp_accumulation(void) {
    TEST_BEGIN("two stamps superpose linearly");
    arena_reset_for_test();
    float in[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 440.0f, 0.3f);

    WaveletSquare *src    = arena_alloc_square(&test_arena, 0);
    WaveletSquare *acc    = arena_alloc_square(&test_arena, 0);
    WaveletSquare *single = arena_alloc_square(&test_arena, 0);
    forward_cdf53(src, 0, in);

    stamp_simple(acc, src, 0.0f, 0.5f);
    stamp_simple(acc, src, 0.0f, 0.5f);
    stamp_simple(single, src, 0.0f, 1.0f);

    float o1[SQUARE_SAMPLES], o2[SQUARE_SAMPLES];
    inverse_cdf53(acc, 0, o1);
    inverse_cdf53(single, 0, o2);

    float d = max_diff_f32(o1, o2, SQUARE_SAMPLES);
    CHECK(d < 1e-5f, "diff = %g", d);
    TEST_PASS();
}

static void test_stamp_cross_square_spill(void) {
    TEST_BEGIN("cross-square spill puts energy in dst_next");
    arena_reset_for_test();
    float impulse[SQUARE_SAMPLES] = {0};
    impulse[0] = 0.5f;

    WaveletSquare *src      = arena_alloc_square(&test_arena, 0);
    WaveletSquare *dst      = arena_alloc_square(&test_arena, 0);
    WaveletSquare *dst_next = arena_alloc_square(&test_arena, 1);
    forward_cdf53(src, 0, impulse);

    StampParams p = {0};
    p.delay_samples = (float)(SQUARE_SAMPLES - 6);
    p.gain          = 1.0f;
    stamp(dst, dst_next, src, &p);

    int found_spill = 0;
    for (int b = WAVELET_LEVELS - 3; b < TOTAL_BANDS; b++)
        for (int i = 0; i < band_size(b); i++)
            if (dst_next->bands[0][b][i] != 0.0f) { found_spill = 1; break; }
    CHECK(found_spill, "no spill into dst_next");
    TEST_PASS();
}

static void test_stamp_no_spill_without_dst_next(void) {
    TEST_BEGIN("stamp with NULL dst_next does not crash");
    arena_reset_for_test();
    float impulse[SQUARE_SAMPLES] = {0};
    impulse[SQUARE_SAMPLES / 2] = 0.5f;

    WaveletSquare *src = arena_alloc_square(&test_arena, 0);
    WaveletSquare *dst = arena_alloc_square(&test_arena, 0);
    forward_cdf53(src, 0, impulse);

    StampParams p = {0};
    p.delay_samples = (float)(SQUARE_SAMPLES - 10);
    p.gain          = 1.0f;
    stamp(dst, NULL, src, &p);
    TEST_PASS();
}

static void test_stamp_negative_delay(void) {
    TEST_BEGIN("negative delay: energy appears before source event");
    arena_reset_for_test();
    float impulse[SQUARE_SAMPLES] = {0};
    impulse[SQUARE_SAMPLES / 2] = 0.5f;

    WaveletSquare *src = arena_alloc_square(&test_arena, 0);
    WaveletSquare *dst = arena_alloc_square(&test_arena, 0);
    forward_cdf53(src, 0, impulse);
    stamp_simple(dst, src, -64.0f, 0.5f);

    float out[SQUARE_SAMPLES];
    inverse_cdf53(dst, 0, out);

    int   peak_pos = 0;
    float peak_val = 0.0f;
    for (int i = 0; i < SQUARE_SAMPLES; i++) {
        float v = fabsf(out[i]);
        if (v > peak_val) { peak_val = v; peak_pos = i; }
    }
    int expected = SQUARE_SAMPLES / 2 - 64;
    CHECK(abs(peak_pos - expected) <= 8,
          "peak at %d, expected ~%d", peak_pos, expected);
    TEST_PASS();
}

static void test_stamp_iq_rotation(void) {
    TEST_BEGIN("I/Q phase rotation: Q channel populated for fractional delay");
    arena_reset_for_test();
    float in[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 440.0f, 0.5f);

    WaveletSquare *src = arena_alloc_square(&test_arena, 0);
    WaveletSquare *dst = arena_alloc_square(&test_arena, 0);
    /* Put energy in BOTH I and Q of src — Q starts at zero unless we put
     * energy there explicitly. We populate Q with a 90°-shifted sine.   */
    forward_cdf53(src, 0, in);
    float in_q[SQUARE_SAMPLES];
    for (int i = 0; i < SQUARE_SAMPLES; i++)
        in_q[i] = 0.5f * cosf(2.0f * (float)M_PI * 440.0f * i / SAMPLE_RATE);
    forward_cdf53(src, 1, in_q);

    /* With a fractional delay, rotation should mix I and Q. */
    stamp_simple(dst, src, 0.7f, 1.0f);

    /* Q channel of dst should be nonzero. */
    float q_sum = 0.0f;
    for (int b = 0; b < TOTAL_BANDS; b++)
        for (int i = 0; i < band_size(b); i++)
            q_sum += fabsf(dst->bands[1][b][i]);
    CHECK(q_sum > 1e-3f, "Q channel sum = %g (expected nonzero)", q_sum);
    TEST_PASS();
}

/* ===========================================================================
 * Section 4: Band coverage
 * =========================================================================*/

static void test_band_frequency_isolation(void) {
    TEST_BEGIN("440 Hz energy concentrated in band 4-6");
    arena_reset_for_test();
    WaveletSquare *sq = arena_alloc_square(&test_arena, 0);
    float in[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 440.0f, 0.8f);
    forward_cdf53(sq, 0, in);

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
    CHECK(max_band >= 4 && max_band <= 6,
          "peak at band %d", max_band);
    TEST_PASS();
}

static void test_band_frequency_8khz(void) {
    TEST_BEGIN("8 kHz energy concentrated in band 0-2");
    arena_reset_for_test();
    WaveletSquare *sq = arena_alloc_square(&test_arena, 0);
    float in[SQUARE_SAMPLES];
    gen_sine(in, SQUARE_SAMPLES, 8000.0f, 0.8f);
    forward_cdf53(sq, 0, in);

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
 * Main
 * =========================================================================*/

int main(void) {
    printf("=================================================================\n");
    printf("Wavelet Core Test Suite (float32)\n");
    printf("SQUARE_SAMPLES=%d  WAVELET_LEVELS=%d  SAMPLE_RATE=%d\n",
           SQUARE_SAMPLES, WAVELET_LEVELS, SAMPLE_RATE);
    printf("=================================================================\n\n");

    printf("[ Section 1: Structure and Arena ]\n");
    test_band_sizes();
    test_band_size_values();
    test_square_init_zeros();
    test_square_band_pointers();
    test_arena_alignment();
    test_arena_save_restore();

    printf("\n[ Section 2: CDF 5/3 Transform ]\n");
    test_roundtrip_silence();
    test_roundtrip_impulse();
    test_roundtrip_sine_440();
    test_roundtrip_sine_80();
    test_roundtrip_sine_12000();
    test_roundtrip_dc();
    test_roundtrip_full_scale();
    test_energy_preservation();
    test_scaling_coefficient_dc();
    test_int16_roundtrip();

    printf("\n[ Section 3: Stamping ]\n");
    test_stamp_zero_delay();
    test_stamp_integer_delay();
    test_stamp_gain();
    test_stamp_accumulation();
    test_stamp_cross_square_spill();
    test_stamp_no_spill_without_dst_next();
    test_stamp_negative_delay();
    test_stamp_iq_rotation();

    printf("\n[ Section 4: Band coverage ]\n");
    test_band_frequency_isolation();
    test_band_frequency_8khz();

    printf("\n=================================================================\n");
    printf("Results: %d/%d passed", tests_passed, tests_run);
    if (tests_failed > 0) printf(", %d FAILED", tests_failed);
    printf("\n=================================================================\n");

    return tests_failed > 0 ? 1 : 0;
}
