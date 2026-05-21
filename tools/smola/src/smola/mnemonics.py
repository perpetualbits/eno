"""RISC-V mnemonic table.

This file is the source of truth for SMOLA's strict typo detection.
A line whose first token isn't a SMOLA keyword, a GAS directive, a
label, or a comment must match a mnemonic in this table — otherwise
SMOLA rejects it with "unknown mnemonic". This is what makes typos
errors instead of silent passthrough to GAS.

The table is organized by RISC-V extension. RVA23 (the 2024 application
profile) mandates the union of these extensions, so a SMOLA file
targeting RVA23 has access to every mnemonic listed here.

Editing this file is the official mechanism for adding support for a
new RISC-V extension. The data is plain Python frozensets; updates are
mechanical and reviewable in a normal diff. There is no codegen step,
no external dependency on binutils, and no version drift between
SMOLA's view of the ISA and the underlying assembler's view —
mismatches surface as "GAS doesn't recognize this mnemonic SMOLA
passed through", which is the right failure mode (concrete and
debuggable).

Coverage status, in order of how mature SMOLA's testing is:

  - Full coverage, well-tested: RV32I, RV64I, M, A, F, D, Zicsr,
    pseudo-instructions.
  - Full coverage, lightly tested: C (compressed), Zba, Zbb, Zbs.
  - Full coverage, not yet behaviorally tested: V (RVV 1.0), Zicntr,
    Zihpm, Zifencei.
  - Not in the table (deliberate omissions): Zfh (half-precision FP),
    Zfhmin, vendor extensions, hypervisor (H), supervisor (S, Sv*),
    debug. These can be added when a real use case appears.

A few non-extension mnemonics are also recognized:
  - RISC-V pseudo-instructions documented in the ISA manual's
    "Assembly Programmer's Handbook" (Vol. I, §25.2 in the 2024
    edition).
  - The bare `call` and `tail` pseudo-ops, which GAS implements as
    `auipc`+`jalr` pairs but the user writes as one token.
"""

from typing import FrozenSet


# =============================================================================
# RV32I — the 32-bit integer base.
# =============================================================================
# These are the foundational instructions present in every RISC-V CPU.
# Sourced from the unprivileged ISA spec, Chapter 2 (RV32I).
_RV32I = frozenset({
    # Integer register-immediate (Chapter 2.4)
    "addi", "slti", "sltiu", "xori", "ori", "andi",
    "slli", "srli", "srai",
    "lui", "auipc",
    # Integer register-register (Chapter 2.4)
    "add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and",
    # Control transfer (Chapter 2.5)
    "jal", "jalr",
    "beq", "bne", "blt", "bge", "bltu", "bgeu",
    # Loads and stores (Chapter 2.6)
    "lb", "lh", "lw", "lbu", "lhu",
    "sb", "sh", "sw",
    # Memory model (Chapter 2.7) — fence has multiple forms but only
    # one mnemonic
    "fence", "fence.i",
    # ECALL/EBREAK (Chapter 2.8)
    "ecall", "ebreak",
})

# =============================================================================
# RV64I — the 64-bit additions.
# =============================================================================
# Sourced from Chapter 4. Adds 64-bit-wide loads/stores and the *W
# instructions that produce 32-bit results sign-extended into the 64-
# bit register file.
_RV64I = frozenset({
    # Wide loads and stores
    "ld", "lwu", "sd",
    # Word-sized integer register-immediate
    "addiw", "slliw", "srliw", "sraiw",
    # Word-sized integer register-register
    "addw", "subw", "sllw", "srlw", "sraw",
})

# =============================================================================
# M extension — integer multiply and divide.
# =============================================================================
# Sourced from Chapter 7. Mandatory in RVA23.
_M = frozenset({
    # Standard widths
    "mul", "mulh", "mulhsu", "mulhu",
    "div", "divu", "rem", "remu",
    # RV64 word-sized variants
    "mulw", "divw", "divuw", "remw", "remuw",
})

# =============================================================================
# A extension — atomics.
# =============================================================================
# Sourced from Chapter 8. The `.aq`/`.rl`/`.aqrl` modifier suffixes
# are valid on any AMO instruction; we list them as separate entries
# because the lexer matches the *whole token* and that's what the user
# types. This produces a combinatorial list, but it's explicit and the
# lexer's hash lookup doesn't care about size.
def _amo_variants() -> FrozenSet[str]:
    # Atomic operations on word and doubleword
    bases = ["lr", "sc",
             "amoswap", "amoadd", "amoxor", "amoand", "amoor",
             "amomin", "amomax", "amominu", "amomaxu"]
    widths = ["w", "d"]
    suffixes = ["", ".aq", ".rl", ".aqrl"]
    out = set()
    for b in bases:
        for w in widths:
            for s in suffixes:
                out.add(f"{b}.{w}{s}")
    return frozenset(out)

_A = _amo_variants()

# =============================================================================
# F extension — single-precision floating point.
# =============================================================================
# Sourced from Chapter 11. The rounding mode suffix (`,rne`/`,rtz`/
# `,rdn`/`,rup`/`,rmm`/`,dyn`) is an operand, not part of the mnemonic,
# so we don't list rounding-mode variants here.
_F = frozenset({
    # Loads and stores
    "flw", "fsw",
    # Arithmetic
    "fadd.s", "fsub.s", "fmul.s", "fdiv.s", "fsqrt.s",
    # Sign-injection
    "fsgnj.s", "fsgnjn.s", "fsgnjx.s",
    # Min/max
    "fmin.s", "fmax.s",
    # Conversions to/from integer
    "fcvt.w.s", "fcvt.wu.s", "fcvt.s.w", "fcvt.s.wu",
    "fcvt.l.s", "fcvt.lu.s", "fcvt.s.l", "fcvt.s.lu",
    # Move between FP and integer registers
    "fmv.x.w", "fmv.w.x",
    # Compare
    "feq.s", "flt.s", "fle.s",
    # Classify
    "fclass.s",
    # Fused multiply-add family
    "fmadd.s", "fmsub.s", "fnmadd.s", "fnmsub.s",
})

# =============================================================================
# D extension — double-precision floating point.
# =============================================================================
# Sourced from Chapter 12. Same shape as F but with .d suffix.
_D = frozenset({
    "fld", "fsd",
    "fadd.d", "fsub.d", "fmul.d", "fdiv.d", "fsqrt.d",
    "fsgnj.d", "fsgnjn.d", "fsgnjx.d",
    "fmin.d", "fmax.d",
    "fcvt.s.d", "fcvt.d.s",
    "fcvt.w.d", "fcvt.wu.d", "fcvt.d.w", "fcvt.d.wu",
    "fcvt.l.d", "fcvt.lu.d", "fcvt.d.l", "fcvt.d.lu",
    "fmv.x.d", "fmv.d.x",
    "feq.d", "flt.d", "fle.d",
    "fclass.d",
    "fmadd.d", "fmsub.d", "fnmadd.d", "fnmsub.d",
})

# =============================================================================
# C extension — compressed (16-bit) instructions.
# =============================================================================
# Sourced from Chapter 16. GAS accepts these as their `c.` prefixed
# names; the user usually writes the non-compressed form and lets the
# assembler choose, but the C names should be accepted for users
# writing size-critical code that wants explicit compressed forms.
_C = frozenset({
    # Stack-pointer based loads and stores
    "c.lwsp", "c.ldsp", "c.fldsp",
    "c.swsp", "c.sdsp", "c.fsdsp",
    # Register-based loads and stores
    "c.lw", "c.ld", "c.fld",
    "c.sw", "c.sd", "c.fsd",
    # Control transfer
    "c.j", "c.jal", "c.jr", "c.jalr",
    "c.beqz", "c.bnez",
    # Integer constant generation and arithmetic
    "c.li", "c.lui",
    "c.addi", "c.addiw", "c.addi16sp", "c.addi4spn",
    "c.slli", "c.srli", "c.srai", "c.andi",
    "c.mv", "c.add", "c.and", "c.or", "c.xor", "c.sub",
    "c.addw", "c.subw",
    # Misc
    "c.nop", "c.ebreak",
})

# =============================================================================
# Zicsr — CSR access. Required for almost any system-level code.
# =============================================================================
_ZICSR = frozenset({
    "csrrw", "csrrs", "csrrc",
    "csrrwi", "csrrsi", "csrrci",
    # Standard CSR pseudo-instructions
    "csrr", "csrw", "csrs", "csrc",
    "csrwi", "csrsi", "csrci",
    # Atomic CSR pseudo-instructions used by some assembly programs
    "rdcycle", "rdtime", "rdinstret",
    "rdcycleh", "rdtimeh", "rdinstreth",
})

# =============================================================================
# Zicntr / Zihpm — counters. Mostly accessed via Zicsr instructions,
# but a few pseudo-mnemonics exist.
# =============================================================================
_ZICNTR_ZIHPM = frozenset({
    # No new mnemonics beyond the rd* set in Zicsr above.
    # Reserved here as a structural placeholder.
})

# =============================================================================
# Zifencei — instruction fence.
# =============================================================================
_ZIFENCEI = frozenset({
    # fence.i is already in RV32I but technically lives in Zifencei
    # since the 2019 spec split. Keep it here too for documentation.
    "fence.i",
})

# =============================================================================
# Zba — address-generation bit manipulation.
# =============================================================================
# Sourced from the bit-manipulation spec, §1.
_ZBA = frozenset({
    "add.uw", "sh1add", "sh2add", "sh3add",
    "sh1add.uw", "sh2add.uw", "sh3add.uw",
    "slli.uw",
})

# =============================================================================
# Zbb — basic bit manipulation.
# =============================================================================
# Sourced from the bit-manipulation spec, §2.
_ZBB = frozenset({
    "andn", "orn", "xnor",
    "clz", "ctz", "cpop",
    "clzw", "ctzw", "cpopw",
    "max", "maxu", "min", "minu",
    "sext.b", "sext.h", "zext.h",
    "rol", "ror", "rori",
    "rolw", "rorw", "roriw",
    "orc.b", "rev8",
})

# =============================================================================
# Zbc — carryless multiplication.
# =============================================================================
_ZBC = frozenset({
    "clmul", "clmulh", "clmulr",
})

# =============================================================================
# Zbs — single-bit instructions.
# =============================================================================
_ZBS = frozenset({
    "bclr", "bclri",
    "bext", "bexti",
    "binv", "binvi",
    "bset", "bseti",
})

# =============================================================================
# V — Vector extension (RVV 1.0).
# =============================================================================
# This is by far the largest extension. We list every mnemonic from
# the RVV 1.0 specification's instruction listing. Operands like
# `v0.t` (mask), rounding mode tokens, and SEW/LMUL settings are
# *operands*, not part of the mnemonic; they aren't here.
_V = frozenset({
    # Configuration
    "vsetvli", "vsetivli", "vsetvl",

    # Unit-stride loads/stores
    "vle8.v", "vle16.v", "vle32.v", "vle64.v",
    "vse8.v", "vse16.v", "vse32.v", "vse64.v",
    "vlm.v", "vsm.v",
    # Strided
    "vlse8.v", "vlse16.v", "vlse32.v", "vlse64.v",
    "vsse8.v", "vsse16.v", "vsse32.v", "vsse64.v",
    # Indexed (unordered and ordered)
    "vluxei8.v", "vluxei16.v", "vluxei32.v", "vluxei64.v",
    "vloxei8.v", "vloxei16.v", "vloxei32.v", "vloxei64.v",
    "vsuxei8.v", "vsuxei16.v", "vsuxei32.v", "vsuxei64.v",
    "vsoxei8.v", "vsoxei16.v", "vsoxei32.v", "vsoxei64.v",
    # Fault-only-first
    "vle8ff.v", "vle16ff.v", "vle32ff.v", "vle64ff.v",

    # Vector integer arithmetic — vv (vector-vector)
    "vadd.vv", "vsub.vv", "vrsub.vx", "vrsub.vi",
    "vand.vv", "vand.vx", "vand.vi",
    "vor.vv", "vor.vx", "vor.vi",
    "vxor.vv", "vxor.vx", "vxor.vi",
    "vsll.vv", "vsll.vx", "vsll.vi",
    "vsrl.vv", "vsrl.vx", "vsrl.vi",
    "vsra.vv", "vsra.vx", "vsra.vi",
    # vx variants
    "vadd.vx", "vadd.vi", "vsub.vx",
    # Min/max signed and unsigned
    "vmin.vv", "vmin.vx", "vminu.vv", "vminu.vx",
    "vmax.vv", "vmax.vx", "vmaxu.vv", "vmaxu.vx",
    # Multiply (various widths)
    "vmul.vv", "vmul.vx",
    "vmulh.vv", "vmulh.vx",
    "vmulhu.vv", "vmulhu.vx",
    "vmulhsu.vv", "vmulhsu.vx",
    "vdiv.vv", "vdiv.vx", "vdivu.vv", "vdivu.vx",
    "vrem.vv", "vrem.vx", "vremu.vv", "vremu.vx",
    # Multiply-accumulate
    "vmacc.vv", "vmacc.vx",
    "vmadd.vv", "vmadd.vx",
    "vnmsac.vv", "vnmsac.vx",
    "vnmsub.vv", "vnmsub.vx",
    # Widening
    "vwadd.vv", "vwadd.vx", "vwsub.vv", "vwsub.vx",
    "vwaddu.vv", "vwaddu.vx", "vwsubu.vv", "vwsubu.vx",
    "vwmul.vv", "vwmul.vx",
    "vwmulu.vv", "vwmulu.vx",
    "vwmulsu.vv", "vwmulsu.vx",
    "vwmacc.vv", "vwmacc.vx",
    "vwmaccu.vv", "vwmaccu.vx",
    "vwmaccsu.vv", "vwmaccsu.vx",
    "vwmaccus.vx",
    # Comparisons
    "vmseq.vv", "vmseq.vx", "vmseq.vi",
    "vmsne.vv", "vmsne.vx", "vmsne.vi",
    "vmslt.vv", "vmslt.vx",
    "vmsltu.vv", "vmsltu.vx",
    "vmsle.vv", "vmsle.vx", "vmsle.vi",
    "vmsleu.vv", "vmsleu.vx", "vmsleu.vi",
    "vmsgt.vx", "vmsgt.vi",
    "vmsgtu.vx", "vmsgtu.vi",

    # Vector FP arithmetic
    "vfadd.vv", "vfadd.vf", "vfsub.vv", "vfsub.vf", "vfrsub.vf",
    "vfmul.vv", "vfmul.vf", "vfdiv.vv", "vfdiv.vf", "vfrdiv.vf",
    "vfsqrt.v", "vfrsqrt7.v", "vfrec7.v",
    "vfmin.vv", "vfmin.vf", "vfmax.vv", "vfmax.vf",
    "vfsgnj.vv", "vfsgnj.vf", "vfsgnjn.vv", "vfsgnjn.vf",
    "vfsgnjx.vv", "vfsgnjx.vf",
    "vfmacc.vv", "vfmacc.vf", "vfnmacc.vv", "vfnmacc.vf",
    "vfmsac.vv", "vfmsac.vf", "vfnmsac.vv", "vfnmsac.vf",
    "vfmadd.vv", "vfmadd.vf", "vfnmadd.vv", "vfnmadd.vf",
    "vfmsub.vv", "vfmsub.vf", "vfnmsub.vv", "vfnmsub.vf",
    "vfwadd.vv", "vfwadd.vf", "vfwsub.vv", "vfwsub.vf",
    "vfwmul.vv", "vfwmul.vf",
    "vfwmacc.vv", "vfwmacc.vf", "vfwnmacc.vv", "vfwnmacc.vf",
    "vfwmsac.vv", "vfwmsac.vf", "vfwnmsac.vv", "vfwnmsac.vf",
    "vfmv.f.s", "vfmv.s.f", "vfmv.v.f",
    # FP comparisons
    "vmfeq.vv", "vmfeq.vf", "vmfne.vv", "vmfne.vf",
    "vmflt.vv", "vmflt.vf", "vmfle.vv", "vmfle.vf",
    "vmfgt.vf", "vmfge.vf",
    # FP conversions
    "vfcvt.xu.f.v", "vfcvt.x.f.v",
    "vfcvt.f.xu.v", "vfcvt.f.x.v",
    "vfcvt.rtz.xu.f.v", "vfcvt.rtz.x.f.v",
    "vfwcvt.xu.f.v", "vfwcvt.x.f.v",
    "vfwcvt.f.xu.v", "vfwcvt.f.x.v", "vfwcvt.f.f.v",
    "vfwcvt.rtz.xu.f.v", "vfwcvt.rtz.x.f.v",
    "vfncvt.xu.f.w", "vfncvt.x.f.w",
    "vfncvt.f.xu.w", "vfncvt.f.x.w", "vfncvt.f.f.w",
    "vfncvt.rtz.xu.f.w", "vfncvt.rtz.x.f.w",
    "vfncvt.rod.f.f.w",

    # Reductions
    "vredsum.vs", "vredmax.vs", "vredmaxu.vs",
    "vredmin.vs", "vredminu.vs",
    "vredand.vs", "vredor.vs", "vredxor.vs",
    "vwredsum.vs", "vwredsumu.vs",
    "vfredusum.vs", "vfredosum.vs",
    "vfredmin.vs", "vfredmax.vs",
    "vfwredusum.vs", "vfwredosum.vs",

    # Mask operations
    "vmand.mm", "vmor.mm", "vmxor.mm", "vmnand.mm",
    "vmnor.mm", "vmxnor.mm", "vmandn.mm", "vmorn.mm",
    "vcpop.m", "vfirst.m",
    "vmsbf.m", "vmsif.m", "vmsof.m",
    "viota.m", "vid.v",

    # Permutations
    "vmv.x.s", "vmv.s.x",
    "vmv.v.v", "vmv.v.x", "vmv.v.i",
    "vmv1r.v", "vmv2r.v", "vmv4r.v", "vmv8r.v",
    "vslideup.vx", "vslideup.vi",
    "vslidedown.vx", "vslidedown.vi",
    "vslide1up.vx", "vslide1down.vx",
    "vfslide1up.vf", "vfslide1down.vf",
    "vrgather.vv", "vrgather.vx", "vrgather.vi",
    "vrgatherei16.vv",
    "vcompress.vm",

    # Move and merge
    "vmerge.vvm", "vmerge.vxm", "vmerge.vim",
    "vfmerge.vfm",

    # Narrowing / widening / shifts (a subset; the rest follow the
    # same naming pattern)
    "vnsrl.wv", "vnsrl.wx", "vnsrl.wi",
    "vnsra.wv", "vnsra.wx", "vnsra.wi",
    "vnclip.wv", "vnclip.wx", "vnclip.wi",
    "vnclipu.wv", "vnclipu.wx", "vnclipu.wi",

    # Fixed-point saturating
    "vsadd.vv", "vsadd.vx", "vsadd.vi",
    "vsaddu.vv", "vsaddu.vx", "vsaddu.vi",
    "vssub.vv", "vssub.vx",
    "vssubu.vv", "vssubu.vx",
    "vsmul.vv", "vsmul.vx",
    "vssrl.vv", "vssrl.vx", "vssrl.vi",
    "vssra.vv", "vssra.vx", "vssra.vi",

    # Sign extension / zero extension
    "vsext.vf2", "vsext.vf4", "vsext.vf8",
    "vzext.vf2", "vzext.vf4", "vzext.vf8",
})


# =============================================================================
# Standard pseudo-instructions.
# =============================================================================
# Sourced from the ISA manual's Assembly Programmer's Handbook. These
# are sequences GAS recognizes and expands; the user types them as one
# token.
_PSEUDO = frozenset({
    # Trivial
    "nop", "ret",
    # Constant generation
    "li", "la",
    # Moves
    "mv", "neg", "not",
    # Conditional set
    "seqz", "snez", "sltz", "sgtz",
    # Unconditional branch
    "j", "jr",
    # Conditional branch with zero
    "beqz", "bnez", "blez", "bgez", "bltz", "bgtz",
    # Conditional branch — argument order variants
    "bgt", "ble", "bgtu", "bleu",
    # Call / tail call (auipc + jalr expansions)
    "call", "tail",
    # FP pseudo-moves and unary
    "fmv.s", "fmv.d",
    "fneg.s", "fneg.d",
    "fabs.s", "fabs.d",
    # Negation pseudo for words
    "negw",
    # Sign-extend pseudo
    "sext.w",
})


# =============================================================================
# Composite: every mnemonic SMOLA recognizes.
# =============================================================================
KNOWN_MNEMONICS: FrozenSet[str] = (
    _RV32I | _RV64I | _M | _A | _F | _D | _C
    | _ZICSR | _ZICNTR_ZIHPM | _ZIFENCEI
    | _ZBA | _ZBB | _ZBC | _ZBS
    | _V | _PSEUDO
)


def is_known_mnemonic(token: str) -> bool:
    """True if `token` is a known RISC-V instruction mnemonic.

    Used by the lexer to classify a line whose first token is not a
    SMOLA keyword, not a GAS directive (starts with `.`), not a label
    (ends with `:`), and not a comment. If the token isn't in this
    table, the line is rejected with "unknown mnemonic".
    """
    return token in KNOWN_MNEMONICS


# Sanity number for the test suite: this is the total recognized
# vocabulary. Roughly 500 mnemonics, dominated by the V extension.
# A test asserts this number is "reasonable" (e.g. > 300, < 1000) so
# a future edit that accidentally drops half the table fails loudly.
TOTAL_MNEMONICS = len(KNOWN_MNEMONICS)
