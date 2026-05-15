"""SMOLA frame planner.

Builds a function prologue and epilogue from:
  - the set of s-registers claimed via VAR.S in the body
  - whether the function makes any calls (so ra must be saved)
  - any user-requested raw spill space

The frame layout follows the standard RISC-V LP64D convention with
16-byte stack alignment at call sites.

Frame layout (high address at top, low at bottom — sp grows down):

    +-----------------------+  <- old sp
    | (padding to 16-byte)  |
    | ra                    |  if save_ra
    | s11                   |  if claimed
    | ...                   |
    | s0                    |  if claimed
    | (user spill area)     |  if user_spill_bytes > 0
    +-----------------------+  <- new sp
"""

from dataclasses import dataclass
from typing import List


# Allocation order for saving s-registers: low to high in pool order.
# We store them in the frame in the same order so addresses are
# predictable from a glance at the prologue.
_S_ORDER = ["s0", "s1", "s2", "s3", "s4", "s5",
            "s6", "s7", "s8", "s9", "s10", "s11"]


@dataclass
class FramePlan:
    save_ra: bool
    saved_s_regs: List[str]      # in save order, low frame offset first
    user_spill_bytes: int
    frame_size: int              # total, 16-byte aligned

    # For each saved register, its offset from new sp.
    ra_offset: int
    s_offsets: dict              # reg name -> offset


def _round_up(x: int, n: int) -> int:
    return (x + n - 1) // n * n


def plan_frame(saved_s_regs: set, calls_other: bool,
               user_spill_bytes: int = 0) -> FramePlan:
    """Build a frame plan.

    saved_s_regs: the s-registers that the function body claimed
    calls_other: True if the body contains any call instruction that
                 might clobber ra. v1 assumes True if any CALL or
                 jal-with-rd-ra was emitted; the parser tracks this.
    user_spill_bytes: extra space requested by .smola.stack
    """
    # Sort s-regs by pool order.
    sorted_s = sorted(saved_s_regs,
                      key=lambda r: _S_ORDER.index(r) if r in _S_ORDER else 999)

    # Layout: at offset 0 from new sp lives the user spill area; above
    # that, the s-registers in ascending order; above them, ra; then
    # padding to 16-byte alignment.
    offset = user_spill_bytes
    s_offsets: dict = {}
    for r in sorted_s:
        s_offsets[r] = offset
        offset += 8

    ra_offset = -1
    if calls_other:
        ra_offset = offset
        offset += 8

    frame_size = _round_up(offset, 16)

    return FramePlan(
        save_ra=calls_other,
        saved_s_regs=sorted_s,
        user_spill_bytes=user_spill_bytes,
        frame_size=frame_size,
        ra_offset=ra_offset,
        s_offsets=s_offsets,
    )


def emit_prologue(plan: FramePlan) -> List[str]:
    """Return the prologue lines (without trailing newlines).

    Lines include their own indentation. Provenance comments mark them
    as frame setup.
    """
    if plan.frame_size == 0:
        return []
    lines: List[str] = []
    lines.append(f"    addi sp, sp, -{plan.frame_size}    # smola: prologue, frame={plan.frame_size}")
    if plan.save_ra:
        lines.append(f"    sd   ra, {plan.ra_offset}(sp)              # smola: save ra")
    for r in plan.saved_s_regs:
        off = plan.s_offsets[r]
        lines.append(f"    sd   {r}, {off}(sp)              # smola: save {r}")
    return lines


def emit_epilogue(plan: FramePlan) -> List[str]:
    """Return the epilogue lines, ending in 'ret'."""
    lines: List[str] = []
    if plan.frame_size == 0:
        lines.append("    ret                          # smola: leaf epilogue")
        return lines
    # Restore in reverse order of save for readability symmetry.
    for r in reversed(plan.saved_s_regs):
        off = plan.s_offsets[r]
        lines.append(f"    ld   {r}, {off}(sp)              # smola: restore {r}")
    if plan.save_ra:
        lines.append(f"    ld   ra, {plan.ra_offset}(sp)              # smola: restore ra")
    lines.append(f"    addi sp, sp, {plan.frame_size}     # smola: epilogue")
    lines.append("    ret")
    return lines
