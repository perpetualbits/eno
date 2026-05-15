# smold Design

The full design document is in `design.pdf` in this directory.

That document is the authoritative plan for smold. It covers:

- The two-personality split (development tool / embedded effect)
- Atom + reachability architecture and granularity rules
- Proposed module layout (core, RV64I, RVC, extension capsules, dev-only)
- Embedded runtime flow and dispatch strategy
- Output styles (minimal embedded / development / artistic cave-wall)
- Coverage-driven decoder growth and SMOLR integration
- Linker / section strategy for atom-discipline assembly
- Size targets and milestones M1 through M7

## Milestones

- [x] **M1: Fallback walker.** Walk a memory range, detect 16-bit vs 32-bit
      instructions, emit `.2byte` / `.4byte` lines.
- [ ] **M2: Minimal RV64I decode.** lui, auipc, jal, jalr, branches, loads,
      stores, addi, basic integer reg-reg ops.
- [ ] **M3: Essential RVC decode.** c.addi, c.li, c.lui, c.mv, c.add,
      c.ldsp, c.sdsp, c.lwsp, c.swsp, c.ld, c.sd, c.lw, c.sw, c.j, c.jr,
      c.jalr, c.beqz, c.bnez.
- [ ] **M4: Coverage reporter.** External tool mode scanning a binary and
      reporting decoded instructions, unknown instructions, family counts,
      required decoder atoms.
- [ ] **M5: SMOLR integration.** Use the coverage report (or SMOLR's own
      knowledge) to select embedded disassembler atoms.
- [ ] **M6: Cave-wall integration.** Pipe smold output into the graphics
      layer as texture / carving mask / inscription stream input.
- [ ] **M7: Optional extension growth.** Add M, A, B subset, F/D subset,
      V subset, Zfa/Zicond as actual demo binaries need them.

## M1 deliverables (this commit)

- `src/core.S` — atoms: `smold_insn_length`, `smold_emit_hex_u16`,
  `smold_emit_hex_u32`, `smold_emit_pc_label`, `smold_emit_dot_halfword`,
  `smold_emit_dot_word`, `smold_walk_range`, plus internal helpers.
- `include/smold.h` — public C contract.
- `cli/smold-cli.c` — three-mode CLI.
- `tests/test_core.c` — runtime unit tests.
- `tests/test_layout.c` — compile-time struct-layout assertions.
- Makefile, README, this file.

## What M1 deliberately does *not* do

- No instruction mnemonics. Every instruction prints as `.2byte`/`.4byte`.
- No symbols, labels, or ABI register names.
- No relocation display.
- No section-header parsing in the CLI. ELF mode walks the first
  executable `PT_LOAD` only.
- No 48-bit-or-longer encoding support. Those are rejected as
  `SMOLD_ERR_UNSUPPORTED_LEN`.

These are all M2+ work.
