# SMOLA

A Python preprocessor for RISC-V GAS assembly. Adds named registers,
struct field access, function frame planning, and method calls. Output
is plain `.s` that standard `riscv64-linux-gnu-as` consumes.

SMOLA is the macro-language companion to SMOLR and smold. See
`spec/Smola_Spec.md` for the full design document; the section
references below match.

## Status

v0.1 (M1–M4 of the spec's milestone list). All v0.1 features in §2
are working. Tested entirely on the host (no cross-toolchain
verification yet — that's the §7 acceptance criterion when binutils
is available).

Implemented in v0.1:

- line-oriented lexer with five line kinds
- three-pool register allocator (T / S / A) with named bindings,
  aliases, free-and-reuse semantics
- struct declarations with natural-alignment layout
- `.smola.func` / `.smola.endfunc` with frame planning
- `.smola.method` / `.smola.endmethod` with implicit `self`
- `LOAD_FIELD`, `STORE_FIELD`, `LA_FIELD`
- `CALL` with argument-shuffle resolution and cycle detection
- `!` escape hatch for raw assembly
- provenance comments in the generated `.s`

Not yet implemented (deferred per §2.8):

- inheritance, generics, virtual dispatch
- scope-tracked destructors
- `include`
- conditional assembly via SMOLA (use GAS `.if` as pass-through)
- RVC-aware register preference (allocator is round-robin in v0.1)

## Layout

```
spec/Smola_Spec.md      # the design document (start here)
src/smola/              # the Python package
    __init__.py
    lexer.py            # line classification and tokenization
    regalloc.py         # register pools and named bindings
    symbols.py          # struct table and field resolution
    frame.py            # prologue / epilogue planner
    translator.py       # orchestrator
    cli.py              # argparse driver
    errors.py           # SmolaError + subclasses with source locations
src/bin/smola           # executable entry point
tests/                  # unit tests + a pytest-free runner
examples/               # worked .smola sources and their .s outputs
Makefile                # test + examples + clean targets
```

## Quick start

```
make test                  # run all unit tests
make examples              # translate all examples/*.smola to .s

# Translate one file
python3 src/bin/smola examples/point.smola --stdout
```

## A taste

Input (`examples/point.smola`):

```
.smola.struct Point {
    x: i64,
    y: i64,
}

.smola.method Point.translate
    VAR.A dx
    VAR.A dy
    VAR.T cx
    VAR.T cy

    LOAD_FIELD cx, self, Point.x
    LOAD_FIELD cy, self, Point.y
    ADD cx, cx, dx
    ADD cy, cy, dy
    STORE_FIELD cx, self, Point.x
    STORE_FIELD cy, self, Point.y
.smola.endmethod
```

Output (key fragment of `examples/point.s`):

```
Point_translate:
    # smola: bind self -> a0  (argument, implicit)
    # smola: bind dx -> a1  (argument)
    # smola: bind dy -> a2  (argument)
    # smola: bind cx -> t0  (caller-saved)
    # smola: bind cy -> t1  (caller-saved)
    ld   t0, 0(a0)    # LOAD_FIELD cx, self, Point.x
    ld   t1, 8(a0)    # LOAD_FIELD cy, self, Point.y
    add  t0, t0, a1   # ADD cx, cx, dx
    add  t1, t1, a2   # ADD cy, cy, dy
    sd   t0, 0(a0)    # STORE_FIELD cx, self, Point.x
    sd   t1, 8(a0)    # STORE_FIELD cy, self, Point.y
    ret               # smola: leaf epilogue
    .size Point_translate, .-Point_translate
```

Leaf-function detection means no prologue overhead. Provenance
comments on every line make the generated `.s` debuggable in
isolation. Use `--no-provenance` to drop them.

## Next steps

Per the spec milestones:

- **M5**: port a representative subset of `tools/smold/src/core.S` to
  `.smola` and verify byte-identical objects against the hand-written
  baseline. This is the load-bearing acceptance test.
- **M6**: rewrite SMOLR's runtime resolver assembly in SMOLA, once
  SMOLR Phase 3 lands.
- **M7**: polish — better diagnostics, optional RVC preference hint
  in the allocator, optional parallel-move resolver for `CALL`, real
  `include` support.

See `spec/Smola_Spec.md` §8 for the full milestone list.
