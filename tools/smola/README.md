# SMOLA

A Python preprocessor for RISC-V GAS assembly.

SMOLA is a clean dialect of RISC-V assembly with:

- typed variable declarations that name physical registers
- struct field access with computed offsets and correct load/store
  mnemonics
- scope-based register lifetime management with auto-free
- function-frame planning (prologue/epilogue emitted from
  callee-saved usage)
- strict typo detection — unknown mnemonics are errors
- comment transfer to the generated `.s`

Output is plain `.s` that standard `riscv64-linux-gnu-as` consumes.
Companion to SMOLR and smold.

## Version

**v0.3.1.** Adds string data keywords (`str`, `cstr`, `txt`), stubs
`f16`/`bf16`, and reserves the sub-byte/exotic-FP family. See spec
§2.13 for details. Not source-incompatible with v0.3.

## At a glance

```asm
# Point.translate
# Moves a Point by (dx, dy) in place.

struct Point {
    x: i64,
    y: i64,
}

func Point.translate
    int.a dx
    int.a dy
    scope
        int cx
        int cy
        load_field cx, self, Point.x
        load_field cy, self, Point.y
        add cx, cx, dx
        add cy, cy, dy
        store_field cx, self, Point.x
        store_field cy, self, Point.y
    endscope
end
```

The generated `.s` includes the source comments, an auto-generated
bindings table at the top of the function, and per-instruction
provenance comments showing what each line came from.

## Discriminator: content classification

A line is classified by what its first token is:

- `#` or `//` → comment (transferred to `.s`)
- `<ident>:` or `.L<id>:` → label (passthrough)
- starts with `.` (not a label) → GAS directive (passthrough)
- known SMOLA keyword → SMOLA construct
- known RISC-V mnemonic → instruction (with name substitution)
- anything else → error: unknown mnemonic

No prefix character is required. Typos become errors at preprocess
time, with clear diagnostics.

## Keywords

Closed vocabulary. Adding to it requires a spec amendment.

| Keyword family    | Purpose                                       |
|-------------------|-----------------------------------------------|
| `func`, `end`     | Function boundaries                           |
| `scope`, `endscope` | Nested register-lifetime scope              |
| `struct`          | Struct layout declaration                     |
| `stack <N>`       | Request raw stack spill space                 |
| `int`, `ptr`, `vec` | Default variable declarations               |
| `f32`, `f64`      | Float variable declarations (precision explicit) |
| `i8`, `u8`, `i16`, `u16`, `i32`, `u32`, `i64`, `u64` | Width-typed integer declarations (documentation) |
| `*.s`, `*.a`      | Storage variants (callee-saved, argument)     |
| `str "…"`         | Bare byte string in a data section            |
| `cstr "…"`        | NUL-terminated string in a data section       |
| `txt` … `eot`     | Multi-line heredoc text block in a data section |
| `f16`, `bf16`     | Half-precision float (stub — not yet implemented) |
| `fp8`, `fp4`, `i4`/`u4`, `i2`/`u2`, `i1`/`u1`, `b1p58`, `packed` | Sub-byte / exotic FP (reserved) |
| `zap`             | Release a binding                             |
| `load_field`, `store_field`, `addr_field` | Struct field access   |
| `raw`             | Escape hatch — emit the tail verbatim         |

## Variable declarations

```asm
int counter         # caller-saved integer, no init
int counter 10      # init to 10 via `li`
u8 byte_counter     # width-typed (documentation only)
u32 phase 0x80000000  # width-typed with init
int.s persistent    # callee-saved integer (prologue handles save/restore)
int.a x             # next free argument register (a0..a7)
int.a y = a3        # pin to specific argument register
f32 gain 0.75       # caller-saved float, init via fmv.w.x
f64 precise 0.5     # caller-saved double, init via literal pool
vec data            # caller-saved vector (v1; v0 is reserved for masks)
```

The width-typed integer keywords (`i8`/`u8`/.../`u64`) all allocate
from the integer register file — the register is 64-bit physically
on RV64. The declared width appears in the bindings table at the
function head as documentation:

```
# smola: bindings —
#   byte_counter: t0 (u8, t)
#   phase: t1 (u32, t)
#   counter: t2 (int, t)
```

## Data sections

In a data section (`.data`, `.rodata`, `.bss`), the type keywords
introduce labeled data blocks with automatic alignment:

```asm
.section .rodata

coefs:
    f32  0.5  0.75  1.0
         0.25  0.125

deltas:
    i16  -3  1  2  -1  0  1

dispatch_table:
    ptr  handler_a  handler_b  handler_c
    ptr  handler_d  handler_e  handler_f
```

SMOLA emits `.balign`, the right storage directive per value
(`.byte`/`.hword`/`.word`/`.dword`/`.float`/`.double`), and `.size`
after each labeled block. Numeric continuation lines are
auto-detected; symbolic references require the type keyword on
each line.

`int` and `vec` are forbidden in data sections — must commit to
a width. `i8` through `u64`, `f32`, `f64`, and `ptr` are allowed.

### String data

```asm
.section .rodata

greeting:
    str "Hello, world!"       # 13 bytes; no NUL

prompt:
    cstr "Enter name: "       # 13 bytes + NUL = 14

banner:
    txt
line one of the banner
line two of the banner
eot
```

`str` emits `.ascii` with a `.size` sized to the UTF-8 byte count.
`cstr` appends a `.byte 0` and counts +1. `txt` is a heredoc: every
line until the `eot` terminator is emitted as `.ascii "…\n"`. Content
inside `txt` is raw text — `\` and `"` are escaped for GAS
automatically; no SMOLA escape sequences are processed.

## Collision detection

Once SMOLA binds a name to a register, raw references to that
register are errors:

```asm
int counter
addi counter, counter, 1   # ok
addi t0, t0, 1             # ERROR: t0 is bound to counter
zap counter
addi t0, t0, 1             # ok now
```

## Layout

```
spec/Smola_Spec.md      # the design document
src/smola/              # the Python package
    __init__.py
    mnemonics.py        # RV mnemonic table (strict typo detection)
    lexer.py            # content-based line classification
    regalloc.py         # multi-pool allocator with scope stack
    symbols.py          # struct table
    frame.py            # prologue / epilogue planner
    translator.py       # orchestrator
    cli.py
    errors.py
src/bin/smola           # executable entry point
tests/                  # 173 unit tests + pytest-free runner
examples/               # ported v0.3 examples
Makefile
README.md
```

## Quick start

```sh
make test                  # run unit tests
make examples              # translate examples to .s
make check-assembles       # requires riscv64-linux-gnu-as
```

## Status

v0.3.1 implemented:

- mnemonic table covers RVA23-mandatory extensions
- all syntax constructs from the spec
- comment transfer from source to .s
- auto-generated bindings table per function
- string data: `str`, `cstr`, `txt`/`eot`
- f16/bf16 stubs (keyword accepted, "not yet implemented" error)
- sub-byte/exotic FP reserved keywords (keyword accepted, reserved error)
- 173 unit tests passing on host

Not yet:

- assembly verification with the cross toolchain (next milestone)
- f16/bf16 implementation
- anonymous temporaries (syntax reserved; semantics for v0.4)
- curated `_v.*` RVV vocabulary (planned v0.4)
- soft-float ABI
- `vec` struct fields
- `include` of other `.smola` files
