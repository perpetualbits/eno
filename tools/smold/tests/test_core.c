/* tests/test_core.c
 *
 * Unit tests for smold-core. Builds for RV64, runs natively on the boards
 * or under qemu-user. Returns 0 on success, non-zero on first failure.
 *
 * Coverage:
 *   - smold_insn_length: every 5-bit pattern at the low end
 *   - smold_emit_hex_u16 / u32
 *   - smold_emit_pc_label
 *   - smold_emit_dot_halfword / dot_word
 *   - smold_walk_range: empty range, one C insn, one 32-bit insn, mixed
 *   - overflow handling: tiny buffer, .needed reflects total
 *   - bad-arg handling
 *   - truncated-instruction handling
 *   - unsupported-length handling (48-bit encoding)
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "smold.h"

static int fails = 0;

#define CHECK(cond) do { \
	if (!(cond)) { \
		fprintf(stderr, "FAIL %s:%d  %s\n", __FILE__, __LINE__, #cond); \
		fails++; \
	} \
} while (0)

#define CHECK_STR(actual, expected) do { \
	if (strcmp((actual), (expected)) != 0) { \
		fprintf(stderr, "FAIL %s:%d  expected %s, got %s\n", \
		    __FILE__, __LINE__, #expected, (actual)); \
		fails++; \
	} \
} while (0)

static void reset(struct smold_out *o, char *buf, size_t cap)
{
	o->buf = buf;
	o->cap = cap;
	o->len = 0;
	o->needed = 0;
}

static void test_insn_length(void)
{
	/* low2 != 11 → compressed (2). 4 cases: 00, 01, 10, plus 11-variants. */
	CHECK(smold_insn_length(0x0000) == 2);
	CHECK(smold_insn_length(0x0001) == 2);
	CHECK(smold_insn_length(0x0002) == 2);
	CHECK(smold_insn_length(0xffff) == 0);  /* low2=11, bits[4:2]=111 → long */

	/* 32-bit: low2 == 11, bits[4:2] != 111. */
	CHECK(smold_insn_length(0x0003) == 4);  /* low2=11, bits[4:2]=000 */
	CHECK(smold_insn_length(0x000b) == 4);  /* bits[4:2]=010 */
	CHECK(smold_insn_length(0x0013) == 4);  /* bits[4:2]=100 */
	CHECK(smold_insn_length(0x001b) == 4);  /* bits[4:2]=110 */

	/* 48-bit: low6 == 011111. */
	CHECK(smold_insn_length(0x001f) == 0);
	/* 64-bit: low7 == 0111111. */
	CHECK(smold_insn_length(0x003f) == 0);
}

static void test_hex_u16(void)
{
	char b[5];
	struct smold_out o;
	reset(&o, b, sizeof b);
	CHECK(smold_emit_hex_u16(&o, 0x1234) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, "1234");
	CHECK(o.needed == 4);

	reset(&o, b, sizeof b);
	CHECK(smold_emit_hex_u16(&o, 0xabcd) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, "abcd");

	reset(&o, b, sizeof b);
	CHECK(smold_emit_hex_u16(&o, 0x0000) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, "0000");

	reset(&o, b, sizeof b);
	CHECK(smold_emit_hex_u16(&o, 0xffff) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, "ffff");
}

static void test_hex_u32(void)
{
	char b[9];
	struct smold_out o;
	reset(&o, b, sizeof b);
	CHECK(smold_emit_hex_u32(&o, 0xdeadbeef) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, "deadbeef");

	reset(&o, b, sizeof b);
	CHECK(smold_emit_hex_u32(&o, 0) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, "00000000");
}

static void test_pc_label(void)
{
	char b[64];
	struct smold_out o;
	reset(&o, b, sizeof b);
	CHECK(smold_emit_pc_label(&o, 0x1234) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, "0000000000001234  ");
	CHECK(o.len == 18);  /* 16 hex + 2 spaces */
	CHECK(o.needed == 18);
}

static void test_dot_halfword(void)
{
	char b[32];
	struct smold_out o;
	reset(&o, b, sizeof b);
	CHECK(smold_emit_dot_halfword(&o, 0x1141) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, ".2byte 0x1141");
	CHECK(o.len == 13);
}

static void test_dot_word(void)
{
	char b[32];
	struct smold_out o;
	reset(&o, b, sizeof b);
	CHECK(smold_emit_dot_word(&o, 0x00000517) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, ".4byte 0x00000517");
	CHECK(o.len == 17);
}

static void test_walk_empty(void)
{
	char b[64];
	struct smold_out o;
	reset(&o, b, sizeof b);
	uint8_t bytes[] = { 0 };
	CHECK(smold_walk_range(bytes, 0, 0, &o) == SMOLD_OK);
	CHECK(o.len == 0);
	CHECK(o.needed == 0);
}

static void test_walk_one_compressed(void)
{
	char b[128];
	struct smold_out o;
	reset(&o, b, sizeof b);
	uint8_t bytes[] = { 0x41, 0x11 };   /* 0x1141: c.addi sp,-16 */
	CHECK(smold_walk_range(bytes, 2, 0x1000, &o) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, "0000000000001000  .2byte 0x1141\n");
}

static void test_walk_one_32bit(void)
{
	char b[128];
	struct smold_out o;
	reset(&o, b, sizeof b);
	uint8_t bytes[] = { 0x17, 0x05, 0x00, 0x00 };  /* 0x00000517: auipc a0,0 */
	CHECK(smold_walk_range(bytes, 4, 0x2000, &o) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b, "0000000000002000  .4byte 0x00000517\n");
}

static void test_walk_mixed(void)
{
	char b[256];
	struct smold_out o;
	reset(&o, b, sizeof b);
	uint8_t bytes[] = {
		0x41, 0x11,                   /* c.addi sp,-16     @ pc */
		0x17, 0x05, 0x00, 0x00,       /* auipc a0,0        @ pc+2 */
		0x06, 0xe4,                   /* c.sdsp ra,8(sp)   @ pc+6 */
	};
	CHECK(smold_walk_range(bytes, 8, 0x1000, &o) == SMOLD_OK);
	b[o.len] = 0;
	CHECK_STR(b,
		"0000000000001000  .2byte 0x1141\n"
		"0000000000001002  .4byte 0x00000517\n"
		"0000000000001006  .2byte 0xe406\n");
}

static void test_walk_overflow(void)
{
	char b[8];                       /* tiny */
	struct smold_out o;
	reset(&o, b, sizeof b);
	uint8_t bytes[] = { 0x41, 0x11 };
	int r = smold_walk_range(bytes, 2, 0x1000, &o);
	CHECK(r == SMOLD_ERR_OUT_OVERFLOW);
	CHECK(o.len == 8);
	/* Expected total: "0000000000001000  .2byte 0x1141\n" = 18+13+1 = 32 */
	CHECK(o.needed == 32);
}

static void test_walk_count_only(void)
{
	struct smold_out o = { NULL, 0, 0, 0 };
	uint8_t bytes[] = {
		0x41, 0x11,
		0x17, 0x05, 0x00, 0x00,
	};
	int r = smold_walk_range(bytes, 6, 0x1000, &o);
	/* cap == 0 is count-only mode; not an overflow error. */
	CHECK(r == SMOLD_OK);
	CHECK(o.len == 0);
	/* "0000000000001000  .2byte 0x1141\n" (32) +
	   "0000000000001002  .4byte 0x00000517\n" (36) = 68 */
	CHECK(o.needed == 68);
}

static void test_walk_bad_args(void)
{
	char b[64];
	struct smold_out o;
	reset(&o, b, sizeof b);
	uint8_t bytes[] = { 0x41, 0x11 };

	CHECK(smold_walk_range(NULL, 2, 0, &o) == SMOLD_ERR_BAD_ARGS);
	CHECK(smold_walk_range(bytes, 2, 0, NULL) == SMOLD_ERR_BAD_ARGS);
	CHECK(smold_walk_range(bytes, 1, 0, &o) == SMOLD_ERR_BAD_ARGS);  /* odd len */
	CHECK(smold_walk_range(bytes + 1, 2, 0, &o) == SMOLD_ERR_BAD_ARGS);  /* odd ptr */
}

static void test_walk_unsupported_len(void)
{
	char b[128];
	struct smold_out o;
	reset(&o, b, sizeof b);
	/* 48-bit encoding marker: low6 == 011111 = 0x1f. */
	uint8_t bytes[] = { 0x1f, 0x00, 0x00, 0x00, 0x00, 0x00 };
	int r = smold_walk_range(bytes, 6, 0x1000, &o);
	CHECK(r == SMOLD_ERR_UNSUPPORTED_LEN);
}

static void test_walk_truncated(void)
{
	char b[128];
	struct smold_out o;
	reset(&o, b, sizeof b);
	/* Only 2 bytes of what claims to be a 32-bit instruction. */
	uint8_t bytes[] = { 0x03, 0x00 };  /* low2=11, bits[4:2]=000 → 32-bit */
	int r = smold_walk_range(bytes, 2, 0x1000, &o);
	CHECK(r == SMOLD_ERR_TRUNCATED_INSN);
}

int main(void)
{
	test_insn_length();
	test_hex_u16();
	test_hex_u32();
	test_pc_label();
	test_dot_halfword();
	test_dot_word();
	test_walk_empty();
	test_walk_one_compressed();
	test_walk_one_32bit();
	test_walk_mixed();
	test_walk_overflow();
	test_walk_count_only();
	test_walk_bad_args();
	test_walk_unsupported_len();
	test_walk_truncated();

	if (fails) {
		fprintf(stderr, "\n%d test(s) FAILED\n", fails);
		return 1;
	}
	printf("all tests passed\n");
	return 0;
}
