# tools/smold

**S**mall **MO**nolithic **L**inux **D**isassembler (RISC-V).

A small, atom-composed RISC-V disassembler with two personalities:

1. **Development tool.** Inspect SMOLR-generated executables, report
   instruction coverage, find unsupported instructions before they ship.
2. **Embedded effect.** Link only the atoms needed by a specific demo into
   the demo binary itself, so the demo can disassemble its own code at
   runtime — e.g. as visual material for a cave-carvings effect.

See `docs/design.pdf` for the full design.

## Status

**M1: fallback walker.** The smallest useful first step: walk a memory
range, detect 16-bit vs 32-bit instructions, emit `.2byte 0xhhhh` /
`.4byte 0xwwwwwwww` lines. No mnemonics yet, but this proves the
infrastructure works and is already useful as a "show me the bytes" tool.

Future milestones (M2 RV64I decode, M3 RVC decode, M4 coverage reporter,
M5 SMOLR integration, M6 cave-wall integration, M7 extension growth)
build on this foundation.

## Architecture

- **`src/core.S`** — hand-written RV64 assembly, the smold-core static library.
  Section-per-function discipline (`FUNC`/`ENDFUNC` macros in `asm-macros.h`)
  so `--gc-sections` can drop unused atoms.
- **`cli/smold-cli.c`** — thin C CLI linking the asm core. Three modes:
  `--bytes <file>`, `--bytes -` (stdin), `--elf <file>` (auto-find executable
  `PT_LOAD`).
- **`include/smold.h`** — public C contract used by the CLI and by any future
  embedded caller.

The asm core builds for RV64 only. On an x86 development laptop the
Makefile cross-compiles by default (`riscv64-linux-gnu-` prefix) and runs
tests under `qemu-riscv64`. On a RISC-V board it builds natively.

## Target ISA

`-march=rv64gc_zba_zbb_zbs -mabi=lp64d`.

This matches the Jupiter/Mars (SpacemiT K1/M1) baseline and works on every
RVA22-or-later board. It does **not** run on the Duo S (T-Head C906) which
lacks scalar bitmanip. Future milestones may add Duo S compatibility if
useful.

## Build

```sh
make            # builds core lib, CLI, and tests
make test       # builds and runs tests (under qemu-user on x86 host)
make clean
```

For the cross-build to work on an x86 host you need:

```sh
sudo apt install gcc-riscv64-linux-gnu binutils-riscv64-linux-gnu \
                 qemu-user qemu-user-binfmt
```

## CLI usage

```sh
# Disassemble raw bytes from a file
./build/smold --bytes hello.bin > hello.txt

# From stdin
cat hello.bin | ./build/smold --bytes -

# From an ELF: finds the first executable PT_LOAD and walks it
./build/smold --elf hello.elf

# Override the PC base label
./build/smold --bytes hello.bin --pc 0x10000
```

Output format (one line per instruction):

```
0000000000001000  .2byte 0x1141
0000000000001002  .4byte 0x00000517
0000000000001006  .2byte 0xe406
```

## Public API

See `include/smold.h`. Key entry points:

```c
int smold_walk_range(const void *bytes, size_t nbytes,
                     uint64_t pc_base,
                     struct smold_out *out);

int smold_insn_length(uint32_t h);
int smold_emit_dot_halfword(uint16_t h, struct smold_out *out);
int smold_emit_dot_word(uint32_t w, struct smold_out *out);
int smold_emit_pc_label(uint64_t pc, struct smold_out *out);
```

`struct smold_out` is a (buf, cap, len, needed) tuple. Passing `cap == 0`
with `buf == NULL` is legal: the walker counts bytes into `needed` without
storing anything, so callers can size buffers in a first pass.

## Testing

`tests/test_layout.c` — compile-time `static_assert`s that the C struct
layout matches the offset constants the assembly relies on.

`tests/test_core.c` — runtime unit tests covering instruction length
detection, hex emitters, the walker on empty/single/mixed inputs, overflow
handling, count-only mode, bad arguments, and the truncated- and
unsupported-length error paths.

On a cross host the tests run under `qemu-riscv64`. Same source, same
binaries run on the Jupiter natively — that's the whole point of the
shape.

## License

To be decided alongside the rest of ENO.
