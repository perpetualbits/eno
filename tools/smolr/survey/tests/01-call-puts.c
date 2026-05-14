/* 01-call-puts.c
 *
 * The simplest external call. Expected to generate R_RISCV_CALL_PLT (or
 * R_RISCV_CALL with -fno-plt) plus the paired R_RISCV_RELAX. This is the
 * absolute floor of what SMOLR must support for Phase 3.
 */

extern int puts(const char *s);

void _start(void)
{
	puts("hi");
	/* Exit via raw syscall so we don't pull in exit() and pollute relocs. */
	register long a7 __asm__("a7") = 93;	/* SYS_exit */
	register long a0 __asm__("a0") = 0;
	__asm__ volatile ("ecall" :: "r"(a7), "r"(a0));
	__builtin_unreachable();
}
