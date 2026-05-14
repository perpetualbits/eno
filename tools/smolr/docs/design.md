# SMOLR Design

The full design document is in `design.pdf` in this directory.

That document is the authoritative plan for SMOLR. It covers:

- Purpose, philosophy, naming, target platform (RVA23U64-first)
- RISC-V control-flow primer (jal, jalr, auipc, relaxation)
- ELF design, runtime resolver, import-stub design
- Hash strategy for symbol resolution
- Relocation support plan and what's intentionally unsupported
- RVA23-first optimisation policy (RVC, scalar bitmanip, RVV)
- Benchmark suite and "top in class" definition
- Phase-by-phase work plan (Phase 0 through Phase 8)

For day-to-day phase tracking, see `work-plan.md`.

For the relocation survey output, see `riscv-relocation-survey.md` (generated
by `make report` from the survey corpus).

## Per-doc index

- `design.pdf` — the long-form design document (this is the source of truth)
- `work-plan.md` — per-phase progress tracker
- `riscv-relocation-survey.md` — Phase 1 deliverable, regenerated from the
  survey corpus
