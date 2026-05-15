/* src/smold-internal.h
 *
 * Constants shared between C and assembly. Included from .S files via the C
 * preprocessor (gcc -E or as -I plus #include in .S).
 *
 * If you change `struct smold_out` in include/smold.h, update the offsets
 * here and the static asserts in tests/test_layout.c will catch any drift.
 */

#ifndef SMOLD_INTERNAL_H
#define SMOLD_INTERNAL_H

/* struct smold_out offsets (bytes). Matches include/smold.h on LP64. */
#define SMOLD_OUT_BUF       0
#define SMOLD_OUT_CAP       8
#define SMOLD_OUT_LEN      16
#define SMOLD_OUT_NEEDED   24
#define SMOLD_OUT_SIZE     32

/* Return codes (must match include/smold.h). */
#define SMOLD_OK                     0
#define SMOLD_ERR_OUT_OVERFLOW      -1
#define SMOLD_ERR_TRUNCATED_INSN    -2
#define SMOLD_ERR_UNSUPPORTED_LEN   -3
#define SMOLD_ERR_BAD_ARGS          -4

/* Format-string fragments. Defining them here keeps the asm side from
 * embedding magic strings. Note these are *not* used by the asm core
 * itself (which writes bytes directly), but they are the canonical
 * format the test suite compares against.
 */
#define SMOLD_HEX2_PREFIX  ".2byte 0x"
#define SMOLD_HEX4_PREFIX  ".4byte 0x"

#endif /* SMOLD_INTERNAL_H */
