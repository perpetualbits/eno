/* 04-call-indirect.c
 *
 * Take the address of an external function and call through it. This usually
 * produces a different relocation pattern from a direct call (typically GOT-
 * based: R_RISCV_GOT_HI20 + R_RISCV_PCREL_LO12_I). SMOLR may not want to
 * support indirect-call patterns in Phase 1; the survey tells us how
 * painful supporting them would be.
 */

extern int puts(const char *s);

void _start(void)
{
	int (*p)(const char *) = puts;
	p("indirect");
	register long a7 __asm__("a7") = 93;
	register long a0 __asm__("a0") = 0;
	__asm__ volatile ("ecall" :: "r"(a7), "r"(a0));
	__builtin_unreachable();
}
