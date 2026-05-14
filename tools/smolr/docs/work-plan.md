# SMOLR Work Plan

Phase-by-phase progress tracker. Update each phase's status as it lands.
Refer back to `design.md` for the original full plan.

## Phase 0: Setup — IN PROGRESS

Repo scaffolding inside `tools/smolr/`, toolchain probe, baseline
measurements.

- [x] Directory layout matching ENO conventions
- [x] `README.md`
- [x] `Makefile` with `probe survey report baseline clean` targets
- [x] `tools/probe-toolchain.sh`
- [x] `tools/size-baseline.sh`
- [ ] First clean `make probe` run on Jupiter
- [ ] License decision (deferred — see top-level ENO discussion)

Exit: `make probe` produces a clean toolchain report on the Jupiter,
matching expectations for the K1/M1.

## Phase 1: Relocation survey — IN PROGRESS

Determine exactly what relocations SMOLR must handle, and how the toolchain
emits them under each ISA tier and each relaxation setting.

- [x] Test corpus covering:
      - Direct call to external libc function (`puts`)
      - Multiple external calls in one translation unit
      - Cross-library call (libm `sqrt`)
      - Indirect call via function pointer
      - Pure syscall, no libc imports
      - External data access (expected to be tricky / unsupported)
- [x] Build under three ISA tiers: rv64gc, rv64gcv_zba_zbb_zbs, rva23u64
- [x] Build with `-mrelax` and `-mno-relax`
- [x] Test `-fno-plt` and default PLT
- [x] Aggregate readelf/objdump outputs into `riscv-relocation-survey.md`
- [ ] Review supported relocation set with Segher before locking it in

Exit: We know exactly which `R_RISCV_*` types SMOLR must handle to reach the
"one dynamic call" milestone in Phase 3.

## Phase 2: Minimal ELF64/RISC-V executable — NOT STARTED

Hand-rolled minimal RV64 ELF that exits cleanly, no imports. First proof of
ELF construction.

## Phase 3: One imported function — NOT STARTED

First proof of life: dynamically resolve one libc symbol and call it.

## Phase 4: Multiple imports and libraries — NOT STARTED

## Phase 5: SMOLR frontend (object scanner + codegen) — NOT STARTED

## Phase 6: RVA23 size/perf optimisation pass — NOT STARTED

This is where Segher's input becomes load-bearing.

## Phase 7: Demo-library stress tests — NOT STARTED

Cairo A8 surfaces, OpenGL/EGL minimal context, audio library calls.
The first realistic ENO/SPINE demo scenario.

## Phase 8: Packer strategy — NOT STARTED

UPX vs custom decompressor vs RISC-V instruction filter.

## Hardware test matrix

| Phase exit | Must run on            | Should also run on          |
|------------|------------------------|-----------------------------|
| 1          | x86 cross host         | Milk-V Jupiter              |
| 2          | qemu-riscv64           | Milk-V Jupiter              |
| 3          | qemu-riscv64           | Milk-V Jupiter              |
| 4+         | Milk-V Jupiter         | qemu, future K3 board       |
| 6          | Milk-V Jupiter + K3    | All available silicon       |

The Duo S boards are bonus targets — useful for measuring overhead on a
smaller core (C906) and for any future bare-metal SMOLR mode.
