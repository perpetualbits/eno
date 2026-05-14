/* 02-call-multi.c
 *
 * Multiple external calls. We want to see whether the toolchain emits one
 * GOT slot per symbol, whether repeated calls share an entry, and whether
 * the relocation pattern is uniform across invocations.
 *
 * Also includes one external data symbol (stdout) — this is expected to
 * produce a relocation pattern SMOLR does not (yet) support, and the survey
 * report will flag it.
 */

extern int puts(const char *s);
extern int fputs(const char *s, void *stream);
extern void *stdout;

void _start(void)
{
	puts("a");
	puts("b");
	fputs("c", stdout);
	register long a7 __asm__("a7") = 93;
	register long a0 __asm__("a0") = 0;
	__asm__ volatile ("ecall" :: "r"(a7), "r"(a0));
	__builtin_unreachable();
}
