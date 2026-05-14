# Running SMOLR Phase 0–1 on the Jupiter

The Jupiter is a native RISC-V host, so SMOLR scripts auto-detect and use
unprefixed tools (no `riscv64-linux-gnu-` prefix).

## One-time setup on the Jupiter

```sh
sudo apt install gcc binutils make python3 qemu-user upx-ucl
# qemu-user and upx-ucl are optional but recommended for the baseline.
```

If the local distro splits `gcc` differently (e.g. needs `gcc-14` explicitly),
override per-invocation:

```sh
make probe GCC=gcc-14
```

## Running the survey

```sh
cd ~/git/eno
git pull   # once the smolr changes land

cd tools/smolr
make probe         # writes build/toolchain-probe.txt
make survey        # builds the test corpus in build/survey/
make report        # writes docs/riscv-relocation-survey.md
make baseline      # writes build/baseline-sizes.txt
```

`make` with no target runs all four in order.

## What to send back

Three files are enough for Phase 1 review:

1. `tools/smolr/build/toolchain-probe.txt` — confirms which `-march` strings
   the local toolchain accepts and which it rejects.
2. `tools/smolr/docs/riscv-relocation-survey.md` — the generated relocation
   matrix per test.
3. `tools/smolr/build/baseline-sizes.txt` — what normal-ld and (optionally)
   UPX produce, our "must beat" numbers.

Optional but useful when something looks weird:

- Any `.compile.log` or `.link.log` file under `build/survey/` that mentions
  an error.
- The raw `.reloc` or `.disasm` for a specific (test, tier, combo) we're
  trying to understand.

## Cross-host alternative

If you also want to run the survey on your x86 laptop with the cross
toolchain, the same commands work — Make will pick `riscv64-linux-gnu-`
automatically. Useful for catching toolchain differences between distros.

## Troubleshooting

- **`-march=rva23u64` rejected**: expected on older toolchains. `build-survey.sh`
  silently falls back to an expanded ISA string. The probe report (step 1)
  shows which strings the toolchain accepts.
- **`03-call-libm` link fails**: check that `libm.so` and crt files exist on
  the system. The `.o` is still produced for relocation inspection.
- **`02-call-multi` link fails**: expected — `stdout` as a `void *` is wrong
  C (it's a `FILE *`), but the object's relocations are what we care about.
  This is intentional: it exercises the external-data path.
