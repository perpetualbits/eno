/* src/core.S
 *
 * smold M1 fallback walker — hand-written RV64 assembly.
 *
 * Target: -march=rv64gc_zba_zbb_zbs -mabi=lp64d (Jupiter/Mars baseline).
 *
 * Atoms (each in its own .text.<name> section, see asm-macros.h):
 *
 *   smold_insn_length          public  — return 2/4/0 for instruction length
 *   smold_out_put_byte         local   — append one byte to a smold_out
 *   smold_out_put_bytes        local   — append a run of bytes
 *   smold_emit_hex_nibble      local   — emit one lowercase hex digit
 *   smold_emit_hex_u16         public  — emit 4 hex digits (uint16_t)
 *   smold_emit_hex_u32         public  — emit 8 hex digits (uint32_t)
 *   smold_emit_hex_u64         local   — emit 16 hex digits (uint64_t)
 *   smold_emit_pc_label        public  — emit "ppppppppppppp  " (PC + 2 sp)
 *   smold_emit_dot_halfword    public  — emit ".2byte 0xhhhh"
 *   smold_emit_dot_word        public  — emit ".4byte 0xwwwwwwww"
 *   smold_walk_range           public  — top-level walker
 *
 * Calling convention: standard RISC-V LP64D. Callee preserves s0..s11.
 * Stack frames are 16-byte aligned.
 *
 * All emit_* atoms return SMOLD_OK or SMOLD_ERR_OUT_OVERFLOW in a0.
 * Callers check `bnez a0, ...` to short-circuit on overflow.
 */

#include "asm-macros.h"
#include "smold-internal.h"

	.option pic

/* ====================================================================== *
 *  smold_insn_length
 * ====================================================================== *
 *
 * int smold_insn_length(uint32_t h);
 *
 * RISC-V instruction-length encoding (RVI manual §1.5):
 *   low2 != 11                          → 16-bit (compressed)
 *   low2 == 11 and bits[4:2] != 111     → 32-bit (standard)
 *   anything else                       → 48-bit or longer (M1 doesn't handle)
 */
FUNC smold_insn_length
	andi    t0, a0, 3
	li      t1, 3
	bne     t0, t1, .Lil_16
	andi    t0, a0, 0x1c
	li      t1, 0x1c
	beq     t0, t1, .Lil_long
	li      a0, 4
	ret
.Lil_16:
	li      a0, 2
	ret
.Lil_long:
	li      a0, 0
	ret
ENDFUNC smold_insn_length

/* ====================================================================== *
 *  smold_out_put_byte   (local)
 * ====================================================================== *
 *
 *   a0 = struct smold_out *
 *   a1 = byte value (low 8 bits)
 *
 * Returns SMOLD_OK or SMOLD_ERR_OUT_OVERFLOW in a0.
 * Always increments .needed. Only stores into .buf when .len < .cap.
 *
 * Clobbers: t0, t1, t2 (caller-saved).
 */
LOCAL_FUNC smold_out_put_byte
	ld      t0, SMOLD_OUT_NEEDED(a0)
	addi    t0, t0, 1
	sd      t0, SMOLD_OUT_NEEDED(a0)

	ld      t0, SMOLD_OUT_LEN(a0)
	ld      t1, SMOLD_OUT_CAP(a0)
	bgeu    t0, t1, .Lpb_no_store

	ld      t2, SMOLD_OUT_BUF(a0)
	add     t2, t2, t0
	sb      a1, 0(t2)
	addi    t0, t0, 1
	sd      t0, SMOLD_OUT_LEN(a0)
	li      a0, SMOLD_OK
	ret
.Lpb_no_store:
	/* If cap is zero we are in count-only mode — not an error. */
	beqz    t1, .Lpb_count_only
	li      a0, SMOLD_ERR_OUT_OVERFLOW
	ret
.Lpb_count_only:
	li      a0, SMOLD_OK
	ret
ENDLOCAL_FUNC smold_out_put_byte

/* ====================================================================== *
 *  smold_out_put_bytes   (local)
 * ====================================================================== *
 *
 *   a0 = struct smold_out *
 *   a1 = const char *src
 *   a2 = size_t n
 *
 * Returns SMOLD_OK if all n bytes fit, SMOLD_ERR_OUT_OVERFLOW if any
 * didn't. .needed is bumped by n regardless.
 *
 * Clobbers: t0..t6.
 */
LOCAL_FUNC smold_out_put_bytes
	beqz    a2, .Lpbs_ok

	/* Always bump .needed by n, even on overflow or count-only. */
	ld      t0, SMOLD_OUT_NEEDED(a0)
	add     t0, t0, a2
	sd      t0, SMOLD_OUT_NEEDED(a0)

	ld      t0, SMOLD_OUT_LEN(a0)
	ld      t1, SMOLD_OUT_CAP(a0)
	bgeu    t0, t1, .Lpbs_no_store

	sub     t2, t1, t0              /* free = cap - len  (> 0 here) */

	/* copy = min(n, free).  t3 saves n for the partial-vs-full check. */
	mv      t3, a2
	bgeu    a2, t2, 1f
	mv      t2, a2
1:
	ld      t4, SMOLD_OUT_BUF(a0)
	add     t4, t4, t0              /* dst = buf + len */
	mv      t5, a1                  /* src */
	mv      t6, t2                  /* count */
2:
	lbu     a3, 0(t5)
	sb      a3, 0(t4)
	addi    t4, t4, 1
	addi    t5, t5, 1
	addi    t6, t6, -1
	bnez    t6, 2b

	add     t0, t0, t2
	sd      t0, SMOLD_OUT_LEN(a0)

	bne     t2, t3, .Lpbs_overflow
.Lpbs_ok:
	li      a0, SMOLD_OK
	ret
.Lpbs_no_store:
	/* cap == 0 → count-only mode, OK. Otherwise overflow. */
	beqz    t1, .Lpbs_ok
.Lpbs_overflow:
	li      a0, SMOLD_ERR_OUT_OVERFLOW
	ret
ENDLOCAL_FUNC smold_out_put_bytes

/* ====================================================================== *
 *  smold_emit_hex_nibble   (local)
 * ====================================================================== *
 *
 *   a0 = struct smold_out *
 *   a1 = nibble (low 4 bits)
 *
 * Returns SMOLD_OK / SMOLD_ERR_OUT_OVERFLOW.
 */
LOCAL_FUNC smold_emit_hex_nibble
	andi    a1, a1, 0xf
	li      t0, 10
	bltu    a1, t0, 1f
	addi    a1, a1, 39              /* 'a' - '0' - 10 */
1:
	addi    a1, a1, '0'
	tail    smold_out_put_byte
ENDLOCAL_FUNC smold_emit_hex_nibble

/* ====================================================================== *
 *  smold_emit_hex_u16   (public)
 * ====================================================================== *
 *
 *   a0 = struct smold_out *
 *   a1 = uint16_t value (only low 16 bits used)
 *
 * Emits 4 lowercase hex digits.
 */
FUNC smold_emit_hex_u16
	addi    sp, sp, -32
	sd      ra, 0(sp)
	sd      s0, 8(sp)
	sd      s1, 16(sp)
	sd      s2, 24(sp)
	mv      s0, a0
	mv      s1, a1
	li      s2, 12
1:
	mv      a0, s0
	srl     a1, s1, s2
	call    smold_emit_hex_nibble
	bnez    a0, 8f
	addi    s2, s2, -4
	bgez    s2, 1b
	li      a0, SMOLD_OK
8:
	ld      ra, 0(sp)
	ld      s0, 8(sp)
	ld      s1, 16(sp)
	ld      s2, 24(sp)
	addi    sp, sp, 32
	ret
ENDFUNC smold_emit_hex_u16

/* ====================================================================== *
 *  smold_emit_hex_u32   (public)
 * ====================================================================== *
 *
 *   a0 = struct smold_out *
 *   a1 = uint32_t value
 *
 * Emits 8 lowercase hex digits.
 */
FUNC smold_emit_hex_u32
	addi    sp, sp, -32
	sd      ra, 0(sp)
	sd      s0, 8(sp)
	sd      s1, 16(sp)
	sd      s2, 24(sp)
	mv      s0, a0
	mv      s1, a1
	li      s2, 28
1:
	mv      a0, s0
	srl     a1, s1, s2
	call    smold_emit_hex_nibble
	bnez    a0, 8f
	addi    s2, s2, -4
	bgez    s2, 1b
	li      a0, SMOLD_OK
8:
	ld      ra, 0(sp)
	ld      s0, 8(sp)
	ld      s1, 16(sp)
	ld      s2, 24(sp)
	addi    sp, sp, 32
	ret
ENDFUNC smold_emit_hex_u32

/* ====================================================================== *
 *  smold_emit_hex_u64   (local — used for PC labels)
 * ====================================================================== *
 *
 *   a0 = struct smold_out *
 *   a1 = uint64_t value
 *
 * Emits 16 lowercase hex digits.
 */
LOCAL_FUNC smold_emit_hex_u64
	addi    sp, sp, -32
	sd      ra, 0(sp)
	sd      s0, 8(sp)
	sd      s1, 16(sp)
	sd      s2, 24(sp)
	mv      s0, a0
	mv      s1, a1
	li      s2, 60
1:
	mv      a0, s0
	srl     a1, s1, s2
	call    smold_emit_hex_nibble
	bnez    a0, 8f
	addi    s2, s2, -4
	bgez    s2, 1b
	li      a0, SMOLD_OK
8:
	ld      ra, 0(sp)
	ld      s0, 8(sp)
	ld      s1, 16(sp)
	ld      s2, 24(sp)
	addi    sp, sp, 32
	ret
ENDLOCAL_FUNC smold_emit_hex_u64

/* ====================================================================== *
 *  smold_emit_pc_label   (public)
 * ====================================================================== *
 *
 *   a0 = struct smold_out *
 *   a1 = pc (uint64_t)
 *
 * Emits "pppppppppppppppp  " (16 hex digits + two spaces).
 */
FUNC smold_emit_pc_label
	addi    sp, sp, -16
	sd      ra, 0(sp)
	sd      s0, 8(sp)
	mv      s0, a0
	call    smold_emit_hex_u64
	bnez    a0, 8f
	mv      a0, s0
	li      a1, ' '
	call    smold_out_put_byte
	bnez    a0, 8f
	mv      a0, s0
	li      a1, ' '
	call    smold_out_put_byte
8:
	ld      ra, 0(sp)
	ld      s0, 8(sp)
	addi    sp, sp, 16
	ret
ENDFUNC smold_emit_pc_label

/* ====================================================================== *
 *  smold_emit_dot_halfword   (public)
 * ====================================================================== *
 *
 *   a0 = struct smold_out *
 *   a1 = uint16_t value
 *
 * Emits ".2byte 0xhhhh" — no PC prefix, no newline.
 */
FUNC smold_emit_dot_halfword
	addi    sp, sp, -32
	sd      ra, 0(sp)
	sd      s0, 8(sp)
	sd      s1, 16(sp)
	mv      s0, a0
	mv      s1, a1                  /* preserve value across put_bytes */

	la      a1, .Lstr_dot_halfword
	li      a2, 9                   /* strlen(".2byte 0x") */
	mv      a0, s0
	call    smold_out_put_bytes
	bnez    a0, 8f

	mv      a0, s0
	mv      a1, s1
	call    smold_emit_hex_u16
8:
	ld      ra, 0(sp)
	ld      s0, 8(sp)
	ld      s1, 16(sp)
	addi    sp, sp, 32
	ret
ENDFUNC smold_emit_dot_halfword

/* ====================================================================== *
 *  smold_emit_dot_word   (public)
 * ====================================================================== *
 *
 *   a0 = struct smold_out *
 *   a1 = uint32_t value
 *
 * Emits ".4byte 0xwwwwwwww" — no PC prefix, no newline.
 */
FUNC smold_emit_dot_word
	addi    sp, sp, -32
	sd      ra, 0(sp)
	sd      s0, 8(sp)
	sd      s1, 16(sp)
	mv      s0, a0
	mv      s1, a1

	la      a1, .Lstr_dot_word
	li      a2, 9                   /* strlen(".4byte 0x") */
	mv      a0, s0
	call    smold_out_put_bytes
	bnez    a0, 8f

	mv      a0, s0
	mv      a1, s1
	call    smold_emit_hex_u32
8:
	ld      ra, 0(sp)
	ld      s0, 8(sp)
	ld      s1, 16(sp)
	addi    sp, sp, 32
	ret
ENDFUNC smold_emit_dot_word

/* ====================================================================== *
 *  smold_walk_range   (public)
 * ====================================================================== *
 *
 *   a0 = const void *bytes
 *   a1 = size_t nbytes
 *   a2 = uint64_t pc_base
 *   a3 = struct smold_out *out
 *
 * Walks the range, emitting one line per instruction:
 *
 *   <pc>  .2byte 0xhhhh\n        (if low2 != 11)
 *   <pc>  .4byte 0xwwwwwwww\n    (if low2 == 11 and bits[4:2] != 111)
 *
 * Returns:
 *   SMOLD_OK                 entire range walked
 *   SMOLD_ERR_OUT_OVERFLOW   output buffer filled
 *   SMOLD_ERR_TRUNCATED_INSN end of range hit mid-instruction
 *   SMOLD_ERR_UNSUPPORTED_LEN  hit a 48-bit-or-longer encoding
 *   SMOLD_ERR_BAD_ARGS       NULL pointers or odd nbytes
 *
 * Register usage (callee-saved across the loop):
 *   s0 = current bytes pointer (advances)
 *   s1 = end pointer (bytes + nbytes)
 *   s2 = current pc
 *   s3 = out pointer
 */
FUNC smold_walk_range
	/* Argument validation. */
	beqz    a0, .Lwr_bad
	beqz    a3, .Lwr_bad
	andi    t0, a1, 1
	bnez    t0, .Lwr_bad            /* odd nbytes not allowed */
	andi    t0, a0, 1
	bnez    t0, .Lwr_bad            /* odd start pointer not allowed */

	addi    sp, sp, -48
	sd      ra, 0(sp)
	sd      s0, 8(sp)
	sd      s1, 16(sp)
	sd      s2, 24(sp)
	sd      s3, 32(sp)

	mv      s0, a0
	add     s1, a0, a1
	mv      s2, a2
	mv      s3, a3

	beq     s0, s1, .Lwr_ok         /* empty range */

.Lwr_loop:
	/* Need at least 2 bytes for an instruction. */
	sub     t0, s1, s0
	li      t1, 2
	bltu    t0, t1, .Lwr_trunc

	lhu     t2, 0(s0)               /* low 16 bits */

	/* PC prefix. */
	mv      a0, s3
	mv      a1, s2
	call    smold_emit_pc_label
	bnez    a0, .Lwr_exit_err

	/* Length detection. Inlined for speed (and to avoid clobbering t2). */
	andi    t0, t2, 3
	li      t1, 3
	bne     t0, t1, .Lwr_emit16

	andi    t0, t2, 0x1c
	li      t1, 0x1c
	beq     t0, t1, .Lwr_long

	/* 32-bit instruction. Need 4 bytes available. */
	sub     t0, s1, s0
	li      t1, 4
	bltu    t0, t1, .Lwr_trunc

	lwu     t3, 0(s0)               /* full 32-bit word */
	mv      a0, s3
	mv      a1, t3
	call    smold_emit_dot_word
	bnez    a0, .Lwr_exit_err

	mv      a0, s3
	li      a1, '\n'
	call    smold_out_put_byte
	bnez    a0, .Lwr_exit_err

	addi    s0, s0, 4
	addi    s2, s2, 4
	bne     s0, s1, .Lwr_loop
	j       .Lwr_ok

.Lwr_emit16:
	mv      a0, s3
	mv      a1, t2
	call    smold_emit_dot_halfword
	bnez    a0, .Lwr_exit_err

	mv      a0, s3
	li      a1, '\n'
	call    smold_out_put_byte
	bnez    a0, .Lwr_exit_err

	addi    s0, s0, 2
	addi    s2, s2, 2
	bne     s0, s1, .Lwr_loop

.Lwr_ok:
	li      a0, SMOLD_OK
	j       .Lwr_exit

.Lwr_trunc:
	li      a0, SMOLD_ERR_TRUNCATED_INSN
	j       .Lwr_exit

.Lwr_long:
	li      a0, SMOLD_ERR_UNSUPPORTED_LEN
	j       .Lwr_exit

.Lwr_exit_err:
	/* a0 already holds the error code. */
.Lwr_exit:
	ld      ra, 0(sp)
	ld      s0, 8(sp)
	ld      s1, 16(sp)
	ld      s2, 24(sp)
	ld      s3, 32(sp)
	addi    sp, sp, 48
	ret

.Lwr_bad:
	li      a0, SMOLD_ERR_BAD_ARGS
	ret
ENDFUNC smold_walk_range

/* ====================================================================== *
 *  Strings   (rodata)
 * ====================================================================== *
 *
 * Each string in its own .rodata.<name> section so --gc-sections can drop
 * them when the corresponding emitter is unused.
 */

	.section .rodata.smold_str_dot_halfword, "a", @progbits
	.balign 2
.Lstr_dot_halfword:
	.ascii  ".2byte 0x"

	.section .rodata.smold_str_dot_word, "a", @progbits
	.balign 2
.Lstr_dot_word:
	.ascii  ".4byte 0x"
