/* include/smold.h
 *
 * Public API for smold-core (M1: fallback walker).
 *
 * The core is hand-written RV64 assembly. This header is the C contract
 * any caller uses. The same header serves the development CLI and any
 * future embedded demo integration.
 *
 * M1 emits one line per instruction:
 *
 *     <8-hex-pc>  .2byte 0xhhhh\n     # for 16-bit instructions (low bits != 11)
 *     <8-hex-pc>  .4byte 0xwwwwwwww\n # for 32-bit instructions (low bits == 11)
 *
 * Longer encodings (48-bit, 64-bit) are not handled in M1. If the low bits
 * indicate a longer encoding, the walker stops and reports an error. This is
 * deliberate: such encodings are extremely rare in user-space RISC-V and
 * SMOLR will not emit them.
 */

#ifndef SMOLD_H
#define SMOLD_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Return codes. */
#define SMOLD_OK                     0
#define SMOLD_ERR_OUT_OVERFLOW      -1  /* output buffer too small */
#define SMOLD_ERR_TRUNCATED_INSN    -2  /* hit end of range mid-instruction */
#define SMOLD_ERR_UNSUPPORTED_LEN   -3  /* >32-bit encoding seen (M1: not handled) */
#define SMOLD_ERR_BAD_ARGS          -4  /* NULL pointers, end < start, etc. */

/* Output writer state.
 *
 * The walker writes textual disassembly into `buf`, advancing `len`. If the
 * buffer fills up, the walker stops with SMOLD_ERR_OUT_OVERFLOW and `len`
 * reflects how much was written before the overflow.
 *
 * cap == 0 with buf == NULL is legal: in that case the walker counts the
 * bytes it *would* have written into `needed` without storing anything,
 * and never returns SMOLD_ERR_OUT_OVERFLOW. This lets a caller size the
 * buffer in a first pass.
 *
 * Fields are public so the C CLI can stream output to stdout in chunks
 * (refilling buf between calls if needed). The asm core treats this as
 * opaque struct memory of known layout — see core.S for offset constants.
 */
struct smold_out {
	char    *buf;     /* output buffer (may be NULL if cap == 0) */
	size_t   cap;     /* capacity in bytes */
	size_t   len;     /* bytes currently written into buf */
	size_t   needed;  /* total bytes that would have been written (overflow-safe) */
};

/* Walk a contiguous range of machine code bytes and emit fallback disassembly.
 *
 *   bytes      pointer to the first instruction
 *   nbytes     length of the code range in bytes (must be a multiple of 2)
 *   pc_base    PC label printed for the first instruction. Subsequent lines
 *              increment by 2 or 4 depending on instruction length.
 *   out        output state (see above)
 *
 * Returns SMOLD_OK on success, or one of SMOLD_ERR_*. On error, `out->len`
 * still reflects everything written before the failure point.
 */
int smold_walk_range(const void *bytes, size_t nbytes,
                     uint64_t pc_base,
                     struct smold_out *out);

/* Detect the length of one RISC-V instruction.
 *
 * Inspects the low 2 (or low 6) bits of `h` and returns:
 *   2  for compressed (16-bit) instructions
 *   4  for standard 32-bit instructions
 *   0  for longer encodings (48-bit, 64-bit, etc.) — caller should treat
 *      this as SMOLD_ERR_UNSUPPORTED_LEN
 *
 * Only the low 16 bits of `h` are inspected; the upper bits are ignored.
 * This matches the RISC-V manual's instruction-length encoding rule.
 */
int smold_insn_length(uint32_t h);

/* Write a textual representation of `h` (16 bits) or `w` (32 bits) into
 * `out`. Used internally by smold_walk_range, exposed here so the M4
 * coverage reporter can reuse them directly.
 *
 * Format: ".2byte 0xhhhh" or ".4byte 0xwwwwwwww" (no leading PC, no trailing
 * newline — caller adds those).
 */
int smold_emit_dot_halfword(uint16_t h, struct smold_out *out);
int smold_emit_dot_word(uint32_t w, struct smold_out *out);

/* Emit a 16-digit lowercase hex PC label followed by two spaces.
 * Used by the walker at the start of each disassembly line. Exposed for
 * the same reason: M4 will want to reuse it.
 */
int smold_emit_pc_label(uint64_t pc, struct smold_out *out);

#ifdef __cplusplus
}
#endif

#endif /* SMOLD_H */
