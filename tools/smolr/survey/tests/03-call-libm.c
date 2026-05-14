/* 03-call-libm.c
 *
 * Call into a second shared library (libm) to verify that DT_NEEDED ordering
 * and per-library symbol resolution work the same way for non-libc calls.
 * Linking will need -lm.
 */

extern double sqrt(double x);
extern int puts(const char *s);

void _start(void)
{
	volatile double x = 2.0;
	volatile double r = sqrt(x);
	if (r > 1.4)
		puts("ok");
	register long a7 __asm__("a7") = 93;
	register long a0 __asm__("a0") = 0;
	__asm__ volatile ("ecall" :: "r"(a7), "r"(a0));
	__builtin_unreachable();
}
