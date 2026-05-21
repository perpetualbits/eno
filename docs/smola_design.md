# SMOLA: A Python-Preprocessed Macro Language for RISC-V Assembly

## Status

Design document v0.3. Implementation prototype at `tools/smola/` in the
ENO monorepo. Hard cut from v0.2 (no source compatibility). Companion
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
  `struct`, `stack`, `int`, `ptr`, `flt`, `vec`, `zap`)
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
    int counter 4096
    flt gain 0.75

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

- `struct <Name> { <fields> }` — declare a struct layout. Same
  semantics as v0.2: natural alignment, primitive field types
  (`i8`/`u8`/`i16`/`u16`/`i32`/`u32`/`i64`/`u64`/`f32`/`f64`/`ptr`).

#### Variable declarations (replace v0.2's `_var.*`)

Form: `<type> <name> [<initializer>]`

- `int counter` — allocate a caller-saved integer register, name it
  `counter`.
- `int counter 10` — same, then emit `li counter, 10` to initialize.
- `ptr base` — allocate a caller-saved integer register, document as
  pointer.
- `flt gain 0.75` — allocate an FP register, emit initialization
  (currently a placeholder; loading a float immediate requires a
  small literal pool; see §2.4).
- `vec data` — allocate a vector register.

By default, variable declarations claim **caller-saved (temporary)**
storage. To claim callee-saved or argument storage:

- `int.s persistent` — callee-saved integer (`s0`..`s11`).
- `int.a x` — next free argument register (`a0`..`a7`).
- `int.a x = a3` — pin to a specific argument register.

The dot-suffix replaces v0.2's `_var.t` / `_var.s` / `_var.a`. The
common case (caller-saved temporary) needs no suffix.

#### `zap <name>[, <name>...]`

Release one or more named bindings. Replaces v0.2's `_free`.

Behavior:
- removes the symbolic binding
- for temporaries: returns the register to its pool
- for callee-saved: removes the name but leaves the prologue's
  save/restore in place (we already committed to saving it)
- for arguments: removes the name; the register's ABI position is
  unchanged

#### `stack <N>`

Inside a function, request `N` extra bytes of user-controlled stack
space. Same as v0.2.

### 2.4 Variable initialization

v0.3 adds initialization syntax that emits an instruction at
declaration:

| Declaration               | Emitted                                  |
|---------------------------|------------------------------------------|
| `int counter`             | (nothing — declaration only)             |
| `int counter 10`          | `li counter, 10`                         |
| `int counter 0xDEAD`      | `li counter, 0xdead`                     |
| `ptr base`                | (nothing)                                |
| `flt gain 0.75`           | see below — requires literal pool        |
| `vec data`                | (nothing)                                |

For floating-point initialization, RISC-V has no "load immediate"
instruction equivalent to `li`. The standard idioms are:

- Load from a `.rodata` literal pool: `la t0, .Lconst_0p75; flw gain,
  0(t0)`.
- Synthesize via integer bit pattern: `li tN, 0x3f400000; fmv.w.x
  gain, tN` for f32.

v0.3 chooses the bit-pattern synthesis path for `f32` and the literal-
pool path for `f64`. Both happen at preprocess time; the user just
writes `flt gain 0.75` and SMOLA emits the right sequence. f32 is
fully inline; f64 emits a literal pool entry at the end of the
function's `.text.<func>` section.

This is the first SMOLA construct that *emits an instruction at
declaration*. v0.2's `_var.t` was pure bookkeeping. The new behavior
is documented explicitly because it represents a small departure from
the "declarations are free" principle: declarations are still
*deterministic* and *zero-cost-beyond-what-you'd-have-written*, but
they can now have side effects.

### 2.5 Anonymous temporaries (reserved syntax)

The form `int 10` (a type and an initializer with no name) is
*reserved* for v0.4 anonymous temporaries. v0.3 errors on this
syntax with a hint:

```
foo.smola:42: error: anonymous temporaries reserved for v0.4
        int 10
hint: name the binding explicitly: 'int tmp 10'
```

This holds the namespace without committing to semantics. The right
semantics for anonymous temporaries (single-use? scoped to next
mnemonic? expression-like?) is a design question that needs concrete
use cases to resolve.

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

### 2.11 What v0.3 does NOT have

- Inheritance, generics, virtual dispatch.
- Anonymous temporaries (§2.5 reserved syntax).
- `vec` struct fields (use raw RVV instructions for vector load/store).
- `include` of other `.smola` files.
- Conditional assembly via SMOLA (use GAS `.if`/`.endif`).
- Soft-float ABI.
- The curated `_v.*` RVV vocabulary mentioned in v0.2's milestone list.
  Raw RVV instructions pass through cleanly; the vocabulary lands when
  a concrete wavelet kernel needs it.

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
| `_var.t flt g`                | `flt g`                             |
| `_var.t vec v`                | `vec v`                             |
| (no init form)                | `int x 10`, `flt g 0.75`            |
| `_free name`                  | `zap name`                          |
| `_load_field`                 | `load_field`                        |
| `_store_field`                | `store_field`                       |
| `_la_field`                   | `addr_field` (renamed)              |
| `_call target, args`          | `call target, args`                 |
| `_add a, b, c`                | `add a, b, c` (raw RV mnemonic)     |
| `! raw line`                  | `raw line` (or just the line itself)|
| any unknown SMOLA `_keyword`  | error                               |
| any unknown lowercase mnemonic| was passthrough → now error         |

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
