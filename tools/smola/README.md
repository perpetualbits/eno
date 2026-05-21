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

**v0.3.** Hard cut from v0.2: not source-compatible. See spec §10
for the migration table.

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
| `int`, `ptr`, `flt`, `vec` | Variable declarations                |
| `int.s`, `int.a`, `flt.s`, `flt.a`, `vec.a` | Storage variants  |
| `f32`, `f64`      | Float variable with precision marker          |
| `zap`             | Release a binding                             |
| `load_field`, `store_field`, `addr_field` | Struct field access   |
| `raw`             | Escape hatch — emit the tail verbatim         |

## Variable declarations

```asm
int counter         # caller-saved integer, no init
int counter 10      # init to 10 via `li`
int.s persistent    # callee-saved integer (prologue handles save/restore)
int.a x             # next free argument register (a0..a7)
int.a y = a3        # pin to specific argument register
flt gain 0.75       # caller-saved float, init via fmv.w.x (f32 default)
f64 precise 0.5     # caller-saved double, init via literal pool
vec data            # caller-saved vector (v1; v0 is reserved for masks)
```

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
tests/                  # 89 unit tests + pytest-free runner
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

v0.3 implemented:

- mnemonic table covers RVA23-mandatory extensions
- all syntax constructs from the spec
- comment transfer from source to .s
- auto-generated bindings table per function
- 89 unit tests passing on host

Not yet:

- assembly verification with the cross toolchain (next milestone)
- anonymous temporaries (syntax reserved; semantics for v0.4)
- curated `_v.*` RVV vocabulary (planned v0.4)
- soft-float ABI
- `vec` struct fields
- `include` of other `.smola` files
