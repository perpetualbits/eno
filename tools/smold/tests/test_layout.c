/* tests/test_layout.c
 *
 * Compile-time assertions that the C struct layout matches the offset
 * constants used by the assembly. If this file compiles, the asm and C
 * agree on smold_out's shape. If not, fix one or the other.
 */

#include <stddef.h>
#include <assert.h>
#include "smold.h"
#include "smold-internal.h"

static_assert(offsetof(struct smold_out, buf)    == SMOLD_OUT_BUF,
              "SMOLD_OUT_BUF offset drift");
static_assert(offsetof(struct smold_out, cap)    == SMOLD_OUT_CAP,
              "SMOLD_OUT_CAP offset drift");
static_assert(offsetof(struct smold_out, len)    == SMOLD_OUT_LEN,
              "SMOLD_OUT_LEN offset drift");
static_assert(offsetof(struct smold_out, needed) == SMOLD_OUT_NEEDED,
              "SMOLD_OUT_NEEDED offset drift");
static_assert(sizeof(struct smold_out) == SMOLD_OUT_SIZE,
              "SMOLD_OUT_SIZE drift");

int main(void) { return 0; }
