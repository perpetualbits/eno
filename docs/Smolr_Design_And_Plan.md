# SMOLR: A RISC-V-Native Minsize Linker and Runtime Import System

## Status

Design document v2. Phase 0 (setup) and Phase 1 scripts complete; Phase 1
data collection pending Jupiter board availability.

## Project identity

**SMOLR** is a RISC-V-native sizecoding linker and runtime import system for
tiny Linux demos. The name is allowed to stay slightly ridiculous. Demoscene
tools benefit from a gremlin-shaped silhouette.

SMOLR lives at `tools/smolr/` inside the ENO monorepo. It is the linker side
of a two-tool pair with `tools/smold/`, the byte-level disassembler that
provides instruction classification and acts as SMOLR's debugging companion
and self-test.

## 1. Purpose

SMOLR exists to make extremely small dynamically linked Linux executables for
RISC-V. The first serious target is not general application packaging — it
is demoscene output:

- tiny graphical/audio/text demos
- dynamically linked against system libraries
- built for RVA22 or RVA23 Linux on the ENO board fleet
- optionally compressed afterward
- with strict control over bytes

It is inspired by SMOL, UPX, Crinkler, and dnload, but is not a port of any
of them. RISC-V has its own instruction encoding, linker relaxation behavior,
compressed instructions, relocation pairs, and ABI details. SMOLR exploits
those deliberately.

## 2. Design philosophy

### 2.1 Build the smallest useful thing first

Do not start with a complete linker. Start with one RISC-V64 Linux ELF
executable, handmade and minimized, dynamically resolving and calling one
external libc function. Everything else follows from that.

### 2.2 Linker first, compressor second

UPX compresses an already-linked executable. SMOL-like tools reduce the
executable before compression by avoiding normal dynamic-linking metadata
overhead. SMOLR is therefore structured as three layers:

1. Minsize linker and runtime import system
2. RISC-V code-shaping layer (atom discipline, RVC density, relaxation)
3. Optional compression / packer layer

Compression matters, but it should not hide bad linking structure. First
make the ELF and imports tiny. Then compress.

### 2.3 RISC-V-native, not x86-in-RISC-V clothing

A direct SMOL port would drag along x86 assumptions: NASM syntax, x86
PLT/GOT patterns, x86 relocation types, x86 dynamic-loader shortcuts, x86
code-size habits.

SMOLR uses RISC-V's own strengths instead:

- RVC compressed instructions and Zcb where available
- `auipc`/`jalr` call patterns
- linker relaxation (`R_RISCV_RELAX`)
- compact register choices for compressibility
- LP64D ABI conventions
- scalar bitmanip where it shrinks code
- careful PC-relative data access

### 2.4 Atom discipline as a first-class principle

Both SMOLR (the linker) and smold (the disassembler) treat code and data as
collections of small, independently-removable atoms. An atom is one
function, one small table, one optional formatter, or one feature capsule.

The same discipline that lets smold ship only the decoders a specific demo
uses lets SMOLR drop unreachable code through `--gc-sections` before its
own packing starts. The atom is the natural unit at every layer.

### 2.5 Correctness before size heroics

The first version may be larger than ideal. That is acceptable. Milestone
order:

1. Runnable
2. Correct
3. Reproducible
4. Measured
5. Smaller
6. Smaller still

The first working resolver can be boring. The second can be sharp. The
third can start stealing spoons from the byte cupboard.

## 3. Target platform

### 3.1 Architecture tiers

SMOLR supports three tiers, matching ENO's hardware fleet:

| Tier | ISA string            | Real silicon                  | Role                  |
|------|-----------------------|-------------------------------|-----------------------|
| 0    | `rv64gc`              | Milk-V Duo S (T-Head C906)    | Bootstrap, future bare-metal mode |
| 1    | `rv64gc_zba_zbb_zbs`  | Milk-V Mars / Jupiter (K1)    | Daily development     |
| 2    | `rva23u64`            | Future SpacemiT K3 board      | Showcase, primary release |

Tier 1 is the daily-driver target. Tier 2 is the showcase target where
SMOLR demonstrates its size wins. Tier 0 keeps us honest about ISA
assumptions and may matter again if SMOLR grows a bare-metal mode for the
Duo S.

Note that the Duo S's C906 reports `rv64imafdcv` but its V is RVV 0.7.1
(not the ratified RVV 1.0) and it has no Zba/Zbb/Zbs. SMOLR treats it as
Tier 0 only — strictly `rv64gc`.

The Jupiter/Mars X60 cores have a known caveat: their hardware does not
support misaligned access for vector instructions, so they are not strictly
RVA22-compliant. Code generated for Tier 1 must avoid relying on Zicclsm.

### 3.2 OS and toolchain

- OS: Linux (Ubuntu, Debian, Bianbu)
- libc: glibc first (musl deferred)
- Binary type: dynamically linked ELF64
- ABI: LP64D
- Toolchain: GCC or LLVM with explicit profile support
- Test runtime: `qemu-riscv64` on x86 development hosts, native on the boards

### 3.3 Non-goals (phase 1)

Explicitly out of scope:

- RV32, musl, static linking
- C++, exceptions, RTTI, constructors/destructors
- TLS, external global data symbols
- IFUNC, copy relocations
- Cairo/Pango complete demos (smoke tests only)
- arbitrary third-party binaries

SMOLR is not a general packer. It is a precision tool for tiny controlled
programs.

## 4. Quick RISC-V control-flow primer

This section exists because SMOLR must be relaxation-aware.

### 4.1 jal

```
jal rd, target
```

Effect: `rd = pc + 4; pc = pc + signed_offset`. PC-relative, limited range.
`jal x0, target` and the `j target` pseudo-instruction are unconditional
jumps. `jal ra, target` is the normal direct call.

### 4.2 jalr

```
jalr rd, imm(rs1)
```

Effect: `target = (rs1 + sign_extend(imm12)) & ~1; rd = pc + 4; pc = target`.
`ret` is `jalr x0, 0(ra)`. `jr rs1` is `jalr x0, 0(rs1)`. Useful when the
destination lives in a register, such as a resolved import slot.

### 4.3 auipc

```
auipc rd, imm20
```

Effect: `rd = pc_of_auipc + sign_extend(imm20 << 12)`. Writes a PC-relative
address base into `rd`. Does not change `pc`. The low 12 bits of `rd` are
inherited from the instruction's PC, not zeroed.

### 4.4 auipc + jalr — the long-range call

When `jal`'s range is insufficient the assembler emits:

```
auipc ra, %pcrel_hi(target)
jalr  ra, %pcrel_lo(target)(ra)
```

If the linker later determines the target is reachable, this can be relaxed
to a single `jal ra, target`.

### 4.5 Linker relaxation

The linker replaces conservative longer instruction sequences with shorter
equivalent ones once final addresses are known. Calls, branches, address
computations, and some loads can all shrink.

### 4.6 SMOLR's relaxation rule

SMOLR does not fight relaxation. The rule: emit normal relocation-marked
RISC-V sequences first, let the linker relax them, then measure and
optimize. Hand-patching byte offsets too early breaks `R_RISCV_RELAX`
records.

## 5. What SMOLR does better than UPX

UPX compresses a normal executable after it has already been linked. SMOLR
reduces the executable before compression by avoiding or replacing bulky
ELF and dynamic-linking structures.

SMOLR focuses on:

- tiny ELF headers
- minimal program headers
- compact dynamic table
- compact DT_NEEDED list
- compact imported-symbol table
- runtime symbol resolution
- tiny import stubs
- RVC-friendly runtime code
- linker-relaxation-aware layout
- optional cooperation with a later packer

UPX remains useful as baseline, fallback, post-link packer, and
benchmark target. SMOLR should make a much smaller input for any later
packer.

## 6. What SMOLR does better than SMOL

Existing SMOL is x86/x86_64. SMOLR is RISC-V-native. Advantages over a
direct port:

- cleaner GNU assembler backend
- RV64GC-and-up first ABI design
- RVC-aware register allocation in runtime code
- relaxation-aware call/data-access sequences
- atom discipline from day one (single-section-per-function for gc)
- benchmark matrix including `ld`, UPX, SMOLR, and SMOLR + packer
- no inherited NASM structure
- clearer separation between linker, runtime resolver, and compression

The decision to fold SMOLR back into SMOL as a backend or keep it
standalone is deferred until after a working RV64GC proof of concept.

## 7. Core architecture

### 7.1 Build pipeline

```
input objects/libs
        ↓
SMOLR scanner
        ↓
relocation and import analysis
        ↓
minimal ELF layout planner
        ↓
RISC-V runtime/import stub generator
        ↓
GNU ld or custom layout link step
        ↓
optional section reordering pass for compressibility
        ↓
optional code/data split and call transform
        ↓
optional packer/compressor
        ↓
final tiny executable
```

### 7.2 Major components

**A. Frontend scanner.** Inspect input ELF objects, verify RV64GC+/LP64D
compatibility, gather undefined global function symbols, gather relocation
types, reject unsupported features clearly, identify required shared
libraries, build import list.

**B. Library/symbol resolver at build time.** Search compiler/library paths,
identify matching RISC-V ELF shared libraries, inspect exported symbols,
map each needed symbol to a library, construct DT_NEEDED order, detect
ambiguous definitions.

**C. ELF layout planner.** Construct minimal ELF64 header, program headers,
loadable segments, dynamic table. Decide RX/RW split or single RWX segment.
Place runtime resolver, import table, user code, user data.

**D. RISC-V runtime resolver.** Locate dynamic linker state, walk loaded
shared libraries, locate symbol/string/hash tables, find imported symbols,
write resolved addresses into the SMOLR import table, transfer control to
user `_start`.

**E. RISC-V import stubs.** For each imported function, provide a callable
symbol. Tentative shape:

```
.globl puts
puts:
    auipc t0, %pcrel_hi(_smolr_sym_puts)
    ld    t0, %pcrel_lo(.Lputs_sym)(t0)
    jr    t0
```

Exact syntax must be validated with GNU `as` and binutils.

**F. Optional post-link transforms.** Section reordering, code/data split,
call transform. These are size-shaping passes that run after the core link
but before any compressor. See §11.5–§11.7.

**G. Optional packer interface.** Feed the final transformed output into
UPX or a custom packer, measure size before/after, support reproducible
benchmark tables.

## 8. Import symbol representation

SMOLR does not carry full dynamic symbol names in the normal ELF way unless
needed. Three import-table designs, in increasing sophistication:

### 8.1 Phase 3: debug-friendly table

```
struct smolr_import {
    uint32_t hash;
    uint16_t lib_index;
    uint16_t flags;
    uint64_t resolved_address;
}
```

Larger, but easy to debug. Used during initial bring-up.

### 8.2 Phase 4: compact hash-address overlay

```
_imports:
    .quad hash(puts)
    .quad hash(write)
    .quad hash(cairo_create)
    .quad 0
```

At runtime, the resolver overwrites each hash slot with the actual resolved
address. 8 bytes per import.

### 8.3 Phase 3.5 / Phase 6: free-hash imports

This is the Crinkler TINYIMPORT insight ported to RISC-V. The idea is to
not store hashes at all. Instead the import table's slot index *is* the
hash. The call site encodes which slot to use, and the slot's value (once
filled in) is the resolved function address.

Concretely, for each imported symbol with hash `h`:

- the symbol goes into slot `h mod table_size`
- the import stub for that symbol references slot `h mod table_size`
- the call site uses that stub

The hash entropy is paid for in the call instruction's immediate, which we
were going to spend anyway. The hash table itself stores only resolved
addresses — no hash codes.

The build-time linker chooses a `(hash_function, table_size)` pair that
yields no collisions for the specific import set. This is search work that
SMOLR does once at build time.

Cost: an `auipc + ld + jr` stub per import is unchanged in size, but the
hash-table storage shrinks by the hash field per entry (4 bytes if we were
using a 32-bit hash). For 20-import demos this saves 80 bytes outright.

Phase 3.5 is the right milestone for this — between "one dynamic call" and
"multiple imports across multiple libraries." See §16.

## 9. Hash strategy

Candidate hash functions for Phase 3:

- DJB2, simple and small
- BSD-style 16-bit hash, smaller but more collisions
- GNU hash reuse, possibly avoids custom hash but increases runtime complexity

Initial recommendation: DJB2. Simple, portable, familiar from SMOL-like
tools, good enough for initial symbol lists.

For Phase 3.5 (free-hash imports per §8.3), the hash function is chosen at
build time from a parameter family. DJB2 with a variable seed is a good
starting point; the linker searches seeds until it finds one that hashes
all required symbols to distinct slots in a chosen table size.

Later experiments to revisit:

- 16-bit hash with collision fallback
- per-library sorted symbol hashes
- direct name comparison for very small import sets
- perfect hash generated at build time for known imports

## 10. Relocation support

### 10.1 Initial supported input

Support only external function calls generated by controlled compiler
flags. Expected first relocation family:

- `R_RISCV_CALL_PLT`
- `R_RISCV_CALL`
- associated `R_RISCV_RELAX`

The exact list is confirmed empirically by the Phase 1 relocation survey
(see `tools/smolr/survey/`). Confirmed via:

```
riscv64-linux-gnu-readelf -rW file.o
riscv64-linux-gnu-objdump -dr file.o
```

### 10.2 Unsupported at first

Reject cleanly:

- TLS relocations
- external data objects
- complex GOT data references
- IFUNC
- copy relocations
- C++ exception/unwind machinery
- constructors/destructors

Error messages should teach the user what compiler flag or source change
caused the problem. Example:

```
error: external data symbol 'errno' requires unsupported RISC-V GOT/data
relocation.
try avoiding libc errno access or use raw syscalls for this path.
```

## 11. RISC-V code-size and performance strategy

### 11.0 Optimization policy

SMOLR optimizes for the profile actually desired:

- Tier 1 (Jupiter K1) first
- Tier 2 (RVA23 / K3) second
- Tier 0 (generic RV64GC) for portability tests only

The runtime resolver may remain scalar where scalar code is smaller, but
generated demo code, decompression filters, byte shufflers, hash scanners,
and transform kernels may use vector and bitmanip instructions where
profitable.

Avoid false economies: saving 30 bytes in the resolver is pointless if it
prevents using RVA22+ features that save hundreds of bytes or many
milliseconds elsewhere.

### 11.1 Use RVC and Zcb deliberately

Runtime resolver and stubs are written with compressed-instruction density
in mind. Guidelines:

- Prefer registers that compress well (`a0`..`a5`, `s0`..`s1`, `t0`..`t2`)
- Prefer `sp`-relative saves/loads with compressible offsets
- Use `c.li`, `c.mv`, `c.addi`, `c.ldsp`, `c.sdsp`, `c.jr`, `c.j`, `c.beqz`,
  `c.bnez` where the assembler can emit them
- Prefer Zcb forms when they replace 32-bit load/extend/multiply sequences
- Keep small hot loops within short branch ranges
- Avoid wide temporaries unless they save more elsewhere

### 11.2 Use scalar bitmanip where it shrinks code

Tier 1+ includes scalar bit manipulation. Test whether bitmanip reduces
code size in:

- symbol hashing
- string scanning
- byte/word packing
- decompressor loops
- bitmap/A8 mask processing
- import table scanning
- small checksum/hash functions
- branchless bit tricks

Useful families: Zbb (rotates, clz/ctz, popcount, byte-reversal), Zba
(address generation), Zbs (single-bit), Zbc (carryless multiply for CRC).

Measure each kernel. Bitmanip is not a universal win.

### 11.3 Use RVV where it wins at system level

RVV is wrong for tiny call glue. It is right for data-parallel kernels:

- decompression filters
- RISC-V instruction-stream preprocessing before compression
- byte shuffling
- fast symbol-name / hash scanning if the resolver becomes large
- A8 alpha mask transforms
- text surface post-processing
- wavelet / chirplet / quadrature kernels
- audio block processing
- particle / state updates
- SPINE event expansion

Design rule: scalar/RVC for tiny control glue, RVV for data-parallel
kernels.

Important RVV design notes:

- VLEN is implementation-defined; code must be vector-length agnostic
  unless a benchmark deliberately targets a known board
- Use `vsetvli` / `vsetivli` cleanly
- Keep vector kernels separately measurable

### 11.4 Let relaxation work

Test both `-mrelax` and `-mno-relax`. A correct SMOLR works with either.
A best-size SMOLR normally prefers relaxation enabled.

### 11.5 Code/data split for compression

The Crinkler insight: code and data have very different statistical
distributions, so compressing them together is wasteful. SMOLR should be
prepared to emit code and data into separate compression streams when a
custom packer wants them.

This implies:

- the layout planner tags each section as code/data/rodata
- the optional packer interface accepts separated streams
- atom-level granularity gives the planner the information it needs

Even without a custom packer, splitting into clean RX/RW segments improves
UPX's later work and keeps NX-compatible options open.

### 11.6 Call transform

Another Crinkler trick worth porting. On RISC-V, calls to the same target
from different sites produce different byte sequences because the
PC-relative offsets differ. A context-modeling compressor — or even LZ77 —
benefits when those sequences become identical.

The transform: rewrite every internal call into a canonical form whose
encoding depends only on the target, not on the call site's address. A
small detransformation stub (~30 bytes estimated) at startup converts back
to runnable form before user code runs.

Two viable canonical forms on RISC-V:

1. Replace `jal ra, target` with `call abs_target_offset_from_text_base`
   represented as a known fixed-width sequence whose immediate is
   independent of PC.
2. Replace direct calls with table-indexed dispatch through a tiny
   thunk table.

Option 1 is closer to what Crinkler does on x86. Option 2 is uglier but
composes naturally with the free-hash import scheme in §8.3.

This is Phase 6 or Phase 8 work, depending on whether we measure the win
before or after a custom packer is in scope.

### 11.7 Section-reordering search hook

The order in which atoms appear in the final binary materially affects
compression ratio. Crinkler searches up to 100,000 orderings. SMOLR should
expose the ordering as a permutation that can be searched over when a
compressor is in the pipeline.

Implementation: the layout planner produces an atom list with constraints
(entry point first, alignment requirements, segment boundaries) and a
permutation function. A driver script can iterate orderings and pick the
smallest compressed result.

This is cheap to design now (just expose the permutation) and lets
compression-time search land in Phase 8 without re-architecting.

### 11.8 RISC-V structural advantages

Things SMOLR gets for free that Crinkler cannot have:

- **Linker relaxation.** `R_RISCV_RELAX` lets the linker shrink calls and
  address computations after final layout. x86 has no equivalent.
- **RVC compressed instructions.** Roughly 30–50% size reduction on
  appropriately-written code with no compression layer involved.
- **Atom discipline via `--gc-sections`.** RISC-V toolchain conventions
  make section-per-function natural. PE/COFF tools have to do their own
  dead-code analysis.
- **Cleaner ELF metadata than PE.** ELF's mandatory overhead is smaller
  than PE's even before any header hackery.

These advantages compound: a SMOLR dynamic ELF before compression should
already be competitive with a Crinkler-compressed PE.

### 11.9 Measure actual emitted bytes

Never trust source-level instruction counts. Required tooling:

```
riscv64-linux-gnu-objdump -dr final.elf
riscv64-linux-gnu-readelf -h -l -d -r -s final.elf
wc -c final.elf
```

The build emits a size report:

```
headers:       N bytes
runtime:       N bytes
import table:  N bytes
stubs:         N bytes
user text:     N bytes
user rodata:   N bytes
packed total:  N bytes
```

The smold disassembler is a natural source of this classification —
see §20.

## 12. ELF design

### 12.1 Header goals

SMOLR generates the minimum ELF64/RISC-V program accepted by Linux and the
dynamic loader. Required areas:

- ELF header
- program headers
- at least one PT_LOAD
- PT_DYNAMIC
- possibly PT_INTERP
- dynamic entries for needed libraries
- string table for library names
- runtime code and import table

### 12.2 RISC-V ELF flags

The generated ELF header must use valid RISC-V `e_flags`, especially
ABI-related flags for LP64D. The Phase 1 survey will record exact values
emitted by the toolchain for each tier.

### 12.3 Section headers

Final executable does not need section headers. Goal: `e_shoff = 0`,
`e_shnum = 0`, `e_shstrndx = 0`. If tools complain but Linux runs it, that
is acceptable for release builds. Debug builds may keep sections.

### 12.4 NX policy

Two modes:

1. Unsafe / minimal single RWX load segment
2. Safer split RX/RW load segments

Demoscene competition rules and runtime environment decide which mode is
acceptable. SMOLR supports both; phase 1 may start with the easier one.

## 13. Runtime resolver design

### 13.1 Correctness-first resolver

First resolver is readable and robust, even if not smallest.

```
_smolr_start:
    save original sp if needed
    find link_map root
    for each import hash:
        for each loaded library in DT_NEEDED order:
            find dynamic section
            find STRTAB, SYMTAB, GNU_HASH or SYSV HASH
            search exported symbols
            if hash matches:
                resolved = l_addr + st_value
                write resolved address into import slot
                break
    set a0 or sp contract for user _start
    jump to user _start
```

### 13.2 Link-map access strategies

Candidate strategies:

1. Use DT_DEBUG if available
2. Use startup / dynamic-linker state assumptions
3. Use an existing dnload-like approach

Start with the most understandable strategy, even if larger. Add smaller
glibc-specific shortcuts after tests pass.

### 13.3 IFUNC

Not supported in Phase 1. Add optional IFUNC resolver support later if
common glibc symbols require it.

## 14. External API and user model

### 14.1 Input requirements

User code is compiled with controlled flags. Starting flags:

```
riscv64-linux-gnu-gcc
    -march=rv64gc_zba_zbb_zbs        # or -march=rva23u64 for Tier 2
    -mabi=lp64d
    -Os
    -fno-stack-protector
    -fno-unwind-tables
    -fno-asynchronous-unwind-tables
    -ffunction-sections
    -fdata-sections
    -nostartfiles
    -c demo.c -o demo.o
```

For assembly:

```
riscv64-linux-gnu-as -march=rv64gc_zba_zbb_zbs demo.s -o demo.o
```

### 14.2 User entry point

Require:

```
.section .text.startup._start,"ax"
.globl _start
_start:
    ...
```

SMOLR runtime eventually jumps into user `_start`.

Startup contract (must be documented and tested):

- `a0` = original stack pointer
- `sp` = original or aligned stack pointer, depending on mode

## 15. Benchmark suite

### 15.0 Target variants

Every serious benchmark tests against at least:

- Tier 0: `rv64gc`
- Tier 1: `rv64gc_zba_zbb_zbs` (and `+v` where vector kernels apply)
- Tier 2: `rva23u64`

Benchmarking separates: code size, packed size, runtime speed, startup
overhead, vector-register-use overhead, portability across boards.

### 15.1 Required benchmark programs

1. Raw syscall hello
2. Dynamic `puts` hello
3. Dynamic `write` hello
4. libm function call
5. Minimal framebuffer or SDL/OpenGL/EGL call
6. Cairo image surface creation
7. Cairo A8 text render
8. Cairo plus Pango text render

### 15.2 Comparison matrix

For each benchmark:

- A: normal GNU `ld`, stripped
- B: normal GNU `ld` + UPX `--best`
- C: SMOLR uncompressed
- D: SMOLR + UPX
- E: SMOLR + custom packer (when available)
- F: SMOLR + code/data split + call transform + custom packer

Metrics: final file size, startup success under qemu-riscv64, startup
success on real hardware, number of imports, runtime resolver size, stub
size per import, compressed ratio, reproducibility.

### 15.3 Definition of top in class

SMOLR is top in class if it consistently produces the smallest working
RVA22/RVA23 Linux dynamic executables in the benchmark suite, while
remaining usable enough for real demo development. Claims must be
measurement-based, not vibes-based.

## 16. Work plan

### Phase 0: setup — done

- repository structure inside `tools/smolr/`
- toolchain probe script (`tools/probe-toolchain.sh`)
- size-baseline script (`tools/size-baseline.sh`)
- relocation-survey scaffolding under `survey/`
- Makefile with `probe / survey / report / baseline / clean` targets

### Phase 1: RISC-V profile and relocation survey — scripts ready

Scripts in place; data collection awaits Jupiter board availability.

Tasks:

- run probe on Jupiter, Mars, and a cross host
- run survey on the test corpus (5 tests × 3 tiers × 4 flag combos)
- generate `docs/riscv-relocation-survey.md`
- review supported relocation set with toolchain specialist

Exit: we know exactly which `R_RISCV_*` types SMOLR must handle for the
Phase 3 milestone.

### Phase 2: minimal ELF64/RISC-V executable

Create a handmade RV64 ELF that exits cleanly, no imports. Run under
qemu-riscv64 and on Jupiter.

Exit: a handmade minimal RV64 ELF starts correctly and returns the
expected exit code.

### Phase 3: one imported function

Emit DT_NEEDED for libc, locate dynamic loader structures, locate libc
symbol table, resolve one symbol by hash, write address into import slot,
implement one import stub, call `puts` or `write`.

Exit: SMOLR-built executable prints text using one dynamically resolved
libc symbol. First true proof of life.

### Phase 3.5: free-hash imports

Reorganize the import table so slot index encodes the hash (§8.3).
Build-time linker searches a `(hash_seed, table_size)` pair without
collisions for the import set. Verify size win against Phase 3.

Exit: import table layout finalized for production use.

### Phase 4: multiple imports and libraries

Multiple imported functions, multiple DT_NEEDED entries, deterministic
library order, import-table terminator strategy, error handling for
unresolved symbols, libm test, basic SDL/Cairo smoke test.

Exit: SMOLR resolves multiple symbols across multiple shared libraries.

### Phase 5: SMOLR frontend

Parse input object symbols, parse relocations, find libraries, map imports
to libraries, generate runtime assembly, invoke assembler/linker, produce
final executable, emit size report.

Exit: one command produces a SMOLR executable from a `.o` file.

### Phase 6: RVA23 size and performance optimization pass

- rewrite resolver for RVC/Zcb density
- tune register choices
- shrink import table
- compare hash strategies (with §8.3 baseline)
- compare SYSV vs GNU hash lookup methods
- test linker relaxation outcomes
- remove redundant dynamic entries
- compare single RWX vs split RX/RW
- compare with UPX
- write scalar bitmanip variants of hash/scan/decompressor kernels
- write RVV variants of data-parallel kernels
- benchmark vector-length-agnostic RVV code
- compare Tier 0, Tier 1, and Tier 2 output
- expose section-reordering hook (§11.7)

Exit: SMOLR beats `ld` + UPX on the benchmark suite.

### Phase 7: demo-library stress tests

Cairo A8 surface creation, Cairo text rendering, Pango layout, OpenGL/EGL
minimal context, audio library call, measure import counts and stub
overhead.

Exit: SMOLR is proven useful for realistic ENO/SPINE demo scenarios.

### Phase 8: packer strategy

- test UPX after SMOLR
- inspect whether UPX harms or helps tiny SMOLR binaries
- design RISC-V instruction filter (call transform per §11.6)
- evaluate context-modeling decompressor (Crinkler-style PAQ)
- evaluate LZ-family decompressor for the 64k category
- code/data split for compression (§11.5)
- section-reorder search (§11.7)
- evaluate external decompression tricks where compo rules allow

Exit: final recommended compression path is known for the 4k and 64k
categories.

### Phase 9: recompression workflow

A Crinkler-inspired late-stage feature. The SMOLR output file should
contain enough metadata to be decompressed, retuned (different hash size,
different compression parameters), and recompressed without rerunning the
original link from `.o` files.

This is a workflow feature for size competitions where you are shaving
bytes against a deadline. Designing the output file format with this in
mind from Phase 6 onward costs nothing now and saves a rewrite later.

Exit: a `.smolr` produced six months ago can be re-tuned for compatibility
or compression on a new toolchain without rebuilding from sources.

## 17. Suggested issue tracker

Initial issues, in rough order:

1. Cross-toolchain and qemu test harness — done as Phase 0
2. Document RISC-V relocations emitted by GCC for simple external calls
3. Generate minimal RV64 ELF header accepted by Linux
4. Determine required RISC-V `e_flags` for Tier 1
5. Implement one-symbol runtime resolver prototype
6. Implement RISC-V import stub prototype
7. Print hello through dynamically resolved libc symbol
8. Add free-hash import table
9. Add multiple imported symbols
10. Add multiple libraries
11. Add SMOLR frontend scanner for object relocations
12. Add deterministic size report
13. Add UPX comparison target
14. Add Cairo smoke test
15. Add RVC optimization pass
16. Add linker relaxation audit
17. Expose section-reordering hook
18. Code/data split prototype
19. Call transform prototype
20. Recompression metadata in output format

## 18. Team roles

### Toolchain lead

GCC/binutils/ELF/ABI experience. Comfortable with `readelf` and `objdump`,
understands linker relaxation and relocation records, can debug dynamic
loader weirdness. Owns relocation survey, ELF validity, linker behavior,
architecture decisions.

### Runtime assembly lead

Strong RISC-V assembly, comfortable with ABI rules, can optimize for RVC,
unafraid of startup code. Owns `_smolr_start`, import resolver, import
stubs, size optimization.

### Test/build lead

Good with Make/CMake/Python/shell, qemu/cross-toolchain setup,
reproducible benchmarks, CI discipline. Owns test harness, size reports,
benchmark matrix, regression tests.

A single contributor can cover the first two roles. The third should still
be automated early — byte-count regressions breed in dark corners.

## 19. Risk register

### Risk: Dynamic loader internals differ or change

Mitigation: start with a robust resolver strategy; document glibc version
assumptions; test on multiple distros; keep safer and smaller resolver
modes separate.

### Risk: RISC-V relaxation breaks hand assumptions

Mitigation: preserve relocation records until the linker stage; test with
`-mrelax` and `-mno-relax`; inspect final disassembly with smold; avoid
depending on temporary register side effects after relaxable sequences.

### Risk: UPX is already good enough for 64k

Mitigation: benchmark early; focus SMOLR on 4k or import-heavy cases where
metadata overhead dominates; keep UPX as a post-processing option.

### Risk: Cairo/Pango imports too many symbols

Mitigation: measure import count early; provide direct Cairo-only mode;
consider text rendering as a build-time asset where possible; cache
generated A8 surfaces at runtime.

### Risk: Tool becomes too general

Mitigation: reject features aggressively; optimize for controlled demo
code; keep non-goals visible in the README.

### Risk: Free-hash import scheme exposes ASLR fragility

Mitigation: the scheme depends on the dynamic loader resolving slots
deterministically once at startup. ASLR moves base addresses but not
internal layout. Verify on real boards across multiple kernel versions
before committing.

## 20. Cooperation with smold

SMOLR and smold are designed as companion tools.

**smold gives SMOLR:**

- byte-level disassembly of SMOLR output for inspection and verification
- instruction coverage reports that tell SMOLR which decoder atoms a demo
  needs (for embedded self-disassembly effects)
- byte classification: this 4-byte chunk is code, that 4-byte chunk is
  float data, that other chunk is a jump table

That third item is the load-bearing one. SMOLR's optional transforms
(call transform per §11.6, code/data split per §11.5, future float-constant
truncation, future jump-table coalescing) all need to know what each byte
*is* before they can transform it. smold's M4 coverage reporter already
walks every byte and classifies each instruction. Extending its
classification output to feed SMOLR is incremental work, not a separate
project.

**SMOLR gives smold:**

- known executable ranges (`__text_start`, `__text_end` linker symbols)
  for the cave-wall effect to walk
- a target binary to debug against — the first SMOLR Phase 2 ELF is also
  a smold test corpus entry
- atom-level metadata that smold's coverage reporter consumes to know
  which atoms to flag as required for embedded self-disassembly

**Self-test relationship:** if smold can walk SMOLR's `.text` from start
to end without hitting an unknown encoding or a truncated instruction, the
SMOLR link is structurally sound. A failing walk in a known-good prefix
means SMOLR mis-emitted something. This is a free regression test that
catches a class of subtle link bugs that no other check finds.

## 21. Early commands

Setup commands:

```
sudo apt install
    gcc-riscv64-linux-gnu
    binutils-riscv64-linux-gnu
    qemu-user
    qemu-user-binfmt
    upx-ucl
    make
    python3
```

Inspection commands:

```
riscv64-linux-gnu-readelf -h -l -d -r -sW file.elf
riscv64-linux-gnu-objdump -dr file.elf
wc -c file.elf
qemu-riscv64 -L /usr/riscv64-linux-gnu ./file.elf
```

Or, once Phase 1 lands:

```
make -C tools/smolr probe
make -C tools/smolr survey
make -C tools/smolr report
make -C tools/smolr baseline
```

## 22. Final strategic recommendation

SMOLR did not begin as "port SMOL to RISC-V." It began as a RISC-V-native
proof-of-concept that borrows SMOL's central idea: replace bulky dynamic-
linking metadata with a tiny runtime resolver and compact import table.
It also borrows specific tricks from Crinkler (free-hash imports, call
transform, code/data split, section-reorder search) where they translate
to RISC-V without distortion.

The decision to upstream into SMOL, remain a separate project, or become a
shared backend is deferred until after Phase 4 (multiple imports across
libraries) is working.

The project wins if it produces measured results. The first real victory
is not theoretical elegance. The first real victory is a tiny dynamic ELF
on the Jupiter that prints one line through a dynamically resolved import
and makes `wc -c` look confused.
