/* cli/smold-cli.c
 *
 * smold development CLI. Thin C wrapper around smold-core (asm).
 *
 * Three modes:
 *   smold --bytes <file>     disassemble raw bytes from a file
 *   smold --bytes -          disassemble raw bytes from stdin
 *   smold --elf <file>       find the executable PT_LOAD in an ELF and walk it
 *
 * Optional flags:
 *   --pc <hex>               override PC base (default: 0 for bytes mode,
 *                              the segment's p_vaddr for ELF mode)
 *   -h, --help               this message
 *
 * Output goes to stdout. Exit status: 0 on full success, non-zero otherwise.
 *
 * This file builds for the RISC-V target (it's linked against the asm core)
 * but uses no asm itself. Run on the boards natively, or under qemu-user
 * for laptop iteration:
 *
 *     qemu-riscv64 -L /usr/riscv64-linux-gnu ./build/smold --elf foo
 */

#include <elf.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include "smold.h"

#define BUF_SIZE  (64 * 1024)

static void usage(FILE *f)
{
	fputs(
"smold — RISC-V fallback disassembler (M1)\n"
"\n"
"Usage:\n"
"  smold --bytes <file>     disassemble raw bytes from a file\n"
"  smold --bytes -          disassemble raw bytes from stdin\n"
"  smold --elf <file>       walk the executable PT_LOAD of an ELF\n"
"\n"
"Options:\n"
"  --pc <hex>               override PC base (e.g. --pc 0x1000)\n"
"  -h, --help               this message\n"
"\n"
"Output goes to stdout. Each line is:\n"
"  <16-hex-pc>  .2byte 0xhhhh         for compressed instructions\n"
"  <16-hex-pc>  .4byte 0xwwwwwwww     for standard 32-bit instructions\n"
"  (longer encodings are reported as errors)\n",
	    f);
}

/* Drain a struct smold_out to stdout and reset its len/needed counters.
 * Used by the caller when it wants to stream output rather than hold it
 * all in memory.
 */
static int flush_out(struct smold_out *out)
{
	if (out->len == 0) return 0;
	size_t off = 0;
	while (off < out->len) {
		ssize_t w = write(STDOUT_FILENO, out->buf + off, out->len - off);
		if (w < 0) {
			if (errno == EINTR) continue;
			perror("write");
			return -1;
		}
		off += (size_t)w;
	}
	out->len = 0;
	out->needed = 0;
	return 0;
}

/* Read an entire file into a malloc'd buffer. Returns 0 on success and
 * fills *out_data / *out_size, otherwise -1 with an error printed.
 * If `path` is "-", reads from stdin.
 */
static int slurp(const char *path, void **out_data, size_t *out_size)
{
	int fd;
	if (strcmp(path, "-") == 0) {
		fd = STDIN_FILENO;
	} else {
		fd = open(path, O_RDONLY);
		if (fd < 0) { perror(path); return -1; }
	}

	size_t cap = 64 * 1024, len = 0;
	char *data = malloc(cap);
	if (!data) { perror("malloc"); if (fd != STDIN_FILENO) close(fd); return -1; }

	for (;;) {
		if (len == cap) {
			cap *= 2;
			char *n = realloc(data, cap);
			if (!n) { perror("realloc"); free(data); if (fd != STDIN_FILENO) close(fd); return -1; }
			data = n;
		}
		ssize_t r = read(fd, data + len, cap - len);
		if (r < 0) {
			if (errno == EINTR) continue;
			perror("read");
			free(data);
			if (fd != STDIN_FILENO) close(fd);
			return -1;
		}
		if (r == 0) break;
		len += (size_t)r;
	}
	if (fd != STDIN_FILENO) close(fd);

	*out_data = data;
	*out_size = len;
	return 0;
}

/* ELF mode: mmap, find the first executable PT_LOAD segment, walk it. */
static int do_elf(const char *path, int pc_override, uint64_t pc_base_arg)
{
	int fd = open(path, O_RDONLY);
	if (fd < 0) { perror(path); return 1; }
	struct stat st;
	if (fstat(fd, &st) < 0) { perror("fstat"); close(fd); return 1; }
	if (st.st_size < (off_t)sizeof(Elf64_Ehdr)) {
		fprintf(stderr, "%s: too small to be an ELF\n", path);
		close(fd);
		return 1;
	}
	void *map = mmap(NULL, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, fd, 0);
	close(fd);
	if (map == MAP_FAILED) { perror("mmap"); return 1; }

	const unsigned char *base = map;
	if (memcmp(base, "\x7f""ELF", 4) != 0) {
		fprintf(stderr, "%s: not an ELF file\n", path);
		munmap(map, (size_t)st.st_size);
		return 1;
	}
	if (base[EI_CLASS] != ELFCLASS64) {
		fprintf(stderr, "%s: not ELF64 (smold M1 only handles 64-bit)\n", path);
		munmap(map, (size_t)st.st_size);
		return 1;
	}
	if (base[EI_DATA] != ELFDATA2LSB) {
		fprintf(stderr, "%s: not little-endian\n", path);
		munmap(map, (size_t)st.st_size);
		return 1;
	}

	const Elf64_Ehdr *eh = map;
	if (eh->e_machine != EM_RISCV) {
		fprintf(stderr, "%s: e_machine is %u, not EM_RISCV (%u)\n",
			path, eh->e_machine, EM_RISCV);
		munmap(map, (size_t)st.st_size);
		return 1;
	}
	if (eh->e_phoff == 0 || eh->e_phnum == 0) {
		fprintf(stderr, "%s: no program headers\n", path);
		munmap(map, (size_t)st.st_size);
		return 1;
	}

	const Elf64_Phdr *ph = (const Elf64_Phdr *)(base + eh->e_phoff);
	int rc = 0;
	int found_any = 0;
	char buf[BUF_SIZE];
	struct smold_out out = { buf, sizeof buf, 0, 0 };

	for (unsigned i = 0; i < eh->e_phnum; i++) {
		if (ph[i].p_type != PT_LOAD) continue;
		if (!(ph[i].p_flags & PF_X)) continue;
		if (ph[i].p_filesz == 0) continue;

		uint64_t pc = pc_override ? pc_base_arg : ph[i].p_vaddr;
		const unsigned char *segbase = base + ph[i].p_offset;
		size_t segsize = (size_t)ph[i].p_filesz;
		if (segsize & 1) {
			fprintf(stderr,
				"%s: executable segment %u has odd p_filesz=%zu, truncating by 1\n",
				path, i, segsize);
			segsize--;
		}

		fprintf(stderr,
			"# segment %u: p_vaddr=0x%016" PRIx64
			" p_filesz=%zu  pc_base=0x%016" PRIx64 "\n",
			i, (uint64_t)ph[i].p_vaddr, segsize, pc);

		int r = smold_walk_range(segbase, segsize, pc, &out);
		if (flush_out(&out) < 0) { rc = 1; break; }
		found_any = 1;

		if (r != SMOLD_OK) {
			fprintf(stderr,
				"smold_walk_range: error %d on segment %u (pc=0x%" PRIx64 ")\n",
				r, i, pc);
			rc = 1;
			break;
		}
	}

	if (!found_any && rc == 0) {
		fprintf(stderr, "%s: no executable PT_LOAD segments\n", path);
		rc = 1;
	}

	munmap(map, (size_t)st.st_size);
	return rc;
}

static int do_bytes(const char *path, uint64_t pc_base)
{
	void *data;
	size_t size;
	if (slurp(path, &data, &size) < 0) return 1;

	if (size & 1) {
		fprintf(stderr, "%s: odd byte count %zu, truncating by 1\n", path, size);
		size--;
	}

	char buf[BUF_SIZE];
	struct smold_out out = { buf, sizeof buf, 0, 0 };
	int r = smold_walk_range(data, size, pc_base, &out);
	flush_out(&out);
	free(data);

	if (r != SMOLD_OK) {
		fprintf(stderr, "smold_walk_range: error %d\n", r);
		return 1;
	}
	return 0;
}

int main(int argc, char **argv)
{
	const char *mode = NULL;
	const char *path = NULL;
	uint64_t pc_base = 0;
	int pc_override = 0;

	for (int i = 1; i < argc; i++) {
		const char *a = argv[i];
		if (strcmp(a, "-h") == 0 || strcmp(a, "--help") == 0) {
			usage(stdout); return 0;
		}
		if (strcmp(a, "--bytes") == 0 || strcmp(a, "--elf") == 0) {
			if (i + 1 >= argc) { usage(stderr); return 2; }
			mode = a;
			path = argv[++i];
			continue;
		}
		if (strcmp(a, "--pc") == 0) {
			if (i + 1 >= argc) { usage(stderr); return 2; }
			char *end;
			pc_base = strtoull(argv[++i], &end, 0);
			if (*end != '\0') {
				fprintf(stderr, "bad --pc value: %s\n", argv[i]);
				return 2;
			}
			pc_override = 1;
			continue;
		}
		fprintf(stderr, "unknown argument: %s\n", a);
		usage(stderr);
		return 2;
	}

	if (!mode) { usage(stderr); return 2; }

	if (strcmp(mode, "--bytes") == 0)
		return do_bytes(path, pc_base);
	else
		return do_elf(path, pc_override, pc_base);
}
