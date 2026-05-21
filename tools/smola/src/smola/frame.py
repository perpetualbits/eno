"""SMOLA v0.3 frame planner.

Builds a function prologue and epilogue from:
  - the set of int s-registers claimed via `int.s` / `ptr.s`
  - the set of flt s-registers claimed via `flt.s`
  - whether the body contains any call (so ra must be saved)
  - any `stack <N>` user spill space

Frame layout (high to low; sp grows down):

    +-----------------------+  <- old sp
    | (padding to 16-byte)  |
    | ra                    |  if save_ra
    | int s-regs            |
    | flt s-regs            |
    | user spill area       |
    +-----------------------+  <- new sp

The 16-byte alignment requirement at call sites is part of the
RISC-V Linux ABI. The planner always rounds the frame size up to 16.

Unchanged from v0.2 in algorithm and output.
"""

from dataclasses import dataclass, field
from typing import Dict, List


# Allocation-order lists for sorting save lists. Saving low-numbered
# s-registers at lower stack offsets keeps the prologue readable.
_INT_S_ORDER = ["s0", "s1", "s2", "s3", "s4", "s5",
                "s6", "s7", "s8", "s9", "s10", "s11"]
_FLT_S_ORDER = ["fs0", "fs1", "fs2", "fs3", "fs4", "fs5",
                "fs6", "fs7", "fs8", "fs9", "fs10", "fs11"]


@dataclass
class FramePlan:
    """The full plan: which registers to save, where to put them,
    how big the frame is."""
    save_ra: bool
    saved_int_s: List[str]       # in save order, low offset first
    saved_flt_s: List[str]
    user_spill_bytes: int
    frame_size: int              # total, 16-byte aligned

    ra_offset: int               # -1 if not saved
    int_s_offsets: Dict[str, int] = field(default_factory=dict)
    flt_s_offsets: Dict[str, int] = field(default_factory=dict)


def _round_up(x: int, n: int) -> int:
    """Round x up to next multiple of n."""
    return (x + n - 1) // n * n


def plan_frame(saved_int_s: set, saved_flt_s: set,
               calls_other: bool,
               user_spill_bytes: int = 0) -> FramePlan:
    """Build a FramePlan.

    Inputs:
      - saved_int_s: integer s-registers the body claimed
      - saved_flt_s: float s-registers the body claimed
      - calls_other: True if the body emitted any call/jal/tail (so ra
        is clobbered)
      - user_spill_bytes: extra space from `stack <N>`
    """
    # Sort by canonical pool order for predictable output.
    int_sorted = sorted(
        saved_int_s,
        key=lambda r: _INT_S_ORDER.index(r) if r in _INT_S_ORDER else 999,
    )
    flt_sorted = sorted(
        saved_flt_s,
        key=lambda r: _FLT_S_ORDER.index(r) if r in _FLT_S_ORDER else 999,
    )

    # Layout, from new sp upward:
    #   [user spill] [flt s-regs] [int s-regs] [ra] [padding to 16]
    offset = user_spill_bytes

    flt_offsets: Dict[str, int] = {}
    for r in flt_sorted:
        flt_offsets[r] = offset
        offset += 8

    int_offsets: Dict[str, int] = {}
    for r in int_sorted:
        int_offsets[r] = offset
        offset += 8

    ra_offset = -1
    if calls_other:
        ra_offset = offset
        offset += 8

    frame_size = _round_up(offset, 16)

    return FramePlan(
        save_ra=calls_other,
        saved_int_s=int_sorted,
        saved_flt_s=flt_sorted,
        user_spill_bytes=user_spill_bytes,
        frame_size=frame_size,
        ra_offset=ra_offset,
        int_s_offsets=int_offsets,
        flt_s_offsets=flt_offsets,
    )


def emit_prologue(plan: FramePlan) -> List[str]:
    """Return the prologue lines for a frame plan.

    Empty for leaf functions with no s-claims and no calls."""
    if plan.frame_size == 0:
        return []
    out: List[str] = []
    out.append(
        f"    addi sp, sp, -{plan.frame_size}    "
        f"# smola: prologue, frame={plan.frame_size}"
    )
    if plan.save_ra:
        out.append(
            f"    sd   ra, {plan.ra_offset}(sp)              "
            f"# smola: save ra"
        )
    for r in plan.saved_int_s:
        off = plan.int_s_offsets[r]
        out.append(
            f"    sd   {r}, {off}(sp)              # smola: save {r}"
        )
    for r in plan.saved_flt_s:
        off = plan.flt_s_offsets[r]
        out.append(
            f"    fsd  {r}, {off}(sp)              # smola: save {r}"
        )
    return out


def emit_epilogue(plan: FramePlan) -> List[str]:
    """Return the epilogue lines for a frame plan, ending in `ret`."""
    out: List[str] = []
    if plan.frame_size == 0:
        out.append(
            "    ret                          # smola: leaf epilogue"
        )
        return out
    # Restore in reverse declaration order for symmetric reading.
    for r in reversed(plan.saved_flt_s):
        off = plan.flt_s_offsets[r]
        out.append(
            f"    fld  {r}, {off}(sp)              "
            f"# smola: restore {r}"
        )
    for r in reversed(plan.saved_int_s):
        off = plan.int_s_offsets[r]
        out.append(
            f"    ld   {r}, {off}(sp)              "
            f"# smola: restore {r}"
        )
    if plan.save_ra:
        out.append(
            f"    ld   ra, {plan.ra_offset}(sp)              "
            f"# smola: restore ra"
        )
    out.append(f"    addi sp, sp, {plan.frame_size}     # smola: epilogue")
    out.append("    ret")
    return out
