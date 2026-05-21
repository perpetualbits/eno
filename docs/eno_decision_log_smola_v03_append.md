# SMOLA v0.3 — decision log entry to append

The text below should be appended verbatim to `eno_decision_log.md`,
preserving the existing entries above it. It documents the
load-bearing decisions made in the 2026-05-21 session that moved
SMOLA from v0.2 to v0.3.

---

## 2026-05-21 — SMOLA v0.3 (hard cut from v0.2)

**Context:** v0.2 worked but its surface was ugly. Every SMOLA
construct started with `_`. Variable declarations needed `_var.t int
counter`. The language read more like a macro DSL than an assembly
dialect. The proximate decision was whether to keep evolving v0.2
incrementally or do a clean v0.3 rewrite. Chose rewrite. Hard cut,
not source-compatible.

### Direction: content-classified syntax

**Decided:** lines are classified by *what their first token is*, not
by syntactic prefix.

- A known SMOLA keyword → SMOLA construct
- A known RISC-V mnemonic (RVA23 table) → instruction passthrough
- A GAS directive (starts with `.`) → directive passthrough
- A label (`<ident>:` or `.L<id>:`) → label passthrough
- A comment (`#` or `//`) → comment (transferred to `.s`)
- Anything else → error: unknown mnemonic

This requires SMOLA to *know what instructions exist*. A mnemonic
table in `mnemonics.py` is the source of truth. v0.2 was deliberately
ignorant of the instruction set; v0.3 is deliberately well-informed.
The tradeoff: maintenance burden when new extensions ship, vs. strict
typo detection at preprocess time. Accepted the burden; the table is
plain Python data, one file, alphabetized, reviewable in normal diffs.

### Syntax simplifications

**Decided:** drop the `_` prefix from every SMOLA construct.

| v0.2                          | v0.3                                |
|-------------------------------|-------------------------------------|
| `_func name`                  | `func name`                         |
| `_endfunc` / `_endmethod`     | `end`                               |
| `_method Struct.name`         | `func Struct.name` (auto-detect)    |
| `_struct S { ... }`           | `struct S { ... }`                  |
| `_scope` / `_endscope`        | `scope` / `endscope`                |
| `_var.t int x`                | `int x`                             |
| `_var.s int x`                | `int.s x`                           |
| `_var.a int x`                | `int.a x`                           |
| `_var.a int x = a3`           | `int.a x = a3`                      |
| `_free name`                  | `zap name`                          |
| `_load_field` etc.            | `load_field` etc.                   |
| `_la_field`                   | `addr_field` (renamed)              |
| `! raw line`                  | `raw line`                          |

Default storage is T (caller-saved temporary); no suffix needed.
The .s/.a suffixes are the deviation from default.

### `func Foo.bar` auto-detects methods

**Decided:** if `Foo` is a previously-declared struct, `func Foo.bar`
implicitly binds `self` to `a0`. If `Foo` is not a declared struct,
the dot still becomes an underscore in the emitted symbol name but
no `self` binding is created. Removes the need for a separate
`_method` keyword.

### Initialization shorthand

**Decided:** typed declarations can include an initializer.

- `int counter 10` emits `li counter, 10`
- `int counter 0xDEAD` emits `li counter, 0xdead`
- `flt gain 0.75` emits the integer-bit-pattern + `fmv.w.x` sequence
  (f32 default) or a literal-pool entry + `la` + `fld` (f64)

This is the first SMOLA construct that emits an instruction at
declaration. v0.2 declarations were pure bookkeeping. The new
behavior is still zero-cost-beyond-what-you'd-have-written, but
declarations can now have side effects. Documented explicitly in
spec §2.4.

### `zap` replaces `_free`

**Decided:** keyword renamed for cleaner reading. Semantics unchanged:
T-storage returns to pool, S-storage releases name but keeps the
prologue commitment, A-storage releases name but ABI position is
unchanged.

### Anonymous temporaries reserved for v0.4

**Decided:** the form `int 10` (a type and an initializer with no
name) is reserved syntax. v0.3 errors on it with a hint to name
the binding. This holds the namespace without committing to
semantics. The right semantics for anonymous temporaries (single-
use? scoped to next mnemonic? expression-like?) is a design
question that needs concrete use cases to resolve. Defer entirely.

### Comment transfer

**Decided:** comments from source transfer to the generated `.s`.

- Block comments before a `func` flush to the `.s` *immediately
  before* the function's section header (so they precede the
  visible function unit).
- Block comments inside a function body flush at the position they
  appear in source.
- End-of-line comments on instruction lines transfer to the
  substituted instruction.
- Comments outside any function appear in order at top-level
  output.

Plus an auto-generated bindings table: immediately after each
function label (and prologue), SMOLA emits a block comment listing
every named variable in the function with its physical register and
storage class. Suppressed by `--no-provenance`. This is what makes
the generated `.s` debuggable: a reader can map abstract names back
to physical registers without scrolling.

Comments containing `//` are normalized to `#` for GAS compatibility.

### `raw` escape hatch

**Decided:** for the rare case where the user wants to emit an
instruction SMOLA's mnemonic table doesn't know about (a brand-new
extension, a vendor extension), a `raw <line>` keyword passes the
tail through verbatim with no checks. Provenance comment notes the
rawness. Replaces v0.2's `!` prefix.

### Mnemonic table coverage

**Decided:** the table covers the RVA23 baseline:
- RV32I, RV64I (base integer)
- M (mul/div), A (atomics)
- F, D (single/double float)
- C (compressed)
- Zicsr, Zifencei
- Zba, Zbb, Zbc, Zbs (bit manipulation)
- V (RVV 1.0)
- Standard pseudo-instructions (`li`, `mv`, `ret`, `j`, `jr`,
  `beqz`, `bnez`, `call`, `tail`, FP unary pseudos, etc.)

Roughly 500 mnemonics. Test asserts the total stays in a reasonable
range (350–1000) so an accidental large removal fails loudly. Adding
a new extension means editing one file (`mnemonics.py`).

Deliberate omissions: Zfh (half-precision), Sv* (supervisor), H
(hypervisor), debug, vendor extensions. Add when a real use case
appears.

### Implementation tree

```
tools/smola/
    src/smola/__init__.py        v0.3.0
    src/smola/mnemonics.py       NEW — closed RV mnemonic table
    src/smola/errors.py          unchanged in shape
    src/smola/lexer.py           rewritten — content classification
    src/smola/symbols.py         lightly edited; added has_struct()
    src/smola/regalloc.py        rename free → zap; bug fixes; add
                                  Allocator.history for the bindings
                                  table
    src/smola/frame.py           unchanged
    src/smola/translator.py      rewritten — new dispatch, comment
                                  transfer, bindings table, init
                                  emission
    src/smola/cli.py             unchanged
    src/bin/smola                unchanged
    tests/                       89 tests; new test_mnemonics.py
    examples/point.smola         ported to v0.3
    examples/render_square.smola NEW — demonstrates init shorthand
    examples/insn_length.smola   ported to v0.3
    Makefile                     unchanged
    README.md                    rewritten for v0.3
```

89 tests passing on the host. Assembly verification with
`riscv64-linux-gnu-as` is pending toolchain availability (the
sandbox where SMOLA was developed lacks the cross toolchain;
`make check-assembles` is the target Roland runs locally).

### Status of v0.2 artifacts

v0.2 implementation and v0.2 spec are discarded. The v0.3
`smola_design.md` §10 migration table is the historical record.
v0.2 was not shipped to anything; nothing depends on it.

---

End of v0.3 entry. Earlier log entries are preserved above this one.
