# SMOLA v0.3.0 — install bundle

This tarball expands at the **ENO repository root**. Paths are
relative to that root:

```
docs/
    smola_design.md                            (replaces v0.2 spec)
    eno_project_index.md                       (replaces existing)
    eno_decision_log_smola_v03_append.md       (paste into existing
                                                eno_decision_log.md)
    _session_2026-05-21_summary.md             (session record)

tools/smola/                                   (replaces v0.2 tree
                                                wholesale)
    Makefile
    README.md
    src/
    tests/
    examples/
```

## Install steps

```sh
# From the ENO root:
cd /path/to/eno

# Remove the v0.2 SMOLA tree (it's not source-compatible with v0.3).
rm -rf tools/smola

# Extract the bundle.
tar xzf tars/smola-v0.3.0.tar.gz

# After extraction, two extra cleanup tasks:
#   1. The old v0.2 spec at tools/smola/spec/Smola_Spec.md is gone
#      automatically (we removed the directory above and didn't
#      restore the spec/ subdir — the canonical doc now lives at
#      docs/smola_design.md).
#   2. examples/counter.smola from v0.2 is also gone for the same
#      reason — it wasn't ported to v0.3.

# Append the decision log entry. Open docs/eno_decision_log.md in
# your editor and paste the contents of
# docs/eno_decision_log_smola_v03_append.md at the bottom (or, if
# you prefer):
cat docs/eno_decision_log_smola_v03_append.md \
    >> docs/eno_decision_log.md
# Then delete the append file:
rm docs/eno_decision_log_smola_v03_append.md

# Verify the install.
cd tools/smola
make test                  # should show: Result: 89 passed, 0 failed
make examples              # translates examples/*.smola to examples/*.s
make check-assembles       # if riscv64-linux-gnu-as is available
```

## What changed from v0.2

See `docs/smola_design.md` §10 for the full migration table. In
summary: no more `_` prefix on SMOLA constructs, `func`/`end`
replaces `_func`/`_endfunc`, bare type keywords (`int x`) replace
`_var.t int x`, `zap` replaces `_free`, initialization shorthand
added (`int counter 10`, `flt gain 0.75`), strict typo detection via
the new mnemonic table, comments transfer to the generated `.s`.

## Files outside this bundle

You'll want to also remove the leftover v0.2 spec file if it still
exists:

```sh
rm -f tools/smola/spec/Smola_Spec.md
rmdir tools/smola/spec 2>/dev/null || true
```

## If something breaks

- Tests fail to import: check Python version (3.10+ recommended).
- Existing scripts that called the v0.2 CLI: arguments are
  compatible; only the input source files need migration.
- A `.smola` file from v0.2 won't translate: this is expected. See
  the migration table in the spec for line-by-line conversions.
