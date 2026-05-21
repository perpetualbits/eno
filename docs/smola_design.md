# SMOLA: A Python-Preprocessed Macro Language for RISC-V Assembly

## Status

Design document v0.3.1. Implementation at `tools/smola/` in the ENO
monorepo. v0.3.1 adds string data keywords; not source-incompatible
with v0.3. Hard cut from v0.2 (no source compatibility). Companion
to SMOLR and smold; see `Smolr_Design_And_Plan.md` and
`Smolr_Embedded_Disassembler_Design.md` for the linker and disassembler
this lives alongside.

## What changed from v0.2

The v0.2 syntax was syntactically distinctive — every SMOLA construct
started with `_`. That made the parser easy but the source ugly. v0.3
drops the prefix and the all-uppercase fallback. Instead, SMOLA
recognizes lines by what they are:

- a known RVA23 / RISC-V instruction
- a known GAS directive (starts with `.`)
- a SMOLA keyword (small closed list: `func`, `end`, `scope`, `endscope`,
  `struct`, `stack`, `int`, `ptr`, `vec`, `zap`, `str`, `cstr`, `txt`,
  and the full width/float/reserved family — see §2.3)
- a label (`<ident>:` or `.L<name>:`)
- a comment (`#` or `//`)
- a blank line

Anything else is an error. A typo in an instruction name no longer
silently passes through to GAS — SMOLA catches it.

End-user code now looks like plain assembly with a few extra keywords:

```asm
# render_square: writes a solid color rectangle into the framebuffer.
# Variable map: src -> framebuffer base, dst -> output pixel cursor,
#               counter -> remaining pixel count, gain -> blend factor.
func render_square
    ptr src
    ptr dst
    u32 counter 4096
    f32 gain 0.75

loop:
    lw t0, 0(src)               # load source pixel
    sw t0, 0(dst)               # store to dest
    addi src, src, 4
    addi dst, dst, 4
    addi counter, counter, -1
    bnez counter, loop

    zap counter
end
```

Data sections work the same way — typed declarations introduce
labeled blocks with automatic alignment:

```asm
.section .rodata

# Delta-coded i16 wavelet coefficients for one sub-band.
band_coefs:
    i16  -3   1   2  -1   0   1
          0  -1   2   1  -3   2

# CDF 5/3 reconstruction taps.
cdf53_taps:
    f32  -0.0625  0.5625  0.5625  -0.0625
```

SMOLA emits the right `.balign` and `.size` directives. Forgetting
alignment in data sections is one of the most error-prone parts of
hand-written RISC-V assembly; SMOLA handles it automatically.

Everything else from v0.2 (typed variable pools, struct fields,
scope-based register lifetimes, collision detection, frame planning)
is preserved with cleaner naming.

## 1. Design principles

### 1.1 Zero runtime cost

Every SMOLA construct expands to instructions a careful assembly
author would have written by hand. SMOLA decides *which physical
register a name binds to* and *what offset a field lives at*, but the
emitted instructions are exactly what the user would have typed.

### 1.2 Provenance is preserved

The generated `.s` is meant to be readable when something goes wrong.
Comments from the source are transferred. SMOLA also emits its own
documentation: a bindings table at the top of each function listing
which physical register each named variable lives in. Reading the
generated `.s` must remain the natural debugging path.

### 1.3 Strict on typos

A line that is none of `{known instruction, known directive, SMOLA
keyword, label, comment, blank}` is an error. This is a strong
commitment: it means SMOLA needs a mnemonic table, and it means SMOLA
must be updated as new RISC-V extensions become standard. The benefit
is that user typos surface immediately with a clear "unknown mnemonic"
error, instead of being passed to GAS and producing a less actionable
error there.

### 1.4 Close to assembly

The user is writing assembly. SMOLA spells fewer letters but does not
introduce its own programming model. There are no closures, no
inheritance, no virtual dispatch, no implicit allocations, no expression
evaluation, no operator overloading. A line that looks like an
instruction is an instruction; a line that looks like a declaration is
a declaration.

### 1.5 Hostile to feature creep

Every proposed addition must point at concrete source it would
shorten in real ENO/SMOLR/smold code, not hypothetical code. The §2.8
non-goals list is binding: features there require a spec amendment to
add.

## 2. The language

### 2.1 Lexical structure

A SMOLA source file is a sequence of UTF-8 lines. The lexer classifies
each line based on its content:

| Pattern                                  | Classification                |
|------------------------------------------|-------------------------------|
| empty / whitespace only                  | blank                         |
| starts with `#` or `//`                  | comment                       |
| matches `<ident>:` or `.L<name>:`        | label                         |
| starts with `.` (and isn't a label)      | GAS directive (passthrough)   |
| first token is a SMOLA keyword (§2.3)    | SMOLA construct               |
| first token is a known RISC-V mnemonic   | instruction (passthrough)     |
| anything else                            | error: unknown mnemonic       |

The "known RISC-V mnemonic" check uses the table in
`tools/smola/src/smola/mnemonics.py`. The table covers RV32I, RV64I,
M, A, F, D, C, Zba, Zbb, Zbc, Zbs, Zicsr, Zicntr, Zifencei, V (RVV
1.0), and standard pseudo-instructions. RVA23-mandatory extensions
are covered. Adding a new extension means editing one Python file.

Identifiers follow C rules: `[A-Za-z_][A-Za-z0-9_]*`.

### 2.2 Comments and prose

Comments serve two purposes:

1. **Source documentation.** Block comments (multiple consecutive `#`
   or `//` lines) and end-of-line comments describe what the code
   does. These transfer to the generated `.s`.

2. **Outline prose.** Outside any `func` block, comments can be longer
   prose describing module structure, design intent, file headers.
   These also transfer.

Comment transfer rules:

- **Block comments before a `func`**: emitted immediately before the
  function's section header in the `.s`.
- **End-of-line comments after instructions**: transferred to the
  corresponding emitted instruction, after register substitution.
- **Block comments inside a function**: emitted at the position they
  appear in source.
- **Comments outside any function**: emitted in order.

Auto-generated bindings table: immediately after each function's
prologue (or after the label, for leaf functions), SMOLA emits a
block comment listing every named variable in the function and its
physical register. This is part of the provenance machinery and is
suppressed by `--no-provenance`.

### 2.3 SMOLA keywords

The closed vocabulary. Editing this list requires a spec amendment.

#### Block-shaping

- `func <name> [static]` — open a function definition.
- `end` — close the current `func` block. Replaces v0.2's `endfunc` /
  `endmethod` (the `method` distinction is gone; methods are just
  functions whose name encodes the struct, written as `func
  Point.translate`).
- `scope` — open a nested scope for register lifetime.
- `endscope` — close the innermost scope.

#### Struct declarations

- `struct <Name> { <fields> }` — declare a struct layout. Natural
  alignment, primitive field types
  (`i8`/`u8`/`i16`/`u16`/`i32`/`u32`/`i64`/`u64`/`f32`/`f64`/`ptr`).

#### Variable declarations

Form: `<type> <name> [<initializer>]` for code-section variables,
where `<type>` is one of:

| Keyword                                     | Meaning                          |
|---------------------------------------------|----------------------------------|
| `int`                                       | integer register, default        |
| `i8`/`u8`/`i16`/`u16`/`i32`/`u32`/`i64`/`u64` | integer register, declared width |
| `ptr`                                       | integer register, pointer-typed  |
| `f32`                                       | FP register, single precision    |
| `f64`                                       | FP register, double precision    |
| `vec`                                       | vector register                  |

The width-typed integer variants (`i8`/`u8`/.../`u64`) allocate from
the same pool as `int` — the integer register file on RV64 is 64-bit
physically. The declared width is **documentation only**: it appears
in the auto-generated bindings table at the function head and serves
to communicate intent to readers, but it does not affect register
allocation or instruction emission and is not enforced when the user
writes width-mixed instructions.

A future v0.4 may use the declared width to drive default load/store
mnemonic inference (`load counter, 0(src)` picking `lbu` because
`counter` is declared `u8`); v0.3 reserves the documentation hook
but does not yet implement that feature.

`flt` was a v0.2/early-v0.3 keyword that has been **removed**.
Always write `f32` or `f64` to declare a float variable. The lexer
catches `flt` with a migration hint.

Examples:

```asm
int counter         # default integer
u8 byte_counter     # width-typed (8-bit, documentation)
u16 phase_index     # width-typed (16-bit)
i32 signed_count    # width-typed (signed 32-bit)
ptr base            # pointer
f32 gain 0.75       # f32 with initialization
f64 precise 0.5     # f64 with initialization
int counter 10      # default integer with initialization
```

By default, declarations claim **caller-saved (temporary)** storage.
To claim callee-saved or argument storage, append `.s` or `.a`:

- `int.s persistent` — callee-saved integer (`s0`..`s11`).
- `u8.a byte_arg` — argument register, width-typed.
- `int.a x = a3` — pin to a specific argument register.
- `f32.s saved_gain` — callee-saved float.

All width keywords accept both suffixes. `vec.s` is forbidden (no
callee-saved vector registers in the RVV ABI).

#### `zap <name>[, <name>...]`

Release one or more named bindings.

Behavior:
- removes the symbolic binding
- for temporaries: returns the register to its pool
- for callee-saved: removes the name but leaves the prologue's
  save/restore in place (we already committed to saving it)
- for arguments: removes the name; the register's ABI position is
  unchanged

#### `stack <N>`

Inside a function, request `N` extra bytes of user-controlled stack
space.

### 2.4 Variable initialization

Typed declarations can include an initializer that emits one or two
instructions at declaration time.

| Declaration                     | Emitted                                   |
|---------------------------------|-------------------------------------------|
| `int counter`                   | (nothing — declaration only)              |
| `int counter 10`                | `li counter, 10`                          |
| `u32 phase 0xDEADBEEF`          | `li phase, 0xDEADBEEF`                    |
| `i64 total 0`                   | `li total, 0`                             |
| `ptr base`                      | (nothing — declaration only)              |
| `f32 gain 0.75`                 | bit-pattern + `fmv.w.x`; see below        |
| `f64 precise 0.5`               | literal-pool + `la`+`fld`; see below      |
| `vec data`                      | (nothing — declaration only)              |

For integer initialization, GAS's `li` pseudo-instruction handles
arbitrary-width constants via the right sequence (`lui`+`addi` or
`addi`+`slli`+`addi` for wider values). The width-typed variants
(`u8`, `i32`, etc.) emit the same `li` — the declared width is
documentation; SMOLA does not mask or truncate the literal to the
declared width.

For floating-point initialization, RISC-V has no "load immediate"
equivalent to `li`. Two idioms:

- **Bit pattern + integer move** (used for `f32`): SMOLA computes
  the IEEE 754 single-precision bit pattern of the literal, emits
  `li tN, 0xBITPATTERN` (using a transient integer temporary), then
  `fmv.w.x reg, tN`. Fully inline.
- **Literal pool** (used for `f64`): SMOLA emits an entry at the
  end of the function's `.text.<func>` section and loads via
  `la tN, .Lflt_N; fld reg, 0(tN)`. The pool entry is invisible
  unless you read the generated `.s`.

Both happen at preprocess time. The user just writes `f32 gain 0.75`
or `f64 precise 0.5` and SMOLA emits the right sequence.

This is the SMOLA construct that *emits an instruction at
declaration*. v0.2's `_var.t` was pure bookkeeping. The new behavior
is documented explicitly: declarations are still *deterministic*
and *zero-cost-beyond-what-you-would-have-written-by-hand*, but
they can now have side effects.

### 2.5 Anonymous declarations (reserved syntax)

The form `int 10` (a type and an initializer with no name) is
**reserved**. v0.3 errors on this syntax with a hint:

```
foo.smola:42: error: anonymous declarations reserved for v0.4
        int 10
hint: name the binding explicitly (e.g. 'int tmp 10'); in data
sections, a label is required
```

Reserved in two contexts:

- **In a code section**, this would be an anonymous temporary
  binding. Reserved because the right semantics (single-use? scoped
  to next mnemonic? expression-like?) needs concrete use cases to
  resolve, and we haven't seen any yet in real ENO code.

- **In a data section**, this would be an anonymous data block
  (data without a preceding label). Reserved because anonymous data
  blocks are hard to reference (no symbol to load) and a label
  always costs nothing. We may add anonymous data later for reset
  vectors or section-prefix data layouts; we wait for the concrete
  use case.

Both reservations hold the namespace without committing to
semantics.

### 2.6 Methods are just functions

v0.2 had `_method Struct.name` as sugar for `_func Struct_name` with
an implicit `self -> a0` binding. v0.3 unifies this: write
`func Point.translate`, and SMOLA:

- emits the symbol as `Point_translate` (the dot is mangled to
  underscore in the symbol name).
- implicitly binds `self` to `a0` if and only if a struct named
  `Point` was previously declared.

If no matching struct exists, the dot stays as a struct-method-style
name mangling but no `self` binding occurs. This means `func
foo.helper` works even for non-method namespacing.

### 2.7 Field access

Same as v0.2 but without the `_` prefix:

- `load_field dst, base, Point.x` — emits the right `l*` instruction
  with computed offset.
- `store_field src, base, Point.x` — emits the right `s*` instruction.
- `addr_field dst, base, Point.x` — computes the field address
  (renamed from `la_field` for slight clarity).

These are SMOLA keywords, not RISC-V mnemonics. They are in the
SMOLA keyword set (§2.3) and parse accordingly.

### 2.8 Calls

Two forms:

- Raw RISC-V `call` mnemonic: standard, no argument shuffling. The
  user is responsible for getting arguments into the right registers.
- `call <target>, <arg1>, ...` — SMOLA pseudo: shuffles arguments
  into `a0..a7` and `fa0..fa7` according to type, then emits `call
  target`. Detects shuffle cycles.

The two coexist because the raw `call` is sometimes all you want,
and the SMOLA pseudo is sometimes all you want. The lexer
distinguishes by argument count: bare `call target` is raw; `call
target, arg1, ...` is the pseudo. (A bare RISC-V `call target` has
no comma-separated trailing operands; SMOLA's pseudo *requires* the
comma.)

### 2.9 Register collision rule (unchanged from v0.2)

Once SMOLA binds a name to a register, raw references to that
register are errors:

```asm
int counter
addi counter, counter, 1   # good
addi t0, t0, 1             # error: t0 bound to counter
zap counter
addi t0, t0, 1             # ok now
```

The rule applies to both SMOLA keywords and raw assembly lines. The
diagnostic names both the register and the variable holding it.

### 2.10 Raw assembly escape hatch

v0.2 had a `!` prefix for raw passthrough. v0.3 doesn't need it:
unrecognized lines are errors, recognized RISC-V instructions are
already passthrough.

However, for the rare case where the user wants to emit something
SMOLA's mnemonic table doesn't know about (e.g. a brand-new extension
SMOLA hasn't been updated for yet), a `raw` directive is available:

```asm
raw mynewexotic.op a0, t0, t1
```

Anything on a `raw` line passes through verbatim with no checks (not
even collision detection — `raw` is a deliberate hatch). Provenance
comment notes the rawness.

### 2.11 What v0.3 / v0.3.1 does NOT have

- Inheritance, generics, virtual dispatch.
- Anonymous declarations in code or data (§2.5 reserved syntax).
- `vec` struct fields (use raw RVV instructions for vector load/store).
- Struct-typed data declarations (you cannot write "a `Point` in
  `.rodata`" with a struct keyword; lay out the fields manually using
  the primitive widths).
- `include` of other `.smola` files.
- Conditional assembly via SMOLA (use GAS `.if`/`.endif`).
- Soft-float ABI.
- The curated `_v.*` RVV vocabulary mentioned in v0.2's milestone list.
  Raw RVV instructions pass through cleanly; the vocabulary lands when
  a concrete wavelet kernel needs it.
- `f16` / `bf16` implementation (keywords reserved; translator raises
  "not yet implemented" — see §2.13).
- Sub-byte / exotic FP types (`fp8`, `fp4`, `i4`/`u4`, `i2`/`u2`,
  `i1`/`u1`, `b1p58`, `packed`): reserved keywords, see §2.13.

### 2.12 Data-section declarations

When the current section is a data section, type keywords gain a
second meaning: they introduce **labeled data blocks**. SMOLA emits
correct alignment, the right GAS storage directive per value, and
a `.size` directive after each block.

A section is a "data section" if its name starts with any of
`.data`, `.rodata`, `.bss`, `.tdata`, `.tbss` (matching both the
section itself and any sub-section like `.rodata.cst8`). The default
section at file start is `.text` (code).

#### Syntax

```
<label>:
    <type>  <value> [<value> ...]
            [<value> <value> ...]    ; continuation lines (numeric only)
```

#### Type keywords allowed in data

| Keyword          | GAS directive | Size | Alignment |
|------------------|---------------|------|-----------|
| `i8` / `u8`      | `.byte`       | 1    | 1         |
| `i16` / `u16`    | `.hword`      | 2    | 2         |
| `i32` / `u32`    | `.word`       | 4    | 4         |
| `i64` / `u64`    | `.dword`      | 8    | 8         |
| `f32`            | `.float`      | 4    | 4         |
| `f64`            | `.double`     | 8    | 8         |
| `ptr`            | `.dword`      | 8    | 8         |

#### Type keywords NOT allowed in data

- `int` — must commit to a width. Use `i64` or `u64` for 8-byte
  integers, `i32`/`u32` for 4-byte, etc.
- `vec` — vector data has no fixed width independent of its
  elements. Use the underlying scalar type; vector loads
  (`vle32.v` etc.) want element-aligned data, which `f32`/`u16`/etc.
  provides.
- Storage-suffixed forms (`i8.s`, `f32.a`, ...) — storage classes
  describe register lifetimes; they're meaningless in data.

#### Emitted output

Source:
```asm
.section .rodata

coefs:
    f32  0.5  0.75  1.0
         0.25  0.125
```

Output:
```asm
    .section .rodata
coefs:
    .balign 4
    .float 0.5
    .float 0.75
    .float 1.0
    .float 0.25
    .float 0.125
    .size coefs, 20
```

The `.balign` directive uses the type's natural alignment. The
`.size` directive reflects the total bytes written under the label
(elements × size). Multiple type-changes under one label accumulate
into the size:

```asm
mixed_block:
    i16  -3  1  2     ; 6 bytes
    f32  0.5  0.75    ; 8 bytes
```

emits `.size mixed_block, 14`. (Note: SMOLA does not account for
GAS-inserted alignment padding between the `i16` block and the `f32`
block. If you care about exact byte sizes across width transitions,
arrange your block so naturally-larger alignments come first.)

#### Continuation lines

A line whose first token is a numeric literal (decimal, hex, signed,
or floating-point) is treated as a **continuation** of the preceding
data directive. The values are emitted with the same GAS directive
as the original line.

Continuation works for numeric values:

```asm
deltas:
    i16  -3  1  2  -1
         0  1  -2  3      ; continues i16
```

Continuation does **not** work for symbol references. For symbolic
data (e.g. jump tables), repeat the type keyword on each line:

```asm
dispatch_table:
    ptr  handler_a  handler_b  handler_c
    ptr  handler_d  handler_e  handler_f
```

This is a deliberate limitation: SMOLA distinguishes numeric
continuations from "unknown mnemonic" typos purely by syntactic
shape, and an identifier like `handler_a` is shape-indistinguishable
from a typo. Requiring the type keyword on symbol-reference lines
keeps the typo detection strict.

A new label terminates any pending continuation context: values
under the new label require a fresh type keyword.

#### Comments in data sections

Block comments and end-of-line comments work the same as in code
sections: they transfer to the generated `.s`. A block comment
between two labeled data blocks attaches to the *following* label
in source order:

```asm
.section .rodata

band_coefs:
    i16  -3  1  2

# CDF 5/3 reconstruction taps. f32 because the kernel uses single
# precision throughout.
cdf53_taps:
    f32  -0.0625  0.5625  0.5625  -0.0625
```

The `.size band_coefs, ...` directive is emitted *before* the
comment for `cdf53_taps`, keeping the documentation associated with
the correct block.

#### Labels are mandatory

A data declaration must be preceded by a label. Anonymous data is
reserved (§2.5).

#### Section transitions

When `.section` switches to a new section, any open data block has
its `.size` directive flushed before the new section begins. So a
sequence like:

```asm
.section .rodata
data:
    i32 42
.section .text
func use_it
    ...
```

emits `.size data, 4` *before* the `.section .text` directive.

### 2.13 String data (v0.3.1)

Three new keywords declare string content directly in a data section.
They require a preceding label (anonymous strings are reserved).
All three emit `.balign 1` because byte strings need no alignment
beyond byte granularity.

#### `str "…"` — bare byte string

```asm
greeting:
    str "Hello, world!"
```

Emits:
```
greeting:
    .balign 1
    .ascii "Hello, world!"
    .size greeting, 13
```

`.size` equals the UTF-8 byte count. No NUL terminator is appended.
Use when the caller knows the length from context (e.g. via a
companion `.word` length field, or a fixed-size protocol).

#### `cstr "…"` — NUL-terminated string

```asm
prompt:
    cstr "Enter name: "
```

Emits `.ascii` followed by `.byte 0`. `.size` counts the NUL byte:
`prompt` is 13 bytes (12 chars + NUL).

#### `txt` … `eot` — multi-line heredoc

```asm
banner:
    txt
line one
line two
eot
```

Emits one `.ascii "…\n"` per content line. `eot` must appear on its
own line. Content is raw: `\` and `"` characters are automatically
escaped for GAS; SMOLA escape sequences (like `\n`) are **not**
processed inside the block. Total size equals Σ(UTF-8 bytes per
line + 1 for the newline).

#### Supported escape sequences (str and cstr only)

| Sequence | Meaning        |
|----------|----------------|
| `\"`     | double-quote   |
| `\\`     | backslash      |
| `\n`     | newline (0x0A) |
| `\t`     | tab (0x09)     |
| `\0`     | NUL (0x00)     |
| `\xHH`   | hex byte       |

Unknown escapes are an error.

#### Context requirement

`str`, `cstr`, and `txt` are only valid in a data section. Using
them in `.text` (or before any `.section`) is an error.

#### f16 / bf16 (stub)

`f16`, `bf16`, and their `.s`/`.a` storage variants are in the
keyword set so the lexer does not reject them as unknown mnemonics.
The translator raises a "not yet implemented" error if they appear.
They will be implemented in a future release.

#### Sub-byte and exotic FP (reserved)

`fp8`, `fp4`, `i4`, `u4`, `i2`, `u2`, `i1`, `u1`, `b1p58` (each
with `.s`/`.a`), and `packed` are reserved keywords. They are in the
keyword set and produce a "reserved — not yet implemented" error.

## 3. Worked example

Source:

```asm
# Point.translate
# Moves a Point by (dx, dy) in place.
# Variable map: dx -> a1, dy -> a2, cx -> t0, cy -> t1, self -> a0.

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

Output (key fragment):

```
# Point.translate
# Moves a Point by (dx, dy) in place.
# Variable map: dx -> a1, dy -> a2, cx -> t0, cy -> t1, self -> a0.

    .set Point_x_offset, 0
    .set Point_y_offset, 8
    .set Point_size, 16

    .section .text.Point_translate, "ax", @progbits
    .globl  Point_translate
    .type   Point_translate, @function
    .balign 2
Point_translate:
    # smola: bindings — self: a0 (ptr, arg implicit), dx: a1 (int, arg),
    #                   dy: a2 (int, arg), cx: t0 (int, temp),
    #                   cy: t1 (int, temp)
    ld   t0, 0(a0)              # load_field cx, self, Point.x
    ld   t1, 8(a0)              # load_field cy, self, Point.y
    add  t0, t0, a1             # add cx, cx, dx
    add  t1, t1, a2             # add cy, cy, dy
    sd   t0, 0(a0)              # store_field cx, self, Point.x
    sd   t1, 8(a0)              # store_field cy, self, Point.y
    ret                         # smola: leaf epilogue
    .size Point_translate, .-Point_translate
```

The top-of-source block comment transferred to the top of the `.s`.
The auto-generated bindings table appears immediately after the
function label.

## 4. Architecture

### 4.1 Pipeline

Same as v0.2: lex → walk → buffer per-function → emit at `end` time
with prologue/epilogue stitched in.

### 4.2 Modules

```
tools/smola/
    src/
        smola/
            __init__.py
            mnemonics.py         # NEW: closed table of RV mnemonics
            lexer.py             # rewritten for v0.3 classification
            symbols.py           # struct table (mostly unchanged)
            regalloc.py          # multi-pool allocator (mostly unchanged)
            frame.py             # prologue/epilogue planner (unchanged)
            translator.py        # orchestrator (rewritten)
            errors.py            # error types (unchanged)
            cli.py               # (unchanged)
        bin/
            smola
    tests/
        test_lexer.py
        test_regalloc.py
        test_symbols.py
        test_translator.py
        test_mnemonics.py        # NEW: typo-detection tests
        run_tests.py
    examples/
        point.smola
        counter.smola
        render_square.smola
    Makefile
    README.md
```

### 4.3 The mnemonic table

A flat set of known instruction names. Lookup is O(1). The table is
explicit data, not generated — it should be reviewable in a normal
diff.

Coverage required for RVA23 baseline:
- RV32I + RV64I base
- M (mul/div)
- A (atomics)
- F + D (floats)
- C (compressed)
- Zba, Zbb, Zbc, Zbs (bit manipulation)
- Zicsr (CSR access)
- Zicntr, Zihpm (counters)
- Zifencei (instruction fence)
- V (vector 1.0)
- Standard pseudo-instructions (`li`, `mv`, `ret`, `j`, `jr`, `nop`,
  `not`, `neg`, `seqz`, `snez`, `sltz`, `sgtz`, `beqz`, `bnez`,
  `blez`, `bgez`, `bltz`, `bgtz`, `bgt`, `ble`, `bgtu`, `bleu`,
  `call`, `tail`, `fence`, `fmv.s`, `fmv.d`, `fneg.s`, `fneg.d`,
  `fabs.s`, `fabs.d`)

Not in the table: SMOLA's own pseudo-instructions (`load_field`,
`store_field`, `addr_field`). Those are in the SMOLA keyword set,
which the lexer checks before the mnemonic table.

### 4.4 Register pools, scopes, frame planning

Unchanged from v0.2. See `smola_design.md` v0.2 §4.3–4.6, transcribed
into the v0.3 codebase but with no behavioral changes.

### 4.5 Comment transfer

The translator maintains a "pending comment buffer" — block-comment
lines accumulate there until a non-comment line appears. At that point:

- If the non-comment is `func`, the pending block flushes into the
  output *before* the function's section header.
- If the non-comment is anything else, the pending block flushes
  immediately at its source position.

End-of-line comments on instruction lines transfer to the emitted
instruction, after register substitution.

The auto-generated bindings table is emitted once at `end` time,
inserted immediately after the function label (before any prologue
saves). The position is fixed; the table content is computed from
the final binding list.

### 4.6 Determinism

Same as v0.2: same input + same SMOLA version + same mnemonic table
= byte-identical output.

## 5. CLI

```
smola [options] input.smola

  -o, --output <file>     Output .s file.
      --stdout            Emit to stdout.
      --no-provenance     Suppress # smola: ... comments and the auto
                          bindings table.
      --check             Parse only; no output.
  -v, --verbose
```

Exit codes: 0 success, 1 SmolaError, 2 internal.

## 6. Build integration

Unchanged:

```
%.s: %.smola
	$(SMOLA) $< -o $@

%.o: %.s
	$(AS) $(ASFLAGS) $< -o $@
```

## 7. Testing

Four levels as before. New: typo-detection tests in
`test_mnemonics.py` to verify both that the table accepts every
RVA23-mandatory mnemonic and that misspellings are rejected.

## 8. Milestones

- **M0 (done)**: v0.2 design and prototype.
- **M0.5 (this session)**: v0.3 syntax, mnemonic table,
  comment-transfer, anonymous-temp syntax reserved. Three examples
  ported.
- **M1**: assembly verification with `riscv64-linux-gnu-as` on a host.
- **M2**: golden-file regression tests.
- **M3**: behavioral tests via `qemu-riscv64`.
- **M4**: port a smold M1 atom; byte-identical object verification.
- **M5**: anonymous-temporary semantics decided, syntax implemented.
- **M6**: curated `_v.*` RVV vocabulary (if a real wavelet kernel
  asks for it).
- **M7**: first SMOLR runtime-resolver use.

## 9. Risks

- **Mnemonic-table maintenance burden.** Every new RISC-V extension
  requires editing `mnemonics.py`. Mitigation: the table is plain
  Python data, single file, alphabetized; updates are mechanical and
  reviewable. We accept this burden as the cost of strict-typo
  detection.
- **Keyword namespace pollution.** Bare keywords like `int`, `func`,
  `end`, `zap` exist in the global namespace. None collide with
  RISC-V mnemonics or GAS directives in RVA23. Mitigation: the
  mnemonic table is the source of truth; we check it after every
  language change.
- **Comment transfer might align poorly with the generated `.s`.**
  Mitigation: golden-file tests on the three examples lock in
  current behavior; user reports drive fixes.
- **`flt gain 0.75` emits a literal-pool entry for f64**, which means
  the user's function gains a `.rodata`-like section. Mitigation:
  document explicitly in §2.4; provide `--no-flt-init` flag to
  disable initialization sugar if the user wants strict control.

## 10. Migration from v0.2

Hard cut.

| v0.2                          | v0.3                                |
|-------------------------------|-------------------------------------|
| `_func name`                  | `func name`                         |
| `_endfunc` / `_endmethod`     | `end`                               |
| `_method Struct.name`         | `func Struct.name` (auto-detects)   |
| `_struct S { ... }`           | `struct S { ... }`                  |
| `_scope` / `_endscope`        | `scope` / `endscope`                |
| `_stack N`                    | `stack N`                           |
| `_var.t int x`                | `int x`                             |
| `_var.s int x`                | `int.s x`                           |
| `_var.a int x`                | `int.a x`                           |
| `_var.a int x = a3`           | `int.a x = a3`                      |
| `_var.t flt g`                | `f32 g` (or `f64 g`; `flt` removed) |
| `_var.t vec v`                | `vec v`                             |
| (no init form)                | `int x 10`, `f32 g 0.75`            |
| (no width-typed integer form) | `u8 x`, `i32 phase`, etc. (doc only)|
| (no data-section semantics)   | `f32 0.5 0.75 ...` in `.rodata`     |
| `_free name`                  | `zap name`                          |
| `_load_field`                 | `load_field`                        |
| `_store_field`                | `store_field`                       |
| `_la_field`                   | `addr_field` (renamed)              |
| `_call target, args`          | `call target, args`                 |
| `_add a, b, c`                | `add a, b, c` (raw RV mnemonic)     |
| `! raw line`                  | `raw line` (or just the line itself)|
| any unknown SMOLA `_keyword`  | error                               |
| any unknown lowercase mnemonic| was passthrough → now error         |

Two notes on the refinements (added during the second 2026-05-21
session):

- The `flt` keyword was removed. Use `f32` or `f64` explicitly.
  The lexer catches `flt` with a migration hint.
- Width-typed integer keywords (`i8`/`u8`/`i16`/`u16`/`i32`/`u32`/
  `i64`/`u64`) were added to the variable-declaration vocabulary.
  They allocate from the same pool as `int`; the declared width
  appears in the bindings table as documentation. v0.3 does not
  enforce the width on instructions; that's a v0.4 hook.

The v0.2 examples in `examples/` are replaced with v0.3 versions.
The v0.2 sources are not preserved in the project; retrieve from git
if historical comparison is wanted.

## 11. Final note

SMOLA stays:

- source-to-source
- deterministic
- zero-runtime-cost
- close to assembly
- readable in generated `.s`
- strict about typos
- hostile to feature creep

If any feature works against any of these, it doesn't ship.

## 12. Implementation notes

### 12.1 Local labels are section-scoped

GAS local labels (`.L<name>`) are scoped to the section they appear
in. Because `func` opens a new `.text.<name>` section per function,
local labels inside one function cannot be referenced from another.

### 12.2 Comment transfer mechanism

The lexer emits Comment lines verbatim. The translator maintains a
"pending block" buffer; comment lines accumulate there until a
non-comment, non-blank line appears. The flush rules in §4.5 apply.

### 12.3 Auto-bindings table

Computed at `end` time when the full binding history is known.
Emitted immediately after the function's label and prologue. Format:

```
    # smola: bindings — <name>: <reg> (<type>, <storage>),
    #                   <name>: <reg> (<type>, <storage>), ...
```

The table lists bindings in declaration order. Scoped bindings
include their scope depth: `(<type>, <storage>, scope <N>)`.

### 12.4 Float initialization synthesis

For `flt gain 0.75`:
- f32 (default): convert 0.75 to its IEEE 754 bit pattern (0x3f400000),
  emit `li tN, 0x3f400000` + `fmv.w.x gain, tN`. Uses a transient int
  temporary register; if none available, errors.
- f64: emit a `.section .rodata.<func>` block with the bit pattern,
  load via `la` + `fld`.

The choice is governed by struct field type when the variable is
later stored; v0.3 defaults declarations to f32 unless explicitly
written as `f64 gain 0.75` (the type tag can be `flt` for default-
precision or `f32`/`f64` for explicit).

### 12.5 `raw` directive

Accepts any text after the keyword. The text is emitted verbatim
into the `.s` with leading indentation. No name resolution, no
collision check. Use sparingly.

## 13. External tooling integration considerations

SMOLA is designed first for hand-written demo code: a person typing
into a text editor, reading the generated `.s` to learn what
happened, fixing mistakes. That is the primary use case and the
spec exists to serve it.

However, SMOLA's structural properties — strict grammar, typed
declarations, deterministic codegen, propagated provenance — also
make it a plausible stage in automated pipelines: continuous
integration, fuzzing, batch compilation, code-generation toolchains,
and (in particular) machine-learning pipelines that synthesize
candidate assembly and need a structured front end to compile and
score it. This section names the hooks that should remain available
to such pipelines as SMOLA evolves, especially through the future
Rust port.

These are **considerations**, not features. None of them ship in
v0.3. They exist here so that the Rust port does not inadvertently
foreclose them.

### 13.1 Structured diagnostics

Current state: `SmolaError` exits with code 1 and a human-readable
message on stderr. This is fine for a person at a terminal but
fragile for automation.

Future hook: a `--diagnostics-json` mode that emits errors as a
JSON array on stderr (or a separate file) with stable fields:

- error code (stable across versions, documented)
- source file, line, column
- severity (error / warning)
- short message
- optional structured context (e.g. expected mnemonic class,
  conflicting binding name)

The Rust port should make this trivial — `serde` plus typed error
variants get you the JSON shape for free. The Python prototype
should grow toward this incrementally as automation use cases
appear.

### 13.2 Batch invocation and fast startup

Current state: SMOLA is a single-file CLI. For interactive use this
is correct. For pipelines that compile thousands of small candidates
per training step or per fuzz iteration, Python interpreter startup
dominates total wall time.

Future hook: a `--batch` mode that reads multiple `(input, output)`
pairs from a manifest file or stdin and processes them in one
process, amortizing startup. The interface should be defined now so
the Rust port adopts it without redesign:

```
smola --batch manifest.json
  # manifest.json: [{"in": "a.smola", "out": "a.s"}, ...]
  # or:
smola --batch -  # reads NDJSON from stdin
```

The Rust port largely obviates the need — startup is milliseconds —
but the `--batch` interface is still useful for pipeline ergonomics
(one process, one exit code, structured per-job results).

### 13.3 Machine-queryable provenance

Current state: comment provenance is preserved by transferring
comment text into the generated `.s`. This is human-readable but
not directly machine-queryable; an external tool that wants to map
a `.s` line back to its `.smola` origin has to parse comments.

Future hook: a `--provenance-map <file>` mode that emits a separate
JSON file alongside the `.s`, mapping every emitted `.s` line to:

- source file path
- source line number
- source kind (instruction / directive / generated / bindings-table /
  comment-transfer / prologue / epilogue)
- the named bindings active at that line, if any

This lets pipelines correlate emitted assembly, profiling output
(e.g. `spike`/QEMU per-line counts), and the original SMOLA source
without textual heuristics. It also makes IDE integrations
(jump-to-source, inline disassembly view) much easier.

The data needed to produce this map already exists inside SMOLA;
emitting it is plumbing, not new logic.

### 13.4 Determinism as a public guarantee

Already stated in §4.6 and §11 as an internal property. Restated
here as a guarantee external tooling can rely on:

- Same SMOLA version + same mnemonic table + same input bytes →
  byte-identical `.s` output.
- No timestamps, no PID-derived names, no platform-dependent
  ordering, no nondeterministic iteration over dicts/sets.
- The mnemonic table version is part of the SMOLA version identity.

The Rust port must preserve this. In particular: `HashMap` iteration
order is unstable in Rust by default. Where SMOLA's output depends
on iteration order (bindings table, register pool scan, comment
flush order), the Rust port must use `BTreeMap`, sorted vectors,
or explicit insertion-order containers.

A `--version-info` flag emitting SMOLA version, mnemonic-table
version, and build hash supports reproducibility audits.

### 13.5 What is explicitly out of scope

To prevent §13 from becoming a feature wishlist:

- **SMOLA does not become an API library** in the Python prototype.
  Pipelines invoke the CLI. The Rust port may expose a library
  crate later if a concrete pipeline needs it; until then, the CLI
  is the contract.
- **SMOLA does not gain a daemon mode** with persistent state
  between invocations. `--batch` is the only concession to
  startup-cost concerns.
- **SMOLA does not score, profile, or otherwise reason about the
  output `.s`.** That is the consumer's job. SMOLA's contract
  ends at "deterministic, structured, well-commented `.s` plus
  optional provenance map."
- **SMOLA does not target non-RISC-V architectures.** Pipelines
  that want to generate ARM/x86/etc. assembly can build their own
  front ends; SMOLA stays RV64-specific.

### 13.6 Rust-port checklist (informational)

When the port happens, the following must be preserved or
introduced:

- [ ] CLI surface compatible with the Python prototype's flags
- [ ] Determinism (BTreeMap / sorted iteration where order matters)
- [ ] Structured diagnostics behind `--diagnostics-json`
- [ ] `--batch` mode reading a manifest
- [ ] `--provenance-map` mode emitting JSON line map
- [ ] `--version-info` exposing SMOLA + mnemonic-table versions
- [ ] Mnemonic table data file kept as plain data (TOML/JSON/RON),
      not compiled into source, so it can be updated without a
      recompile
- [ ] Byte-identical `.s` output verified against a golden corpus
      ported from the Python prototype

None of these change SMOLA's language or behavior. They constrain
how the implementation is structured so it remains usable by
external tooling.
