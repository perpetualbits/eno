/* 05-syscall-only.c
 *
 * Zero external imports. Pure ecall-based "hello world" + exit. This is the
 * baseline: SMOLR must produce an ELF at least this small for the no-import
 * case, and the resolver+stubs overhead is measured against this number.
 */

void _start(void)
{
	const char msg[] = "syscall hi\n";

	/* write(1, msg, sizeof(msg)-1) */
	register long  a7 __asm__("a7") = 64;	/* SYS_write */
	register long  a0 __asm__("a0") = 1;
	register const char *a1 __asm__("a1") = msg;
	register long  a2 __asm__("a2") = sizeof(msg) - 1;
	__asm__ volatile ("ecall"
		: "+r"(a0)
		: "r"(a7), "r"(a1), "r"(a2));

	/* exit(0) */
	register long e7 __asm__("a7") = 93;
	register long e0 __asm__("a0") = 0;
	__asm__ volatile ("ecall" :: "r"(e7), "r"(e0));
	__builtin_unreachable();
}
