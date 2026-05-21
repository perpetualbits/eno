"""SMOLA v0.3 register allocator.

The central piece of SMOLA. `int counter` works because this module
picks a physical register from the right pool, remembers the binding,
and exposes a `resolve(name)` method that the translator uses to
substitute names with physical register names in the emitted `.s`.

Three orthogonal axes:

  1. Pool (which register file): int/ptr, flt, vec
  2. Storage class (calling-convention role): T (caller-saved /
     temporary), S (callee-saved), A (argument)
  3. Scope (lexical lifetime): function-level scope at depth 1, plus
     any nested `scope` blocks pushed on top

Allocation is round-robin within each (pool, storage) sub-pool: the
lowest-numbered free register comes out first. This is deterministic
and easy to read in generated `.s`.

`zap` (v0.3's rename of v0.2's `_free`) releases a binding:
  - T storage: register returns to the pool, reusable for the next
    declaration.
  - S storage: name released, but the register stays committed to
    the prologue's save list. Reusing it under a different name in
    the same function would emit confusingly-mixed names for one
    saved slot.
  - A storage: name released; the register's ABI position is
    unchanged.

The scope stack lets `endscope` release every binding declared since
the matching `scope` without the user writing a `zap` for each.

Reserved registers (`zero`, `ra`, `sp`, `gp`, `tp`, `v0`) cannot be
bound. v0 is reserved per the RVV mask convention; the rest have
ABI-fixed roles SMOLA doesn't abstract over.

Unchanged from v0.2 in core algorithms; the public method names are
the same. Differences are limited to the storage-class parsing
(v0.3 accepts `int.s` / `int.a` etc. as the user-facing syntax, the
translator splits these into (VarType, Storage) tuples).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from .errors import RegAllocError, SourceLoc


class VarType(Enum):
    """The four logical types. Determines pool selection.

    INT and PTR both use the integer register file; the distinction is
    documentary only. The translator doesn't enforce "you can only do
    pointer arithmetic on ptr" — that's type-checking out of scope for
    v0.3.
    """
    INT = "int"
    PTR = "ptr"
    FLT = "flt"
    VEC = "vec"


class Storage(Enum):
    """Storage class corresponds to the variable's role in the calling
    convention. Drives sub-pool selection, prologue save/restore, and
    free-vs-keep semantics on `zap`."""
    T = "t"   # temporary / caller-saved
    S = "s"   # callee-saved
    A = "a"   # argument


# Pool definitions: immutable tuples giving allocation order. The
# Allocator copies these into mutable lists per-instance so we never
# corrupt the module-level data.

# Integer temporary (7 regs, caller-saved).
_INT_T = ("t0", "t1", "t2", "t3", "t4", "t5", "t6")
# Integer callee-saved (12 regs).
_INT_S = ("s0", "s1", "s2", "s3", "s4", "s5",
          "s6", "s7", "s8", "s9", "s10", "s11")
# Integer arguments / return values (8 regs).
_INT_A = ("a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7")

# FP temporary (12 regs).
_FLT_T = ("ft0", "ft1", "ft2", "ft3", "ft4", "ft5",
          "ft6", "ft7", "ft8", "ft9", "ft10", "ft11")
# FP callee-saved (12 regs).
_FLT_S = ("fs0", "fs1", "fs2", "fs3", "fs4", "fs5",
          "fs6", "fs7", "fs8", "fs9", "fs10", "fs11")
# FP arguments (8 regs, hard-float ABI).
_FLT_A = ("fa0", "fa1", "fa2", "fa3", "fa4", "fa5", "fa6", "fa7")

# Vector temporary: excludes v0 (mask) and v8..v23 (arg range).
_VEC_T = ("v1", "v2", "v3", "v4", "v5", "v6", "v7",
          "v24", "v25", "v26", "v27", "v28", "v29", "v30", "v31")
# Vector arguments per RVV ABI.
_VEC_A = ("v8", "v9", "v10", "v11", "v12", "v13", "v14", "v15",
          "v16", "v17", "v18", "v19", "v20", "v21", "v22", "v23")
# No vector callee-saved pool: the RVV ABI defines none.


# (VarType, Storage) -> immutable pool tuple. Used to look up the
# original allocation order (for re-sorting after a free) and to
# detect "no such pool" combinations.
_POOLS = {
    (VarType.INT, Storage.T): _INT_T,
    (VarType.INT, Storage.S): _INT_S,
    (VarType.INT, Storage.A): _INT_A,
    (VarType.PTR, Storage.T): _INT_T,
    (VarType.PTR, Storage.S): _INT_S,
    (VarType.PTR, Storage.A): _INT_A,
    (VarType.FLT, Storage.T): _FLT_T,
    (VarType.FLT, Storage.S): _FLT_S,
    (VarType.FLT, Storage.A): _FLT_A,
    (VarType.VEC, Storage.T): _VEC_T,
    (VarType.VEC, Storage.A): _VEC_A,
    # (VEC, S) deliberately absent.
}


def _build_register_names() -> Set[str]:
    """Build the set of every register name SMOLA recognizes.

    Includes ABI names, xN/fN/vN numeric aliases, and the `fp` alias
    for s0. Used to reject variable names that look like registers
    and to power the collision detector.
    """
    names: Set[str] = set()
    # Integer xN aliases.
    for i in range(32):
        names.add(f"x{i}")
    # Integer ABI names — explicit so missing ones are obvious in
    # review.
    abis = ["zero", "ra", "sp", "gp", "tp",
            "t0", "t1", "t2", "s0", "s1",
            "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7",
            "s2", "s3", "s4", "s5", "s6", "s7", "s8", "s9", "s10", "s11",
            "t3", "t4", "t5", "t6"]
    names.update(abis)
    # Frame-pointer alias (= s0).
    names.add("fp")
    # Float fN aliases.
    for i in range(32):
        names.add(f"f{i}")
    # Float ABI names.
    for r in _FLT_T + _FLT_S + _FLT_A:
        names.add(r)
    # Vector registers (v0..v31).
    for i in range(32):
        names.add(f"v{i}")
    return names


_ALL_REGISTER_NAMES = _build_register_names()


# Numeric-alias -> ABI canonical name maps. Used by `normalize_reg`
# so `x5`, `t0`, and `fp` all canonicalize to forms the inverse
# binding map (reg_to_name) recognizes.
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
    "fp": "s0",
}

_FN_TO_ABI = {
    "f0": "ft0", "f1": "ft1", "f2": "ft2", "f3": "ft3",
    "f4": "ft4", "f5": "ft5", "f6": "ft6", "f7": "ft7",
    "f8": "fs0", "f9": "fs1",
    "f10": "fa0", "f11": "fa1", "f12": "fa2", "f13": "fa3",
    "f14": "fa4", "f15": "fa5", "f16": "fa6", "f17": "fa7",
    "f18": "fs2", "f19": "fs3", "f20": "fs4", "f21": "fs5",
    "f22": "fs6", "f23": "fs7", "f24": "fs8", "f25": "fs9",
    "f26": "fs10", "f27": "fs11",
    "f28": "ft8", "f29": "ft9", "f30": "ft10", "f31": "ft11",
}


def is_register_name(name: str) -> bool:
    """True if `name` is any form of register name SMOLA knows."""
    return name in _ALL_REGISTER_NAMES


def normalize_reg(name: str) -> Optional[str]:
    """Canonicalize a register to its ABI form, or return None.

    `x5` -> `t0`, `f10` -> `fa0`, `fp` -> `s0`, `t0` -> `t0` (no-op
    for already-canonical), `v2` -> `v2`, anything else -> None.
    """
    if name in _XN_TO_ABI:
        return _XN_TO_ABI[name]
    if name in _FN_TO_ABI:
        return _FN_TO_ABI[name]
    if name in _ALL_REGISTER_NAMES:
        return name
    return None


@dataclass
class Binding:
    """One active variable binding."""
    name: str
    reg: str                # canonical ABI name
    var_type: VarType
    storage: Storage
    scope_depth: int        # which scope frame owns this
    bound_at: Optional[SourceLoc] = None
    # The width the user declared at the binding site, as the literal
    # keyword they typed: "int", "i8", "u8", "i16", "u16", "i32", "u32",
    # "i64", "u64", "ptr", "f32", "f64", "vec". Documentation only —
    # the integer register file is 64-bit on RV64 regardless of the
    # declared sub-word width. The bindings table at the function head
    # uses this string verbatim so the user sees what they wrote.
    #
    # Empty string is allowed for backwards-compat with code paths
    # that construct Bindings without a width (internal temporaries
    # created by float-init synthesis, mostly). Those won't appear in
    # the user-facing bindings table anyway.
    declared_width: str = ""


@dataclass
class ScopeFrame:
    """One scope on the allocator's stack. Records which bindings
    were created within it."""
    depth: int
    names: List[str] = field(default_factory=list)


class Allocator:
    """Multi-pool register allocator for one function.

    One instance per function. Created at `func` time, populated as
    the translator walks the body, queried at `end` time for frame
    planning, then discarded.
    """

    def __init__(self) -> None:
        # Free pools. Lists (mutable) initialized from the module-level
        # immutable tuples.
        self.free_int_T = list(_INT_T)
        self.free_int_S = list(_INT_S)
        self.free_int_A = list(_INT_A)
        self.free_flt_T = list(_FLT_T)
        self.free_flt_S = list(_FLT_S)
        self.free_flt_A = list(_FLT_A)
        self.free_vec_T = list(_VEC_T)
        self.free_vec_A = list(_VEC_A)

        # Active bindings, keyed by name.
        self.bindings: Dict[str, Binding] = {}

        # Tombstones for zapped names — used to give a "X was zapped at
        # <file>:<line>" diagnostic instead of generic "unknown name".
        self.freed_names: Dict[str, SourceLoc] = {}

        # Tracks which S-registers (int and flt) were ever claimed.
        # The frame planner reads these at `end` time.
        self.saved_int_S: Set[str] = set()
        self.saved_flt_S: Set[str] = set()

        # Scope stack. Depth 1 is the function-level scope, pushed
        # here so the translator doesn't need a separate "open function
        # scope" call.
        self.scopes: List[ScopeFrame] = [ScopeFrame(depth=1)]

        # Inverse binding map for collision detection: which physical
        # register is currently held by which variable.
        self.reg_to_name: Dict[str, str] = {}

        # Track every name ever bound in this function (across all
        # scopes, including those that have been zapped). Used by the
        # auto-bindings-table emitter at `end` time to give a complete
        # variable-map comment in the .s output.
        #
        # This separate history exists because once a binding is
        # zapped, it's removed from `bindings`, but we still want the
        # output table to remember it. The translator could maintain
        # its own history, but keeping it in the allocator keeps the
        # data with the source of truth.
        self.history: List[Binding] = []

    # ----- scope management -----

    @property
    def current_depth(self) -> int:
        return self.scopes[-1].depth

    def push_scope(self) -> None:
        """Open a new nested scope. Called by `scope`."""
        self.scopes.append(ScopeFrame(depth=self.current_depth + 1))

    def pop_scope(self,
                   loc: Optional[SourceLoc] = None) -> List[str]:
        """Close the innermost scope, freeing all its bindings.

        Returns freed names so the caller can emit a provenance comment.
        """
        if len(self.scopes) <= 1:
            raise RegAllocError(
                loc,
                "endscope without matching scope",
                hint="the function-level scope cannot be closed manually",
            )
        frame = self.scopes.pop()
        freed = []
        for name in list(frame.names):
            self._free_unchecked(name, loc)
            freed.append(name)
        return freed

    def pop_all_remaining(self,
                           loc: Optional[SourceLoc] = None) -> List[str]:
        """Free everything still live at function end.

        Called by `end`. Errors on unclosed scopes — strict balance
        required.
        """
        if len(self.scopes) != 1:
            raise RegAllocError(
                loc,
                f"function ended with {len(self.scopes) - 1} "
                f"unclosed scope(s)",
                hint="add matching endscope before end",
            )
        frame = self.scopes[0]
        freed = []
        for name in list(frame.names):
            self._free_unchecked(name, loc)
            freed.append(name)
        return freed

    # ----- allocation -----

    def _check_new_name(self, name: str,
                         loc: Optional[SourceLoc]) -> None:
        """Validate that `name` can be used for a new binding."""
        if name in self.bindings:
            existing = self.bindings[name]
            raise RegAllocError(
                loc,
                f"name {name!r} is already bound to {existing.reg}",
                hint=(f"previously bound at "
                      f"{existing.bound_at.filename}:"
                      f"{existing.bound_at.line_no}"
                      if existing.bound_at else None),
            )
        if is_register_name(name):
            # Catches `int t0`, `flt fs1`, etc. — variable name that
            # shadows a register would create ambiguity at use sites.
            raise RegAllocError(
                loc,
                f"cannot use register name {name!r} as a variable name",
                hint="pick a non-register identifier",
            )
        # Clearing the tombstone on rebind so a later zap-of-this-new-
        # binding gets the correct "was zapped at" diagnostic.
        self.freed_names.pop(name, None)

    def alloc(self, name: str, var_type: VarType, storage: Storage,
              loc: Optional[SourceLoc] = None,
              explicit_reg: Optional[str] = None,
              declared_width: str = "") -> str:
        """Allocate a register for a new named binding.

        Public entry. Validates the name, rejects (VEC, S), delegates
        to the pool-pop logic.

        `declared_width` is the literal type keyword the user wrote
        ("int", "u8", "f32", etc.). It's stored on the Binding for
        display in the bindings table; allocation logic doesn't use
        it. Empty string is allowed (e.g. for internal float-init
        transient temporaries that don't appear in the user-facing
        table).
        """
        self._check_new_name(name, loc)

        if var_type == VarType.VEC and storage == Storage.S:
            raise RegAllocError(
                loc,
                "vec variables cannot use callee-saved (s) storage",
                hint=("the standard RVV ABI has no callee-saved "
                      "vector registers"),
            )

        pool_key = (var_type, storage)
        if pool_key not in _POOLS:
            # Defensive: every legitimate combination has a pool.
            raise RegAllocError(
                loc, f"no pool for {var_type.value} {storage.value}",
            )

        pool = self._pool_for(var_type, storage)
        return self._alloc_from_pool(pool, var_type, storage, name, loc,
                                      explicit_reg=explicit_reg,
                                      declared_width=declared_width)

    def _alloc_from_pool(self, pool: List[str], var_type: VarType,
                         storage: Storage, name: str,
                         loc: Optional[SourceLoc],
                         explicit_reg: Optional[str] = None,
                         declared_width: str = "") -> str:
        """Core allocation logic.

        Two paths: implicit round-robin (pop lowest-numbered) or
        explicit pinning (verify the requested register is in the
        right pool and free, then claim it).

        See `alloc` for the role of `declared_width`.
        """
        if explicit_reg is not None:
            # Explicit pinning. Used for `int.a x = a3` and the
            # implicit `self -> a0` for methods.
            canonical = normalize_reg(explicit_reg)
            if canonical is None:
                raise RegAllocError(
                    loc, f"{explicit_reg!r} is not a register name",
                )
            # Order: check "already bound" first (more informative
            # than pool-mismatch).
            if canonical in self.reg_to_name:
                holder = self.reg_to_name[canonical]
                raise RegAllocError(
                    loc,
                    f"{canonical} is already bound to {holder!r}",
                )
            if canonical not in pool:
                # Right syntax form (e.g. `int.a x = ft0`) but wrong
                # pool — ft0 isn't an integer argument register.
                raise RegAllocError(
                    loc,
                    f"{canonical!r} is not in the "
                    f"{var_type.value} {storage.value} pool",
                    hint=f"valid choices: {', '.join(pool)}",
                )
            pool.remove(canonical)
            reg = canonical
        else:
            # Implicit round-robin.
            if not pool:
                raise RegAllocError(
                    loc,
                    f"no {var_type.value} {storage.value} "
                    f"registers available",
                    hint=self._pool_state_hint(),
                )
            # .pop(0) gives lowest-numbered free reg. O(N) shift but
            # N <= 12, negligible.
            reg = pool.pop(0)

        binding = Binding(
            name=name, reg=reg, var_type=var_type, storage=storage,
            scope_depth=self.current_depth, bound_at=loc,
            declared_width=declared_width,
        )
        self.bindings[name] = binding
        self.reg_to_name[reg] = name
        self.scopes[-1].names.append(name)
        # Append to history for the bindings-table emitter. We append
        # *every* allocation, even rebinds, so the bindings table
        # reflects what the user actually wrote.
        self.history.append(binding)

        # Track S-storage claims for the frame planner.
        if storage == Storage.S:
            if var_type in (VarType.INT, VarType.PTR):
                self.saved_int_S.add(reg)
            elif var_type == VarType.FLT:
                self.saved_flt_S.add(reg)
            # (VEC, S) already rejected above.

        return reg

    def _pool_for(self, var_type: VarType,
                   storage: Storage) -> List[str]:
        """Get the live mutable free-list for a (type, storage) pair."""
        m = {
            (VarType.INT, Storage.T): self.free_int_T,
            (VarType.INT, Storage.S): self.free_int_S,
            (VarType.INT, Storage.A): self.free_int_A,
            (VarType.PTR, Storage.T): self.free_int_T,
            (VarType.PTR, Storage.S): self.free_int_S,
            (VarType.PTR, Storage.A): self.free_int_A,
            (VarType.FLT, Storage.T): self.free_flt_T,
            (VarType.FLT, Storage.S): self.free_flt_S,
            (VarType.FLT, Storage.A): self.free_flt_A,
            (VarType.VEC, Storage.T): self.free_vec_T,
            (VarType.VEC, Storage.A): self.free_vec_A,
        }
        return m[(var_type, storage)]

    # ----- freeing -----

    def zap(self, name: str,
             loc: Optional[SourceLoc] = None) -> None:
        """Release a named binding (v0.3 `zap` keyword).

        Public entry. Handles unknown-name and double-zap errors,
        then delegates to _free_unchecked.
        """
        if name not in self.bindings:
            if name in self.freed_names:
                prior = self.freed_names[name]
                raise RegAllocError(
                    loc,
                    f"{name!r} was already zapped at "
                    f"{prior.filename}:{prior.line_no}",
                )
            raise RegAllocError(
                loc, f"zap of unknown name {name!r}",
            )
        # Remove from whichever scope frame owns it. We walk frames to
        # find it (a binding lives in exactly one frame, usually
        # innermost).
        for frame in self.scopes:
            if name in frame.names:
                frame.names.remove(name)
                break
        self._free_unchecked(name, loc)

    def _free_unchecked(self, name: str,
                         loc: Optional[SourceLoc]) -> None:
        """Internal free path. Caller has verified the binding exists.

        T returns to pool; S and A do not (see module docstring).
        """
        b = self.bindings.pop(name)
        if self.reg_to_name.get(b.reg) == name:
            del self.reg_to_name[b.reg]
        if b.storage == Storage.T:
            pool = self._pool_for(b.var_type, Storage.T)
            pool.append(b.reg)
            # Re-sort so allocation order is preserved for the next
            # claim. Determinism matters more than performance here.
            original = _POOLS[(b.var_type, Storage.T)]
            pool.sort(key=lambda r: original.index(r))
        # S: name released, register stays in saved set.
        # A: name released, ABI position unchanged.
        self.freed_names[name] = loc

    # ----- queries -----

    def resolve(self, name: str,
                 loc: Optional[SourceLoc] = None) -> str:
        """Look up the physical register a name refers to.

        SMOLA name -> bound register. Raw register name -> canonical
        ABI form (collision check is the caller's responsibility).
        Unknown / freed -> RegAllocError with a useful diagnostic.
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
                (f"{name!r} was zapped at "
                 f"{prior.filename}:{prior.line_no}")
                if prior else f"{name!r} was zapped",
            )
        raise RegAllocError(
            loc, f"unknown name {name!r}",
            hint="declare it with int / ptr / flt / vec first",
        )

    def is_bound(self, name: str) -> bool:
        return name in self.bindings

    def reg_holder(self, reg: str) -> Optional[Binding]:
        """Inverse lookup: which Binding currently holds `reg`?

        Returns None if the register is free. Used by the collision
        detector. Accepts any form of register name via normalize_reg.
        """
        canonical = normalize_reg(reg)
        if canonical is None:
            return None
        owner_name = self.reg_to_name.get(canonical)
        if owner_name is None:
            return None
        return self.bindings.get(owner_name)

    def _pool_state_hint(self) -> str:
        """Build a diagnostic string showing allocator state, attached
        as a hint to pool-exhaustion errors."""
        lines = []
        if self.bindings:
            entries = sorted(self.bindings.values(),
                             key=lambda b: (b.storage.value, b.reg))
            lines.append(
                "currently bound: "
                + ", ".join(f"{b.name}={b.reg}" for b in entries)
            )
        lines.append(f"free int T: {self.free_int_T}")
        lines.append(f"free int S: {self.free_int_S}")
        lines.append(f"free int A: {self.free_int_A}")
        if self.free_flt_T != list(_FLT_T):
            lines.append(f"free flt T: {self.free_flt_T}")
        if self.free_vec_T != list(_VEC_T):
            lines.append(f"free vec T: {self.free_vec_T}")
        return "\n      ".join(lines)
