"""SMOLA symbol table: structs and method declarations.

v1 supports flat struct layouts only — no inheritance, no bitfields,
no explicit padding. Each field has a name, a type, and a computed
offset. Total size and alignment are derived from field types.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .errors import SourceLoc, StructError


# Type table: (size_in_bytes, alignment, load_mnemonic, store_mnemonic).
# 'load' and 'store' are the GAS mnemonics to use for that width.
PRIMITIVE_TYPES: Dict[str, Tuple[int, int, str, str]] = {
    "i8":  (1, 1, "lb",  "sb"),
    "u8":  (1, 1, "lbu", "sb"),
    "i16": (2, 2, "lh",  "sh"),
    "u16": (2, 2, "lhu", "sh"),
    "i32": (4, 4, "lw",  "sw"),
    "u32": (4, 4, "lwu", "sw"),
    "i64": (8, 8, "ld",  "sd"),
    "u64": (8, 8, "ld",  "sd"),
    "ptr": (8, 8, "ld",  "sd"),
}


@dataclass
class Field:
    name: str
    type_name: str   # primitive name or struct name (v1: primitives only)
    offset: int
    size: int
    align: int
    load_mnemonic: str
    store_mnemonic: str


@dataclass
class StructDef:
    name: str
    fields: List[Field]
    size: int            # rounded up to alignment
    align: int           # = max(field aligns)
    declared_at: Optional[SourceLoc] = None

    def field(self, name: str, loc: Optional[SourceLoc] = None) -> Field:
        for f in self.fields:
            if f.name == name:
                return f
        raise StructError(
            loc,
            f"struct {self.name!r} has no field {name!r}",
            hint=f"known fields: {', '.join(f.name for f in self.fields)}",
        )


def _round_up(x: int, n: int) -> int:
    return (x + n - 1) // n * n


def define_struct(name: str, raw_fields: List[Tuple[str, str]],
                  loc: Optional[SourceLoc] = None) -> StructDef:
    """Build a StructDef from a list of (field_name, type_name) pairs.

    Offsets are assigned in declaration order with natural alignment.
    """
    fields: List[Field] = []
    offset = 0
    max_align = 1
    seen_names: set[str] = set()

    for fname, tname in raw_fields:
        if fname in seen_names:
            raise StructError(
                loc,
                f"duplicate field {fname!r} in struct {name!r}",
            )
        seen_names.add(fname)

        if tname not in PRIMITIVE_TYPES:
            raise StructError(
                loc,
                f"unknown field type {tname!r} in struct {name!r}",
                hint=f"supported types: {', '.join(sorted(PRIMITIVE_TYPES.keys()))}",
            )
        size, align, ld, sd = PRIMITIVE_TYPES[tname]
        offset = _round_up(offset, align)
        fields.append(Field(
            name=fname, type_name=tname, offset=offset,
            size=size, align=align,
            load_mnemonic=ld, store_mnemonic=sd,
        ))
        offset += size
        if align > max_align:
            max_align = align

    total_size = _round_up(offset, max_align) if fields else 0
    return StructDef(
        name=name, fields=fields,
        size=total_size, align=max_align,
        declared_at=loc,
    )


class SymbolTable:
    """Global SMOLA symbol table: structs (and later, methods)."""

    def __init__(self) -> None:
        self.structs: Dict[str, StructDef] = {}

    def add_struct(self, s: StructDef) -> None:
        if s.name in self.structs:
            existing = self.structs[s.name]
            raise StructError(
                s.declared_at,
                f"struct {s.name!r} already declared at "
                f"{existing.declared_at.filename if existing.declared_at else '?'}:"
                f"{existing.declared_at.line_no if existing.declared_at else '?'}",
            )
        self.structs[s.name] = s

    def get_struct(self, name: str, loc: Optional[SourceLoc] = None) -> StructDef:
        if name not in self.structs:
            raise StructError(
                loc,
                f"unknown struct {name!r}",
                hint=f"declared structs: {', '.join(sorted(self.structs.keys())) or '(none)'}",
            )
        return self.structs[name]

    def resolve_field(self, path: str, loc: Optional[SourceLoc] = None) -> Tuple[StructDef, Field]:
        """Resolve a 'Struct.field' path to (struct, field)."""
        if '.' not in path:
            raise StructError(
                loc,
                f"field reference {path!r} must be Struct.field",
            )
        sname, fname = path.split('.', 1)
        s = self.get_struct(sname, loc)
        f = s.field(fname, loc)
        return s, f
