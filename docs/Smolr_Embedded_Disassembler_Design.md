# smold: An Atom-Composed RISC-V Disassembler

## Status

Design document v3. M1 (fallback walker) implemented and ready for test on
RV64 boards. M2 (RV64I decode) is the next milestone. Incorporates framings
from the retired CARVE design document.

## Project identity

**smold** lives at `tools/smold/` inside the ENO monorepo. It is the
byte-level disassembler half of a two-tool pair with `tools/smolr/`, the
sizecoding linker. The two are designed to inform each other:

- smold reads SMOLR's output and tells you what is in it.
- SMOLR depends on smold's byte classification when transforming output
  for compression.

The name is short, distinct in logs and `grep`, and tells the
cave-carving story without ceremony.

## 1. Core idea

smold is a library of small atoms.

A complete build is a useful external disassembler for RISC-V ELFs. A demo
build links only the atoms needed by that specific demo, using the same
discipline as the rest of the ENO system: softsynth atoms, graphics atoms,
SPINE atoms, instrument tables, effect tables, and decode atoms are
included only when reachable.

The embedded disassembler is therefore not a gimmick. It is both:

- a debugging and inspection tool for size-constrained RISC-V binaries
- an artistic source generator, producing real code-derived text usable
  as visual material

One intended visual use is a cave scene: a procedurally generated cave
system where firelight flickers across walls covered in ancient carvings.
The carvings are not arbitrary text. They are the demo disassembling
itself.

### 1.1 Decode encodings, not intent

smold decodes the actual instruction encodings present in memory, not the
programmer's likely intent. For example:

- `addi x0, x0, 0` stays `addi x0, x0, 0`, not `nop`
- `jalr x0, x1, 0` stays `jalr x0, x1, 0`, not `ret`
- `c.jr ra` stays `c.jr ra`, not `ret`

Pseudo-instruction reconstruction is an optional presentation layer, never
part of the core decoder. This rule:

- reduces implementation complexity
- improves atomization (no pseudo-instruction inference logic to drag in)
- preserves executable authenticity
- improves SMOLR inspection fidelity (what is actually emitted matters
  more than what the programmer would have written)
- and better reflects the actual binary to the cave-wall effect

### 1.2 smold as reference atomized subsystem

smold itself serves as a proving ground for SMOLR's atomization and
dead-code elimination philosophy. If smold cannot effectively prune unused
functionality from its own build, the wider ENO/SMOLR ecosystem likely
cannot either. The M1 implementation's atom count (11 atoms in `core.S`,
of which the CLI uses only a subset, with `--gc-sections` cleaning up the
rest) is the first empirical check on this thesis.

## 2. Goals

### 2.1 Development tool goals

The development build helps inspect SMOLR-generated executables and
answer:

- Which instruction families are present after final linking?
- Which compressed instructions appear?
- Which instructions are not yet covered by the embedded decoder?
- Did linker relaxation or instruction compression change the final code
  shape?
- Which decode atoms would be needed to disassemble this specific binary?
- Which parts of a library are being pulled in unexpectedly?
- Which bytes are code, and which are data?

That last question is where smold becomes load-bearing for SMOLR.

The development tool may support ELF parsing, symbols, section names,
executable segment detection, and instruction coverage reporting.

### 2.2 Embedded demo goals

The embedded version:

- walks a known executable memory range, usually `.text`
- decodes 16-bit and 32-bit RISC-V instructions
- emits disassembly text into a buffer
- uses simple textual formatting suitable for later graphics processing
- degrades gracefully when it sees an unknown instruction
- is link-pruned to only the instruction families and emitters needed
- avoids bulky features such as symbols, labels, ELF parsing, ABI register
  names, and pseudo-instruction prettification unless explicitly needed

The embedded version may be incomplete if the fallback output remains
useful.

## 3. Non-goals

The embedded version does not aim to be a full replacement for `objdump`.
By default it does not need:

- symbolic labels
- relocation display
- source-line mapping
- ABI register names
- pseudo-instruction reconstruction
- complete CSR name tables
- full RVA23 coverage
- debug information parsing
- exact reconstruction of original assembly source

The goal is to disassemble the actual machine code that exists in the
final linked executable, not to recover what the programmer originally
wrote.

## 4. Two build personalities

### 4.1 Full development disassembler

May include: ELF parser; executable segment or `.text` section discovery;
optional symbol table support; optional relocation display; instruction
coverage reporting; broad RISC-V decode coverage; optional pretty-printing
modes; unknown-instruction reporting. Larger is acceptable here.

### 4.2 Embedded runtime disassembler

Includes only: memory range walker; instruction length detection; minimal
output buffer writer; selected instruction-family decoders; simple
register and immediate formatting; fallback `.2byte` / `.4byte` output.
Aggressively size-pruned.

## 5. Architectural principle: atoms and reachability

An **atom** is the smallest independently includable code or data unit
intended for linker- and SMOLR-level reachability analysis and elimination.

smold is split into independently removable atoms. An atom can be:

- one function
- one small family decoder
- one string table
- one immediate formatter
- one register-name emitter
- one optional output style
- one instruction extension capsule

The final executable includes only atoms reachable from the chosen root
symbols. Conceptually:

```
roots = [_start, demo_main, selected_effects]
reachable = graph walk over symbol references and relocations
emit only reachable atoms
layout / relax / compress
```

The same approach applies to the whole demo:

```
demo entry
    -> SPINE event system
    -> cave text-carving effect
    -> embedded disassembler
        -> RV64I subset decoder
        -> RVC subset decoder
        -> fallback emitter
Everything else is discarded.
```

This works in practice because RISC-V toolchain conventions treat each
function in its own section (via `-ffunction-sections`), and the linker's
`--gc-sections` drops unreferenced sections.

## 6. Granularity rules

Maximum granularity is useful only when it does not increase total size.

### 6.1 Split aggressively when

- optional instruction extensions
- rare instruction families
- large decode functions
- optional output formats
- optional symbol handling
- optional ELF handling
- large lookup tables
- feature-specific strings
- development-only helpers

### 6.2 Group when smaller

- excessive alignment padding makes splitting costly
- too many relocations
- too many long calls or jumps
- tiny string fragments
- repeated prologue/epilogue code
- tables that compress better when contiguous
- helpers that are always used together

Practical rule: one atom per independently optional thing. Not one atom
per microscopic fragment.

### 6.3 Concrete size heuristic

A specific rule of thumb that helps when deciding whether to split:

> If an atom's body is smaller than its likely alignment padding plus
> relocation overhead, group it with related functionality. Otherwise
> split it.

On RV64 with section-per-function, the per-atom overhead is roughly
2-byte alignment padding (often zero, since instructions are already
aligned) plus one section header in the unlinked object (vanishes after
gc). Worst-case overhead per very small atom is ~32 bytes when alignment
and relocation interact badly.

Therefore:

- Atoms with bodies under ~32 bytes: usually group with a related helper
  or family decoder.
- Atoms with bodies of 32+ bytes representing one optional feature: split.
- Atoms representing rare extension capsules: always split regardless of
  size — the size win when the demo doesn't use the extension dominates.

This is a heuristic, not a strict rule. The optimal grouping depends on
linker behaviour, relaxation, compression, call frequency, locality, and
entropy effects. Measure when in doubt.

## 7. Proposed module layout

### 7.1 Core runtime modules

```
disasm_core/
    walk_range
    decode_instruction_length
    output_buffer_writer
    emit_char / emit_string / emit_space / emit_newline
    emit_hex_u16 / emit_hex_u32
    emit_signed_decimal_or_hex
    emit_xreg_numeric
    emit_freg_numeric
    emit_vreg_numeric
    fallback_dot_halfword
    fallback_dot_word
```

The embedded version always starts here.

### 7.2 RV64I decode modules

```
disasm_rv64i/
    decode_lui_auipc
    decode_jal_jalr
    decode_branch
    decode_load
    decode_store
    decode_op_imm
    decode_op
    decode_system_minimal
```

### 7.3 Compressed decode modules

```
disasm_rvc/
    decode_c_quadrant_0
    decode_c_quadrant_1
    decode_c_quadrant_2
    decode_c_addi / c_li / c_lui / c_mv_add
    decode_c_ld_sd / c_lw_sw
    decode_c_ldsp_sdsp / c_lwsp_swsp
    decode_c_j_jal / c_jr_jalr
    decode_c_beqz_bnez
    decode_c_shift_andi
```

RVC support is essential for size-constrained RISC-V demos.

### 7.4 Optional extension capsules

```
disasm_ext_m/      decode_muldiv
disasm_ext_a/      decode_atomic
disasm_ext_f/      decode_float_single
disasm_ext_d/      decode_float_double
disasm_ext_b/      decode_bitmanip_subset
disasm_ext_v/      decode_vector_subset
disasm_ext_zfa/    decode_zfa_subset
disasm_ext_zicond/ decode_conditional_zero
disasm_ext_csr/    decode_csr_numeric, csr_name_table_optional
```

Each extension is optional.

### 7.5 Development-only modules

```
disasm_elf/
    parse_elf_header
    parse_program_headers
    find_executable_segments
    find_text_section_optional
    parse_symbol_table_optional
    parse_string_table_optional

disasm_report/
    instruction_coverage_report
    unsupported_instruction_report
    required_decoder_atom_report
    size_contribution_report
    byte_classification_report     # consumed by SMOLR transforms

disasm_pretty/
    abi_register_names
    pseudo_instruction_printer
    symbolic_branch_labels
    symbol_plus_offset_formatting
```

These are not pulled into the embedded demo build unless intentionally
requested.

## 8. Embedded runtime flow

The embedded version avoids ELF parsing when possible. The demo exposes
linker symbols for known code ranges:

```
__text_start
__text_end
```

Then runtime disassembly is:

```
p = __text_start
pc = pc_base                   # see §8.1
out = text_buffer
while p < __text_end:
    h = load16(p)
    if (h & 3) != 3:
        decode16(h, pc, out)
        p += 2
        pc += 2
    else:
        w = load32(p)
        decode32(w, pc, out)
        p += 4
        pc += 4
    emit_newline(out)
```

The decoder never fails catastrophically. Unknown instructions become
data directives:

```
.2byte 0x1141
.4byte 0x00000517
```

This is both useful and visually acceptable.

### 8.1 PC base: link-time vs runtime

The `pc_base` parameter matters more than it looks. Three sensible
options:

- For embedded use that just feeds a graphics pipe: link-time address as
  a label is fine. The user does not care that the carving says `1234`
  versus `7fff_b234`.
- For embedded use that wants to render correct branch targets: use the
  runtime PC. On a Linux dynamic ELF this means reading the actual
  current PC at the walker entry, which costs a few bytes but is
  honest about ASLR.
- For development-tool use: almost always link-time addresses, because
  the user wants to cross-reference against the source ELF.

smold's `smold_walk_range` takes `pc_base` as a parameter rather than
baking in a choice. The CLI defaults to link-time PC for ELF mode (uses
`p_vaddr`); the embedded caller decides.

### 8.2 ELF parsing in the embedded version — sometimes worth it

The cave effect wants to disassemble the demo itself, but a demo loaded
on Linux may also want to render the carvings of `libc.text` or
`libm.text` — code it depends on but did not write. That requires
walking the dynamic loader's link map.

This is not M1 work. But the design path between "no ELF parsing in
embedded" and "full ELF parser" includes one tiny option: use `_r_debug`
or `dlinfo` to discover loaded segments. The walker itself does not
change; only the range-discovery step gains an option.

Phase 1 in this design space is `__text_start` / `__text_end`. Phase 2
is link-map enumeration if a demo wants it.

## 9. Development tool flow

The external development tool operates on an ELF file:

```
open ELF file
validate ELF64 little-endian RISC-V
read ELF header
read program headers
for each executable PT_LOAD segment:
    disassemble bytes from p_offset to p_offset + p_filesz
    use p_vaddr as pc base
collect instruction coverage
report unknown / unsupported instructions
report required decoder atoms
report byte classification for SMOLR consumption
```

Section-header support can be added later. Program headers are enough for
a first executable-image view.

## 10. Output style

### 10.1 Minimal embedded style

```
0000000000001348  c.addi x2,-16
000000000000134a  c.sdsp x1,8(x2)
000000000000134c  c.mv x15,x10
000000000000134e  lui x10,0
0000000000001352  addi x10,x10,84
```

Properties: numeric register names, no ABI names, no labels, no
pseudo-instructions, compact spacing, raw branch targets or immediates,
unknowns as `.2byte` / `.4byte`.

### 10.2 Development style

```
00001348: 1141     c.addi x2,-16
0000134a: e406     c.sdsp x1,8(x2)
0000134c: 87aa     c.mv x15,x10
0000134e: 00000537 lui x10,0x0
```

Development style may include raw bytes, addresses, symbols, and comments.

### 10.3 Artistic style layer and the carving-depth map

smold outputs plain text. The graphical layer distorts, arranges, damages,
or stylizes it.

Each emitted line is tagged with an opcode class (4 bits, in a parallel
buffer). The graphics layer maps class to carving style:

| Class             | Carving style                         |
|-------------------|---------------------------------------|
| compressed        | shallow scratches                     |
| load / store      | flowing, water-like grooves           |
| branch / jump     | deeper, more deliberate strokes       |
| arithmetic        | clean parallel lines                  |
| system / ecall    | glowing or cracked                    |
| atomic            | spiral, rune-like                     |
| float             | curved, organic                       |
| vector            | wide, banner-like                     |
| unknown / fallback| broken, eroded                        |

Possible cave-wall transformations: irregular spacing, broken lines,
faded characters, text following wall contours, glowing firelight
modulation, partial erosion of instruction text, mixing decoded
instructions with fallback `.word` fragments, carving depth based on
opcode class or instruction frequency.

This keeps the disassembler itself clean and reusable. The graphics layer
makes its own decisions; smold just gives it ground truth.

## 11. Dispatch strategy

### 11.1 No central dispatch table

This is the single highest-leverage size decision in the whole design.

A central pointer table referencing every decoder is tempting but
catastrophic for size:

```
decode_table:
    .quad decode_addi
    .quad decode_slti
    .quad decode_xori
    .quad decode_vector_op
    .quad decode_atomic
```

The table is rodata bytes (8 bytes per entry on RV64) plus one relocation
per entry in the unlinked object. Worse, `ld --gc-sections` cannot see
through a function pointer table the way it sees through direct calls.
Every decoder named in the table is kept alive whether the demo reaches
it or not.

### 11.2 Preferred embedded pattern

Use direct dispatch in a `switch`-style cascade:

```
decode32:
    inspect opcode
    branch only to enabled family decoders
    otherwise fallback .4byte
```

This cascade compiles to a sequence of `auipc + jalr` calls that are
visible to `--gc-sections`. Decoders not referenced from the cascade get
dropped at link time. Adding a decoder is a new branch in the cascade,
not a new table entry.

Feature capsules are referenced only when their enabling macro is set,
and the macro is set only by the build's feature selection (see §12).

### 11.3 Development build exception

For the full development tool, where total size is less critical, a
denser table-driven approach may be acceptable. The architectural rule
is that the *embedded* build uses cascade dispatch; the *development*
build may use whatever is convenient.

### 11.4 ABI for atoms

Each atom is a function or a table. Atoms call each other using the
standard RISC-V LP64D calling convention, with one project-specific
tightening:

- Emitter atoms take `struct smold_out *` as the first argument (a0).
- Emitter atoms return `int` (a0) — either `SMOLD_OK` or one of
  `SMOLD_ERR_*`.
- Callers check `bnez a0, ...` to short-circuit on overflow.
- Atoms clobber only caller-saved registers (t0–t6, a0–a7), and save
  any callee-saved registers (s0–s11) they need.
- No floating-point registers. The decoder never needs FP, and FP
  use would force callers to save FP state across decoder calls.

This convention means atoms compose cleanly, tail calls work, and the
walker can call a dispatched decoder without setup overhead beyond the
normal call sequence.

## 12. Coverage-driven decoder growth

The decoder grows based on actual binaries, not theoretical full-ISA
coverage.

The development tool scans a final linked executable and produces a
report like:

```
Instruction families present:
RV64I:
    addi   83
    lui    12
    jal    21
    beq    18
RVC:
    c.addi 141
    c.sdsp 38
    c.ldsp 37
M:
    mul    4
Unsupported:
    opcode 0x5b / funct3 0x2: 2 occurrences
```

This report guides which embedded decode atoms are needed.

### 12.1 Feedback mechanism: generated undefined-symbol pulls

The coverage report drives the embedded build via a generated `.S` file
containing undefined symbol references. The embedded link includes this
generated file as input. Each undefined symbol forces the linker to
include the corresponding atom; atoms that nothing references are
dropped.

Example generated file:

```
# Auto-generated by smold --feature-pull from binary analysis.
# Forces the linker to include atoms required by the analyzed binary.
.section .smold.required, "a"
.globl _smold_features_pull
_smold_features_pull:
    .quad decode_addi
    .quad decode_lui_auipc
    .quad decode_jal_jalr
    .quad decode_c_addi
    .quad decode_c_sdsp
    # ...
```

The `.quad <symbol>` references force the linker to keep the named
atoms reachable. `--gc-sections` drops everything else.

This mechanism is preferred over `#ifdef` gating in the source because:

- it requires no edits to the decoder source
- it composes naturally with `--gc-sections`
- the same source builds for any feature set; the difference is in the
  generated pull file
- it works for assembly-only atoms, where `#ifdef` is awkward

Eventually SMOLR emits a required-disassembler-feature set directly,
making this fully automatic.

## 13. Interaction with SMOLR — smold as the byte-classification brain

SMOLR represents code and data as atoms with relocations and alignment.
smold reads those atoms after linking and classifies every byte.

A possible internal atom model SMOLR maintains:

```
atom:
    kind: code | data | rodata | metadata
    bytes
    exported symbols
    imported symbols
    relocation records
    alignment
    flags
    compression hints
```

smold's role is to answer questions about the *post-link* byte stream that
SMOLR's atom model alone cannot:

- Which bytes are instructions vs. embedded constants?
- For an instruction byte: which family, which class, which size?
- For a data byte: is it likely a float? An address? A jump table entry?
- What is the call graph reachable from the entry point?

### 13.1 SMOLR transforms that need smold's classification

- **Call transform (SMOLR §11.6).** Needs to identify every internal call
  instruction. Cannot work without instruction-level classification.
- **Code/data split (SMOLR §11.5).** Needs to know which byte ranges are
  code and which are data, more precisely than ELF section headers say.
- **Float-constant transform** (future, akin to Crinkler's TRUNCATEFLOATS).
  Needs heuristics on which 32-bit and 64-bit chunks of `.rodata` are
  floats. The label-name heuristic Crinkler uses is fragile; smold's
  surrounding-instruction context is stronger evidence.
- **Jump-table coalescing** (future). Needs to identify which `.rodata`
  ranges are jump tables and which are pure data.

The pattern: SMOLR knows what each atom *is supposed to be*; smold
verifies what each byte *actually is*. Disagreements between them are
where bugs hide.

### 13.2 Output: byte_classification_report

smold's M4 coverage reporter produces a byte-classification report
alongside the instruction coverage report. Schema (tentative):

```
range_start range_end class confidence detail
0x1000      0x1024    code  high       rv64i.op_imm
0x1024      0x1028    code  high       rvc.c_addi
0x1028      0x102c    code  high       rvc.c_jr
0x102c      0x1030    data  medium     float32_constant
...
```

SMOLR consumes this to drive its transforms. Confidence levels exist
because smold's classification of `.rodata` ranges is heuristic.

### 13.3 Possible SMOLR report consumed in return

```
Required embedded disassembler atoms:
    disasm_core
    disasm_rv64i.decode_op_imm
    disasm_rv64i.decode_load
    disasm_rv64i.decode_store
    disasm_rvc.decode_c_addi
    disasm_rvc.decode_c_ldsp_sdsp
    disasm_ext_m.decode_muldiv
```

This becomes the input to the §12.1 feature-pull file.

### 13.4 Why structural metadata helps compression

smold's value to a future SMOLR packer is not tokenisation in the NLP
sense. The value lies in improving probability models by exposing
executable structure to the context-model compressor.

A 12-bit immediate field of a load instruction wants a different
probability model than the surrounding opcode bytes, which want a
different model than the UTF-8 text of an embedded string constant. A
naïve context model treats all bytes as the same kind of input; one
informed by smold's classification can switch models per region.

Concrete example: in a region tagged `code/rv64i.op_imm`, the high
nibble of every fourth byte is opcode bits — strongly predictable from
neighbours. The low 12 bits are signed immediates — much less
predictable, but with a known statistical shape (small values dominate).
A context model that knows this can compress both regions better than
one that doesn't.

This is one concrete payoff for the byte-classification work described
in §13.2 above, beyond just helping the call transform and code/data
split.

### 13.5 Atom-graph verification

smold can also verify SMOLR's reachability assumptions after the link.
Possible checks:

- Detect unreachable retained atoms (SMOLR kept something `--gc-sections`
  should have dropped — a bug in atom-graph emission).
- Detect unexpected dependencies (atom A references atom B but the
  design said it shouldn't — a bug in source organisation).
- Verify pruning assumptions (the demo declared "I use only X, Y, Z"
  but the linked binary contains W — find the call chain that retained
  W).
- Detect accidental retention via relocation graphs (a function-pointer
  table kept five decoders alive — exactly the dispatch-table hazard
  §11.1 warns about; smold can prove it happened).

This is what makes smold a self-test for SMOLR: same source classifying
the same bytes, run after every link, giving immediate feedback when
atom discipline silently slips.

## 14. Linker / section strategy for assembly

For handwritten assembly, section-per-function:

```
.macro FUNC name
    .section .text.\name, "ax", @progbits
    .globl  \name
    .type   \name, @function
    .balign 2
\name:
.endm

.macro ENDFUNC name
    .size \name, .-\name
.endm
```

Feature-specific strings in separate rodata sections:

```
.section .rodata.disasm.str_c_addi, "a", @progbits
str_c_addi:
    .ascii "c.addi\0"
```

Very small strings may be better grouped by family:

```
.rodata.disasm.rv64i_strings
.rodata.disasm.rvc_strings
.rodata.disasm.m_strings
```

This is the discipline used in the M1 implementation; see `src/core.S`
and `src/asm-macros.h`.

## 15. Code/data separation and ranges

The embedded disassembler preferably disassembles known executable ranges
rather than blindly scanning the entire loaded image. A loaded executable
may contain code, constants, jump tables, literal data, string data,
packed resources, and alignment padding. Disassembling all bytes can
produce nonsense.

That nonsense may be artistically useful later, but the first version
walks clean code ranges.

Recommended first target: `.text` only.

Possible later target: `.text` plus selected rodata fragments,
intentionally rendered as mysterious false-code carvings. This is also
where SMOLR's byte classification (§13) becomes load-bearing — it tells
smold which rodata to attempt to disassemble.

## 16. Instruction length detection

RISC-V instruction length is the first essential primitive. The first
embedded version handles only 16-bit and 32-bit instructions.

Rule (from the RISC-V manual §1.5):

- low2 != 11 → 16-bit compressed
- low2 == 11 and bits[4:2] != 111 → 32-bit standard
- otherwise → 48-bit or longer (M1 does not handle)

Implementation in `smold_insn_length`:

```
andi  t0, a0, 3
li    t1, 3
bne   t0, t1, .Lcompressed
andi  t0, a0, 0x1c
li    t1, 0x1c
beq   t0, t1, .Llong
li    a0, 4
ret
```

Longer encodings are not needed for the initial SMOLR / demo target unless
deliberately introduced. M1 reports them as `SMOLD_ERR_UNSUPPORTED_LEN`.

## 17. Unknown instruction policy

Unknown instructions must not stop the disassembler.

### 17.1 Two kinds of unknown

The coverage reporter and the embedded fallback both treat unknown
instructions as "emit raw bytes, keep walking," but the reporter
distinguishes two cases that matter for tooling:

- **Unsupported instruction.** Valid encoding, but the corresponding
  decoder atom is not linked into this build. Action: add the atom if
  the demo will actually exercise this code path. This is a TODO for the
  decoder, not a bug.
- **Invalid instruction.** Illegal or unrecognised bit pattern. Action:
  investigate. On a SMOLR-built binary, an invalid instruction in the
  reachable code range is a SMOLR emission bug. On a third-party binary
  it may be data wrongly tagged as code, or a hardware-extension
  encoding we should learn about.

The embedded build does not need this distinction at runtime — both
become `.2byte`/`.4byte` lines. The dev-tool coverage reporter does, and
labels each unknown accordingly.

### 17.2 Emission policy

Policy:

- unknown 16-bit: emit `.2byte 0xhhhh`
- unknown 32-bit: emit `.4byte 0xwwwwwwww`
- continue scanning at the next instruction boundary

Byte order in `0xhhhh` and `0xwwwwwwww` is little-endian — the natural
read order on RISC-V. This matches every other RISC-V disassembler and
avoids surprising users.

This policy makes the embedded version robust even when decoder coverage
is incomplete.

## 18. Size targets

Approximate size targets for handwritten RV64 assembly, assuming RVC
density of 2–3 bytes per instruction:

- Fallback-only walker: 1–2 KiB
- Minimal useful embedded disassembler: 2–5 KiB
- Practical embedded disassembler for a real demo subset: 4–8 KiB
- Broader embedded disassembler with several extensions: 8–16 KiB
- Full development disassembler: tens of KiB; size less critical

Planning targets, not guarantees. Actual size depends on output formatting
richness, number of instruction families, string storage, register-name
strategy, table use, alignment, compressed instruction density, linker
relaxation, and SMOLR's atom pruning effectiveness.

## 19. Public API

```c
int smold_walk_range(const void *bytes, size_t nbytes,
                     uint64_t pc_base,
                     struct smold_out *out);

int smold_insn_length(uint32_t h);
int smold_emit_dot_halfword(uint16_t h, struct smold_out *out);
int smold_emit_dot_word(uint32_t w, struct smold_out *out);
int smold_emit_pc_label(uint64_t pc, struct smold_out *out);
```

`struct smold_out` is a `(buf, cap, len, needed)` tuple. Passing `cap == 0`
with `buf == NULL` is legal: the walker counts bytes into `needed`
without storing anything and never returns overflow. This lets a caller
size the buffer in a first pass.

Return codes: `SMOLD_OK`, `SMOLD_ERR_OUT_OVERFLOW`,
`SMOLD_ERR_TRUNCATED_INSN`, `SMOLD_ERR_UNSUPPORTED_LEN`,
`SMOLD_ERR_BAD_ARGS`.

## 20. Milestones

### M0: Design

This document.

### M1: Fallback walker — done

The smallest useful first step: walk a memory range, detect 16-bit vs
32-bit instructions, emit `.2byte 0xhhhh` / `.4byte 0xwwwwwwww` lines.
No mnemonics yet, but this proves the infrastructure works and is
already useful as a "show me the bytes" tool.

Delivered:

- `src/core.S` — eleven atoms in RV64 assembly
- `include/smold.h` — public C contract
- `cli/smold-cli.c` — CLI with `--bytes file`, `--bytes -`, `--elf file`
- `tests/test_core.c` — runtime unit tests
- `tests/test_layout.c` — compile-time struct-layout assertions
- Makefile auto-detecting native vs cross builds

### M2: Minimal RV64I decode

Common 32-bit instructions: `lui`, `auipc`, `jal`, `jalr`, branches,
loads, stores, `addi`, basic integer register-register ops.

### M3: Essential RVC decode

Common compressed instructions: `c.addi`, `c.li`, `c.lui`, `c.mv`,
`c.add`, `c.ldsp`, `c.sdsp`, `c.lwsp`, `c.swsp`, `c.ld`, `c.sd`, `c.lw`,
`c.sw`, `c.j`, `c.jr`, `c.jalr`, `c.beqz`, `c.bnez`.

### M4: Coverage reporter

External tool mode that scans a binary and reports decoded instructions,
unknown instructions, instruction family counts, required decoder atoms,
and byte classification per §13.

### M5: SMOLR integration

Use the coverage report (or SMOLR's own atom knowledge) to select embedded
disassembler atoms via the §12.1 feature-pull mechanism.

### M6: Cave-wall integration

Use the output buffer (with parallel opcode-class buffer) as graphics
input: texture source, carving mask, wall inscription stream, glyph-depth
source, firelight modulation input.

### M7: Optional extension growth

Add only the extensions actually present in final binaries: M, A, B
subset, F/D subset, V subset, CSR numeric decode, Zfa/Zicond as needed.

## 21. Open design questions (resolved or rephrased)

Original open questions, with current positions:

1. **Should the embedded disassembler print addresses, or only instruction
   text?** Configurable. M1 always prints; embedded use may skip the PC
   prefix when graphics doesn't need it.
2. **Decimal, hex, or both for immediates?** Hex by default. Decimal as
   an optional pretty-print atom.
3. **Branch targets: absolute, relative, or omitted?** Configurable per
   caller. M2 emits relative offsets; pretty-print atom adds resolved
   absolute targets.
4. **Cave wall: compact or visually varied?** Visually varied. The
   opcode-class side-channel buffer (§10.3) is the mechanism.
5. **`.text` only or also data?** `.text` only for M1–M6. Selected data
   ranges become a Phase 7+ option once SMOLR's classification feeds in.
6. **How does SMOLR describe instruction families?** Through the
   feature-pull file mechanism in §12.1.
7. **Automatic, manual, or both for instruction-family selection?**
   Both. Manual override always wins; automatic from coverage report
   is the default.
8. **Smallest register formatter that still looks good?** Numeric
   `x0`..`x31` is the M1 baseline. Two characters per register, no
   table needed.
9. **ABI register names in the development tool only?** Yes. Embedded
   build never includes them.
10. **Unknown instruction byte order?** Little-endian, matching the
    native RISC-V read order. Resolved.

## 22. Design doctrine

The disassembler follows the same discipline as the rest of ENO: build a
large library of tiny atoms, compose only the atoms needed for the piece.

For the embedded demo version: correct enough, tiny, graceful fallback,
visually useful.

For the development version: broad enough to inspect SMOLR output and
guide size reduction, and *byte-classification-complete* enough to feed
SMOLR's transform passes.

The full disassembler is a tool. The embedded disassembler is both a tool
and an instrument.

In the cave scene, the executable becomes archaeology: the machine reads
its own bones and writes them on stone.

## 23. Test corpus

smold is tested against three corpora plus one cross-tool differential
check.

### 23.1 Synthetic torture binary

A hand-built RV64 ELF that contains exactly one instance of every
supported instruction encoding. Used as the M2+ regression baseline:
every decoder produces its expected mnemonic for its target encoding,
and nothing else.

The torture binary is generated, not hand-written — a Python script
emits a `.S` file with `.4byte`/`.2byte` directives for every encoding,
plus a small wrapper so the resulting ELF can be loaded but never
actually executed.

### 23.2 SMOLR survey corpus

The Phase 1 SMOLR relocation-survey ELFs (`tools/smolr/build/survey/`)
serve as a secondary test corpus. They exercise realistic call patterns,
dynamic linking metadata, and relaxation outcomes.

### 23.3 Real demo binaries

Once ENO has its first production-size demo, that binary is the third
corpus. The acceptance criterion is that smold can walk its `.text` from
start to end without hitting an unknown encoding (after the relevant
extension capsules are linked in) and without false-positive
classification of data as code.

### 23.4 Differential validation against external tools

The dev-tool build of smold supports differential comparison against
`objdump` and `llvm-objdump`. The workflow:

```
assemble corpus
    ↓
disassemble with smold       disassemble with objdump
    ↓                            ↓
reassemble smold output      reassemble objdump output
    ↓                            ↓
compare resulting bytes  ←——————┘
```

Differences should be explainable by intentionally lossy formatting
choices (e.g. smold decodes `addi x0,x0,0` as itself rather than `nop`,
per §1.1, so a `nop`-aware reassembler may produce identical bytes from
both forms but textual diff is non-zero).

This is important because the embedded build and the dev-tool build
share decode atoms. A bug in a decoder shows up identically in both
modes, so catching it on the dev side is catching it everywhere.

## 24. M1 retrospective

Notes from implementing M1 that informed this design:

- **Count-only mode is its own thing.** Treating `cap == 0` as count-only
  mode (rather than as overflow) lets callers size buffers in one pass
  through the same code path. The first M1 draft conflated this with
  overflow and short-circuited the walker; fixed before commit.
- **Alignment must be validated on both pointer and length.** The walker
  reads halfwords and words; an odd starting pointer crashes on
  alignment-strict cores. M1 validates both.
- **Struct-layout drift between C and asm is real.** `tests/test_layout.c`
  uses `static_assert` on every field offset and the struct size. This
  is cheap insurance and caught nothing in M1 only because we caught
  the offsets right the first time.
- **Section-per-function discipline costs nothing at write time but
  pays at link time.** The `FUNC`/`ENDFUNC` macros mean every atom is
  individually droppable; M1 has 11 atoms, of which the CLI only needs
  some (e.g. it does not call `smold_emit_hex_u16` directly), and
  `--gc-sections` cleans up.
- **Cross-build under qemu-user is fast enough.** Iteration on a laptop
  with `qemu-riscv64` is sub-second per test cycle. The "develop on
  laptop, deploy to board" model works.

These observations inform M2 onward: same discipline, same testing
pattern, same struct-layout assertion mechanism, same count-only
semantics through the new atoms.
