"""SMOLA v0.3 symbol table: struct layouts.

A SMOLA program declares named structs with primitive-typed fields:

    struct Point {
        x: i64,
        y: i64,
    }

This module owns the layout logic — given a list of (field_name,
field_type) pairs, compute byte offsets with natural alignment,
total size, struct alignment, and the GAS load/store mnemonics to use
for each field at access time. The result is captured in a StructDef
and stored in a SymbolTable for the translator to look up.

Unchanged from v0.2 in behavior. Lightly re-commented during the
v0.3 pass.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .errors import SourceLoc, StructError


# Type table for struct fields. Maps a type name to:
#   (size_in_bytes, alignment, load_mnemonic, store_mnemonic)
# Adding a primitive means one new line; downstream never special-
# cases by type name.
PRIMITIVE_TYPES: Dict[str, Tuple[int, int, str, str]] = {
    # Signed/unsigned 1-byte integers. The signed/unsigned distinction
    # matters for partial-width loads (sign-extending vs zero-extending
    # into the 64-bit destination register).
    "i8":  (1, 1, "lb",  "sb"),
    "u8":  (1, 1, "lbu", "sb"),
    # 2-byte.
    "i16": (2, 2, "lh",  "sh"),
    "u16": (2, 2, "lhu", "sh"),
    # 4-byte. On RV64, `lw` sign-extends to 64 bits; `lwu` zero-extends.
    "i32": (4, 4, "lw",  "sw"),
    "u32": (4, 4, "lwu", "sw"),
    # 8-byte. Sign-vs-unsigned makes no difference at this width.
    "i64": (8, 8, "ld",  "sd"),
    "u64": (8, 8, "ld",  "sd"),
    # Float and double. Require F and D extensions (mandatory in RVA23).
    "f32": (4, 4, "flw", "fsw"),
    "f64": (8, 8, "fld", "fsd"),
    # Opaque 8-byte pointer. Same mnemonics as u64; the name is for
    # the reader.
    "ptr": (8, 8, "ld",  "sd"),
}


@dataclass
class Field:
    """One field of a struct, with everything the translator needs."""
    name: str
    type_name: str
    offset: int
    size: int
    align: int
    load_mnemonic: str
    store_mnemonic: str

    @property
    def is_float(self) -> bool:
        return self.type_name in ("f32", "f64")


@dataclass
class StructDef:
    """A complete struct declaration. Immutable after construction."""
    name: str
    fields: List[Field]
    size: int               # rounded up to struct's alignment
    align: int              # = max of field alignments
    declared_at: Optional[SourceLoc] = None

    def field(self, name: str,
              loc: Optional[SourceLoc] = None) -> Field:
        """Look up a field by name. Linear scan; structs are small."""
        for f in self.fields:
            if f.name == name:
                return f
        raise StructError(
            loc,
            f"struct {self.name!r} has no field {name!r}",
            hint=f"known fields: {', '.join(f.name for f in self.fields)}",
        )


def _round_up(x: int, n: int) -> int:
    """Round x up to the next multiple of n. Used for natural-alignment
    field placement and final-size padding."""
    return (x + n - 1) // n * n


def define_struct(name: str, raw_fields: List[Tuple[str, str]],
                  loc: Optional[SourceLoc] = None) -> StructDef:
    """Build a StructDef from a list of (field_name, type_name) pairs.

    Layout: for each field in source order, round the write offset
    up to the field's alignment, place the field there, advance the
    offset by the field's size. After all fields, round the total
    size up to the struct's alignment (= max field alignment).

    This matches the C ABI on RISC-V, so SMOLA structs are compatible
    with C-allocated structs without per-field accessor wrappers.

    Errors: duplicate field name, unknown field type. Both reported
    with helpful hints.
    """
    fields: List[Field] = []
    offset = 0
    max_align = 1
    seen: set = set()

    for fname, tname in raw_fields:
        if fname in seen:
            raise StructError(
                loc,
                f"duplicate field {fname!r} in struct {name!r}",
            )
        seen.add(fname)

        if tname not in PRIMITIVE_TYPES:
            raise StructError(
                loc,
                f"unknown field type {tname!r} in struct {name!r}",
                hint=(f"supported: "
                      f"{', '.join(sorted(PRIMITIVE_TYPES.keys()))}"),
            )

        size, align, ld, sd = PRIMITIVE_TYPES[tname]
        # Natural-alignment placement: bump offset up to the field's
        # alignment before placing it.
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
    """The translator's catalog of declared structs.

    One instance per translation. Each `struct` directive registers a
    new entry; each `load_field` / `store_field` / `addr_field` /
    `call Struct.method` looks one up. No removal; structs live until
    end of translation.
    """

    def __init__(self) -> None:
        self.structs: Dict[str, StructDef] = {}

    def add_struct(self, s: StructDef) -> None:
        """Register a new struct. Errors on re-declaration."""
        if s.name in self.structs:
            existing = self.structs[s.name]
            raise StructError(
                s.declared_at,
                f"struct {s.name!r} already declared at "
                f"{existing.declared_at.filename if existing.declared_at else '?'}:"
                f"{existing.declared_at.line_no if existing.declared_at else '?'}",
            )
        self.structs[s.name] = s

    def get_struct(self, name: str,
                    loc: Optional[SourceLoc] = None) -> StructDef:
        """Look up a struct by name with a helpful hint on miss."""
        if name not in self.structs:
            raise StructError(
                loc, f"unknown struct {name!r}",
                hint=(f"declared: "
                      f"{', '.join(sorted(self.structs.keys())) or '(none)'}"),
            )
        return self.structs[name]

    def has_struct(self, name: str) -> bool:
        """Predicate without raising. Used by the `func Foo.bar`
        method-detection code path."""
        return name in self.structs

    def resolve_field(self, path: str,
                       loc: Optional[SourceLoc] = None
                       ) -> Tuple[StructDef, Field]:
        """Resolve a `Struct.field` path. Returns both pieces because
        callers usually want the struct for diagnostics and the field
        for emission."""
        if '.' not in path:
            raise StructError(
                loc, f"field reference {path!r} must be Struct.field",
            )
        sname, fname = path.split('.', 1)
        s = self.get_struct(sname, loc)
        return s, s.field(fname, loc)
