/* src/asm-macros.h
 *
 * Section-per-function macros from the smold design doc §14. Each function
 * gets its own .text.<name> section so that --gc-sections can drop unused
 * atoms cleanly.
 *
 * Usage:
 *
 *   #include "asm-macros.h"
 *
 *   FUNC smold_walk_range
 *           addi    sp, sp, -16
 *           ...
 *           ret
 *   ENDFUNC smold_walk_range
 *
 * Per-feature rodata gets a similar treatment via the RODATA / ENDRODATA
 * macros. Keep tables in their own sections so they too are gc-able.
 */

#ifndef SMOLD_ASM_MACROS_H
#define SMOLD_ASM_MACROS_H

.macro FUNC name
	.section .text.\name, "ax", @progbits
	.globl  \name
	.type   \name, @function
	.balign 2
\name:
.endm

.macro ENDFUNC name
	.size   \name, .-\name
.endm

.macro LOCAL_FUNC name
	.section .text.\name, "ax", @progbits
	.type   \name, @function
	.balign 2
\name:
.endm

.macro ENDLOCAL_FUNC name
	.size   \name, .-\name
.endm

.macro RODATA name
	.section .rodata.\name, "a", @progbits
	.balign 2
\name:
.endm

.macro ENDRODATA name
	.size   \name, .-\name
.endm

#endif /* SMOLD_ASM_MACROS_H */
