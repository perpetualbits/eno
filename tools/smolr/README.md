# tools/smolr

**S**mall **M**insize-**O**riented **L**inker for **R**ISC-V Linux.

A RISC-V-native sizecoding linker and runtime import system for tiny dynamically
linked Linux executables. The first target is ENO's own demoscene output:
graphical/audio/text demos for RV64GC, RVA22, and RVA23 Linux systems.

Inspired by [smol](https://github.com/Shizmob/smol) (Linux/x86, x86-64),
[Crinkler](https://github.com/runestubbe/Crinkler) (Windows), and
[dnload](https://github.com/faemiyah/dnload), but **not a port**. RISC-V has its
own instruction encoding, linker relaxation, compressed instructions,
relocation pairs, and ABI conventions, and SMOLR exploits those deliberately.

This is **Segher's territory** in the long run — he's the GCC maintainer on the
crew and owns the relocation-survey review and the deep optimisation passes.
Phases 0–4 (scaffolding, survey, minimal ELF, first dynamic call) can land
without blocking on him.

## Status

**Phase 0–1: setup and relocation survey.** No linker exists yet. We're
measuring what the host toolchain emits so we know what SMOLR has to handle.

See `docs/design.md` for the full plan and `docs/work-plan.md` for phase
tracking.

## What SMOLR will do

1. **Minsize linker / runtime import system** — replace bulky ELF dynamic-
   linking metadata with a tiny runtime resolver and compact import table.
2. **RISC-V code-shaping layer** — RVC- and Zcb-aware import stubs, scalar
   bitmanip kernels where they shrink code, RVV for data-parallel kernels.
3. **Optional compression / packer layer** — UPX or a custom decompressor on
   top, once the uncompressed ELF is already tiny.

The order matters: SMOLR reduces the executable *before* compression. UPX
compresses what's already there. SMOLR is what feeds the packer.

## Target tiers

SMOLR explicitly supports three architecture tiers, matching ENO's test
hardware:

| Tier | ISA string                          | Real silicon          | Role                    |
|------|-------------------------------------|-----------------------|-------------------------|
| 0    | `rv64gc`                            | Milk-V Duo S (C906)   | Bootstrap / experiments |
| 1    | `rv64gcv_zba_zbb_zbs`               | Milk-V Jupiter (K1/M1)| Daily development target|
| 2    | `rva23u64`                          | SpacemiT K3 boards    | Primary release target  |

Tier 1 is the daily-driver target. Tier 2 is the showcase target for the
benchmark wins. Tier 0 keeps us honest about ISA assumptions and may matter
again if SMOLR ever grows a bare-metal mode for the Duo S.

Note: lib/wavelet already uses `RISCV_MARCH = rv64gcv_zba_zbb` for its
cross-build. SMOLR matches that exactly for Tier 1, with `_zbs` added because
RVA22 mandates it.

## Quick start

From the ENO root, or from inside `tools/smolr/`:

```sh
make probe          # inspect local toolchain, write build/toolchain-probe.txt
make survey         # build the relocation survey corpus
make report         # generate docs/riscv-relocation-survey.md from the corpus
make baseline       # measure normal-ld + optional UPX sizes for comparison
make clean
```

`make` with no target runs `probe survey report baseline` in order.

The Makefile auto-detects native vs cross: if `uname -m` is `riscv64` it uses
unprefixed tools, otherwise it uses the `riscv64-linux-gnu-` cross prefix
(override with `SMOLR_CROSS=`).

## Layout

```
tools/smolr/
├── README.md                # This file
├── Makefile                 # Drives the survey and reports
├── docs/
│   ├── design.md            # The original SMOLR design document
│   ├── work-plan.md         # Phase tracking
│   └── riscv-relocation-survey.md  # Phase 1 deliverable (generated)
├── tools/
│   ├── probe-toolchain.sh   # Toolchain capability check
│   └── size-baseline.sh     # Normal-ld + UPX size measurements
├── survey/                  # Phase 1 test corpus
│   ├── tests/               # Tiny C and asm test programs
│   └── scripts/
│       ├── inspect-all.sh   # Runs readelf/objdump on every survey object
│       └── build-report.py  # Aggregates results into the markdown report
└── build/                   # All artifacts (git-ignored)
```

Later phases will add `runtime/` (resolver + stubs), `frontend/` (object
scanner + codegen), and `examples/` (working SMOLR-linked demos).

## License

To be decided alongside the rest of ENO. Until then treat as
"all rights reserved by the contributors, do not redistribute."
