"""SMOLA register allocator.

Tracks which physical RISC-V register each named binding maps to within
a function. Three pools:

  - T (temporary, caller-saved):   t0 .. t6  (x5..x7, x28..x31)
  - S (saved, callee-saved):       s0 .. s11 (x8..x9, x18..x27)
  - A (argument):                  a0 .. a7  (x10..x17)

The argument pool is special: VAR.A without an explicit register binds
to the next free a-register starting from a0; VAR.A with an explicit
register pins it. Argument bindings are not freeable mid-function in
v1.

The allocator's scope is one function. .smola.func resets it; .smola.endfunc
inspects it (to learn which S-regs need saving) and then discards it.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from .errors import RegAllocError, SourceLoc


class RegKind(Enum):
    T = "T"   # caller-saved temporary
    S = "S"   # callee-saved
    A = "A"   # argument / return


# Allocation order. Lowest-numbered first within each pool. Predictable
# and easy to read in generated output.
_T_REGS = ["t0", "t1", "t2", "t3", "t4", "t5", "t6"]
_S_REGS = ["s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7",
           "s8", "s9", "s10", "s11"]
_A_REGS = ["a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7"]

# Registers that cannot be bound by name in v1.
_RESERVED = {"zero", "ra", "sp", "gp", "tp"}

# All valid x-register aliases for raw-register checking. We accept both
# ABI names and xN names.
_XN_TO_ABI = {
    "x0": "zero", "x1": "ra", "x2": "sp", "x3": "gp", "x4": "tp",
    "x5": "t0", "x6": "t1", "x7": "t2",
    "x8": "s0", "x9": "s1",
    "x10": "a0", "x11": "a1", "x12": "a2", "x13": "a3",
    "x14": "a4", "x15": "a5", "x16": "a6", "x17": "a7",
    "x18": "s2", "x19": "s3", "x20": "s4", "x21": "s5",
    "x22": "s6", "x23": "s7", "x24": "s8", "x25": "s9",
    "x26": "s10", "x27": "s11",
    "x28": "t3", "x29": "t4", "x30": "t5", "x31": "t6",
}


def normalize_reg(name: str) -> Optional[str]:
    """Return the canonical ABI name for a register, or None if not a register."""
    if name in _XN_TO_ABI:
        return _XN_TO_ABI[name]
    if name in _XN_TO_ABI.values():
        return name
    if name in _RESERVED:
        return name
    return None


@dataclass
class Binding:
    name: str
    reg: str               # ABI name, e.g. "t0", "s2", "a1"
    kind: RegKind
    bound_at: Optional[SourceLoc] = None


@dataclass
class Allocator:
    """Per-function register allocator state."""
    free_T: List[str] = field(default_factory=lambda: list(_T_REGS))
    free_S: List[str] = field(default_factory=lambda: list(_S_REGS))
    free_A: List[str] = field(default_factory=lambda: list(_A_REGS))
    bindings: Dict[str, Binding] = field(default_factory=dict)
    saved_S: Set[str] = field(default_factory=set)

    # Names that were freed; used to give a better diagnostic on
    # use-after-free than just "unknown name".
    freed_names: Dict[str, SourceLoc] = field(default_factory=dict)

    def _check_new_name(self, name: str, loc: Optional[SourceLoc]) -> None:
        if name in self.bindings:
            existing = self.bindings[name]
            raise RegAllocError(
                loc,
                f"name {name!r} is already bound to {existing.reg}",
                hint=f"free it first, or pick a different name "
                     f"(previously bound at "
                     f"{existing.bound_at.filename if existing.bound_at else '?'}:"
                     f"{existing.bound_at.line_no if existing.bound_at else '?'})",
            )
        if name in self.freed_names:
            # That is fine; rebinding after FREE is legitimate. Remove
            # the freed record so a subsequent FREE diagnostic is clean.
            self.freed_names.pop(name, None)

    def alloc_T(self, name: str, loc: Optional[SourceLoc] = None) -> str:
        self._check_new_name(name, loc)
        if not self.free_T:
            raise RegAllocError(
                loc,
                "no caller-saved (t) registers available",
                hint=self._pool_state_hint(),
            )
        reg = self.free_T.pop(0)
        self.bindings[name] = Binding(name=name, reg=reg,
                                       kind=RegKind.T, bound_at=loc)
        return reg

    def alloc_S(self, name: str, loc: Optional[SourceLoc] = None) -> str:
        self._check_new_name(name, loc)
        if not self.free_S:
            raise RegAllocError(
                loc,
                "no callee-saved (s) registers available",
                hint=self._pool_state_hint(),
            )
        reg = self.free_S.pop(0)
        self.bindings[name] = Binding(name=name, reg=reg,
                                       kind=RegKind.S, bound_at=loc)
        self.saved_S.add(reg)
        return reg

    def alloc_A(self, name: str, explicit_reg: Optional[str] = None,
                loc: Optional[SourceLoc] = None) -> str:
        self._check_new_name(name, loc)
        if explicit_reg is None:
            if not self.free_A:
                raise RegAllocError(
                    loc,
                    "no argument (a) registers available",
                    hint=self._pool_state_hint(),
                )
            reg = self.free_A.pop(0)
        else:
            canonical = normalize_reg(explicit_reg)
            if canonical is None or not canonical.startswith('a'):
                raise RegAllocError(
                    loc,
                    f"{explicit_reg!r} is not an argument register",
                    hint="argument registers are a0..a7",
                )
            if canonical not in self.free_A:
                # Find who has it.
                holder = None
                for b in self.bindings.values():
                    if b.reg == canonical:
                        holder = b
                        break
                if holder is not None:
                    raise RegAllocError(
                        loc,
                        f"{canonical} is already bound to {holder.name!r}",
                    )
                else:
                    raise RegAllocError(
                        loc,
                        f"{canonical} is not available",
                    )
            self.free_A.remove(canonical)
            reg = canonical
        self.bindings[name] = Binding(name=name, reg=reg,
                                       kind=RegKind.A, bound_at=loc)
        return reg

    def free(self, name: str, loc: Optional[SourceLoc] = None) -> None:
        if name not in self.bindings:
            if name in self.freed_names:
                prior = self.freed_names[name]
                raise RegAllocError(
                    loc,
                    f"{name!r} was already freed at "
                    f"{prior.filename}:{prior.line_no}",
                )
            raise RegAllocError(
                loc,
                f"FREE of unknown name {name!r}",
            )
        b = self.bindings.pop(name)
        # Aliases: if any other name still points to the same reg,
        # do not return the register to the pool.
        still_bound = any(other.reg == b.reg for other in self.bindings.values())
        if not still_bound:
            if b.kind == RegKind.T:
                # Return to T pool in deterministic order.
                self.free_T.append(b.reg)
                self.free_T.sort(key=lambda r: _T_REGS.index(r))
            elif b.kind == RegKind.S:
                # Callee-saved registers stay reserved (we already
                # committed to saving them in the prologue). Returning
                # them to the pool would be incorrect: a later alloc
                # might give the same physical register a different
                # name with overlapping liveness, and the saved-set
                # tracking still treats them as saved -- which is
                # actually fine. But to keep semantics simple, v1
                # does not reuse freed S registers within the same
                # function. They are released for bookkeeping only.
                pass
            elif b.kind == RegKind.A:
                # v1: argument registers are not returned to the pool
                # after FREE either; the ABI fixes their meaning. A
                # FREE on an arg register is for documentation.
                pass
        self.freed_names[name] = loc

    def alias(self, new_name: str, existing_name: str,
              loc: Optional[SourceLoc] = None) -> str:
        """Create a second name for the same physical register."""
        if existing_name not in self.bindings:
            raise RegAllocError(
                loc,
                f"VAR.ALIAS source name {existing_name!r} is not bound",
            )
        self._check_new_name(new_name, loc)
        src = self.bindings[existing_name]
        self.bindings[new_name] = Binding(
            name=new_name, reg=src.reg, kind=src.kind, bound_at=loc,
        )
        return src.reg

    def resolve(self, name: str, loc: Optional[SourceLoc] = None) -> str:
        """Look up the physical register for a name.

        If the name is itself a raw register (xN or ABI), return it
        as-is. This is how 'ADD result, a, t6' works.
        """
        canonical = normalize_reg(name)
        if canonical is not None:
            return canonical
        if name in self.bindings:
            return self.bindings[name].reg
        if name in self.freed_names:
            prior = self.freed_names[name]
            raise RegAllocError(
                loc,
                f"{name!r} was freed at {prior.filename}:{prior.line_no}"
                if prior else f"{name!r} was freed",
            )
        raise RegAllocError(
            loc,
            f"unknown name {name!r}",
            hint="declare it with VAR.T, VAR.S, or VAR.A first",
        )

    def is_bound(self, name: str) -> bool:
        return name in self.bindings

    def _pool_state_hint(self) -> str:
        lines = []
        if self.bindings:
            entries = sorted(self.bindings.values(),
                             key=lambda b: (b.kind.value, b.reg))
            lines.append("currently bound: "
                         + ", ".join(f"{b.name}={b.reg}" for b in entries))
        lines.append(f"free T: {self.free_T}")
        lines.append(f"free S: {self.free_S}")
        lines.append(f"free A: {self.free_A}")
        return "\n      ".join(lines)
