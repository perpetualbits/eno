# SMOLA v0.3.0 — refinements bundle

This tarball expands at the **ENO repository root**. It updates an
already-installed v0.3 SMOLA with the data-section + width-typed-
declaration refinements.

## What's in this bundle

```
docs/
    smola_design.md                              (updated spec)
    _session_2026-05-21_afternoon_summary.md     (session record)

tools/smola/                                     (replaces existing
                                                  v0.3 SMOLA tree)
    Makefile
    README.md                                    (updated)
    src/                                         (lexer, regalloc,
    tests/                                        translator changes)
    examples/                                    (3 unchanged + 2 new)
```

## Install

```sh
# From the ENO root:
cd /path/to/eno

# Remove the previous v0.3 SMOLA tree.
rm -rf tools/smola

# Extract the bundle.
tar xzf /path/to/smola-v0.3-refinements.tar.gz

# Replace the spec doc.
# (smola_design.md was overwritten by extraction — no manual step.)

# Verify.
cd tools/smola
make test                  # should show: Result: 114 passed, 0 failed
make examples              # translates examples/*.smola to examples/*.s
make check-assembles       # if riscv64-linux-gnu-as is available
```

## What changed from the morning v0.3

The decisions logged in `docs/eno_decision_log.md` under the
afternoon 2026-05-21 entry are now implemented:

1. **`flt` keyword removed.** Use `f32` / `f64` explicitly.
2. **Width-typed integer declarations** added (`i8`/`u8`/.../`u64`
   each with `.s` and `.a` variants). All allocate from the integer
   pool; the declared width is documentation that appears in the
   bindings table.
3. **Data-section declarations** added (spec §2.12). Type keywords
   in `.data`/`.rodata`/`.bss`/etc. introduce labeled data blocks
   with automatic alignment and sizing.

Tests grew from 90 to 114. Examples grew from 3 to 5
(`jump_table.smola` and `wavelet_coefs.smola` are new).

## Migration notes for existing `.smola` files

- Any file using `flt` will fail to translate. Change `flt` to
  `f32` or `f64` as appropriate. The error message includes the
  hint inline.
- All other v0.3 source remains compatible; no behavioral changes
  to existing features.
