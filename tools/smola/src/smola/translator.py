"""SMOLA v0.3 translator.

Orchestrates the pipeline:
  - lex source -> Line stream
  - walk Lines, maintaining symbol table, allocator, scope stack,
    per-function buffer, and a pending-comment buffer
  - at `end`, plan the frame and stitch:
      header -> prologue -> bindings table -> body -> epilogue
  - emit a complete .s file

Major v0.3 changes from v0.2:
  - Discriminator is content-based, not prefix-based. Lexer already
    handles this; the translator dispatches on LineKind.
  - Variable declarations are bare type keywords (`int counter`)
    instead of `_var.t int counter`. Storage-class suffixes
    (`int.s`, `int.a`) used for non-default storage.
  - Initialization shorthand: `int counter 10` declares and emits
    `li`. `flt gain 0.75` declares and emits the appropriate float-
    immediate sequence.
  - Comments transfer to the generated .s. Block comments above a
    func go before the function header. Block comments inside the
    function go in body order. End-of-line comments attach to the
    instruction they document.
  - Auto-generated bindings table at the top of each function lists
    every variable and its register.
  - `zap` replaces v0.2's `_free`. `end` replaces `_endfunc` /
    `_endmethod`. `func Foo.bar` does method-detection automatically.
"""

import re
import struct as _struct  # avoid name clash with our `struct` keyword
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import __version__
from .errors import (CollisionError, FrameError, ParseError,
                     RegAllocError, SmolaError, SourceLoc, StructError)
from .frame import FramePlan, emit_epilogue, emit_prologue, plan_frame
from .lexer import Line, LineKind, SMOLA_KEYWORDS, lex_source
from .regalloc import (Allocator, Binding, Storage, VarType,
                       is_register_name, normalize_reg)
from .symbols import SymbolTable, define_struct


# Subset of SMOLA_KEYWORDS that introduce a variable declaration.
# Computed once at module load by intersecting the full keyword set
# with the set of type-leading tokens. The dispatch in `_handle_smola`
# does a single hash lookup against this set.
#
# What counts as "type-leading":
#   - integer family: int, i8, u8, i16, u16, i32, u32, i64, u64
#   - pointer: ptr
#   - float: f32, f64
#   - vector: vec
# Each may carry .s or .a storage suffix; the base + suffix forms
# were already enumerated when SMOLA_KEYWORDS was built.
VAR_DECL_KEYWORDS = frozenset(
    kw for kw in SMOLA_KEYWORDS
    if kw.split('.')[0] in {
        "int", "i8", "u8", "i16", "u16", "i32", "u32", "i64", "u64",
        "ptr", "f32", "f64", "vec",
    }
)


# Width-typed integer keyword bases (without any storage suffix).
# Used by the data-declaration handler to map type names to GAS
# storage directives and natural alignments.
DATA_TYPE_INFO = {
    # Type name : (GAS directive, size in bytes, alignment in bytes)
    "i8":  (".byte",   1, 1),
    "u8":  (".byte",   1, 1),
    "i16": (".hword",  2, 2),
    "u16": (".hword",  2, 2),
    "i32": (".word",   4, 4),
    "u32": (".word",   4, 4),
    "i64": (".dword",  8, 8),
    "u64": (".dword",  8, 8),
    "f32": (".float",  4, 4),
    "f64": (".double", 8, 8),
    "ptr": (".dword",  8, 8),
    # NOTE: `int` and `vec` are deliberately absent. Data must commit
    # to a concrete width; `int` is ambiguous (use i64 or u64) and
    # `vec` has no fixed width independent of its elements (use the
    # underlying scalar type).
}


# Section-name prefixes that classify a section as a *data* section
# rather than a code section. SMOLA tracks the current section by
# observing `.section` GAS directives; if the name starts with one
# of these prefixes, data-declaration semantics activate. The default
# section at file start is `.text` (code).
_DATA_SECTION_PREFIXES = (".data", ".rodata", ".bss", ".tdata", ".tbss")


def _is_data_section(name: str) -> bool:
    """Is `name` (the section name from a `.section` directive) a
    data section?

    Matches any prefix in _DATA_SECTION_PREFIXES, including
    sub-sections like `.rodata.cst8` (which GAS uses for constant
    pools).
    """
    return any(name == p or name.startswith(p + ".")
               for p in _DATA_SECTION_PREFIXES)


# Regex for `imm(reg)` memory operands. Imm is optional (atomics use
# `(rs1)` with no offset; the regex makes it optional and we default
# to "0" at emission time).
_MEM_OPERAND_RE = re.compile(
    r'^\s*([+-]?(?:0x[0-9a-fA-F]+|\d+|[A-Za-z_][\w]*))?'
    r'\s*\(\s*([A-Za-z_]\w*)\s*\)\s*$'
)

# Pattern for identifying register tokens inside raw assembly lines.
# Used by the collision detector to scan a passthrough line for any
# token that might be a register reference.
_TOKEN_RE = re.compile(r'[A-Za-z_]\w*')


def _split_operands(tail: str) -> List[str]:
    """Comma-split operands, respecting parens.

    `"a, b, 0(sp)"` -> `["a", "b", "0(sp)"]`. Tracks paren depth so
    commas inside memory operands aren't split on (none exist in
    standard syntax, but the depth tracking is harmless).
    """
    if tail.strip() == "":
        return []
    parts: List[str] = []
    depth = 0
    current = []
    for ch in tail:
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current or parts:
        parts.append(''.join(current).strip())
    return [p for p in parts if p]


def _looks_like_immediate(s: str) -> bool:
    """Heuristic: does this token look like a numeric immediate or
    local label?

    Recognizes:
      - integers: 42, -5, 0xDEAD, +1
      - floats: 0.5, 1e3, -1.5e-10
      - local labels: anything starting with `.`
    """
    s = s.strip()
    if not s:
        return False
    rest = s[1:] if s[0] in '-+' else s
    if rest.startswith('0x') or rest.startswith('0X'):
        return all(c in '0123456789abcdefABCDEF' for c in rest[2:])
    if rest and (rest[0].isdigit() or rest[0] == '.'):
        try:
            float(rest)
            return True
        except ValueError:
            pass
    # Local labels start with `.` (e.g. `.Ldone`).
    if s.startswith('.'):
        return True
    return False


def _parse_var_keyword(keyword: str) -> Tuple[VarType, Storage, str]:
    """Parse a SMOLA variable keyword into (VarType, Storage, declared_width).

    Accepts the v0.3-refined vocabulary:

      - `int`, `i8`, `u8`, `i16`, `u16`, `i32`, `u32`, `i64`, `u64`
        → VarType.INT
      - `ptr` → VarType.PTR
      - `f32`, `f64` → VarType.FLT
      - `vec` → VarType.VEC

    Each may carry a `.s` (callee-saved) or `.a` (argument) suffix.
    Default storage is T (caller-saved temporary).

    The width-typed integer variants (`i8`, `u8`, `i16`, ...) all
    allocate from the integer register pool — the integer register
    file on RV64 is 64-bit physically and SMOLA doesn't try to
    enforce sub-word widths at instruction level. The declared width
    is returned as the third tuple element ("documentation width")
    for inclusion in the bindings table at the function head and
    for future width-aware default load/store inference (a v0.4
    feature; the hook exists now even though it isn't wired).

    The `declared_width` string is the base keyword as the user
    wrote it ("int", "i8", "u32", "ptr", "f32", "f64", "vec").
    It survives into the Binding for documentation purposes.

    Note: `flt` was removed in the v0.3 refinements. The lexer
    catches it earlier with a migration hint, so this function
    never sees `flt` in practice.
    """
    # Split off any storage suffix.
    base, _, suffix = keyword.partition('.')

    # Integer family. All map to VarType.INT for allocation; the
    # declared width is documentation.
    int_family = ["int", "i8", "u8", "i16", "u16",
                  "i32", "u32", "i64", "u64"]
    if base in int_family:
        var_type = VarType.INT
    elif base == "ptr":
        var_type = VarType.PTR
    elif base == "f32":
        var_type = VarType.FLT
    elif base == "f64":
        var_type = VarType.FLT
    elif base == "vec":
        var_type = VarType.VEC
    else:
        # Defensive: the lexer should have already filtered to known
        # SMOLA keywords. If we get here it's a SMOLA bug, not user
        # error.
        raise ParseError(
            None, f"unknown variable type keyword {keyword!r}",
        )

    if suffix == "":
        storage = Storage.T
    elif suffix == "s":
        storage = Storage.S
    elif suffix == "a":
        storage = Storage.A
    else:
        raise ParseError(
            None, f"unknown storage suffix .{suffix!r}",
            hint="use .s for callee-saved or .a for argument",
        )
    return var_type, storage, base


@dataclass
class FuncCtx:
    """Per-function state. Created at `func`, finalized at `end`."""
    name: str
    is_global: bool
    declared_at: SourceLoc
    alloc: Allocator = field(default_factory=Allocator)
    body_lines: List[str] = field(default_factory=list)
    calls_other: bool = False
    user_spill_bytes: int = 0
    header_lines: List[str] = field(default_factory=list)
    # Block comments that appeared before this function in source.
    # Emitted into the .s immediately before the function header.
    leading_comments: List[str] = field(default_factory=list)
    # Float-init literal pool entries — bit patterns to emit at the
    # end of the function's section. Used for f64 initialization.
    flt_pool: List[Tuple[str, int]] = field(default_factory=list)
    # Counter for unique labels within the function (for flt pool
    # entries, etc.).
    label_counter: int = 0
    # Set of label names declared in this function. Populated as
    # `<name>:` lines are processed. Used by operand resolution to
    # recognize branch targets that don't start with `.`.
    declared_labels: set = field(default_factory=set)


class Translator:
    """The full SMOLA translator. Owns the symbol table, output
    buffer, and current-function state."""

    def __init__(self, filename: str = "<input>",
                 emit_provenance: bool = True):
        self.filename = filename
        self.emit_provenance = emit_provenance
        self.symbols = SymbolTable()
        self.current_func: Optional[FuncCtx] = None
        # All output, fully formed, in order.
        self.output_lines: List[str] = []
        # Buffer for block comments not yet attached to a destination.
        # Flushed when a non-comment line arrives, or attached to the
        # next `func`.
        self.pending_comments: List[str] = []

        # Data-section state. SMOLA tracks the current section by
        # observing `.section` GAS directives as they stream past.
        # The default at file start is `.text` (code). When the
        # section is a data section, the type keywords (i8, u8, ...
        # f32, f64, ptr) gain a second meaning: they introduce
        # labeled data blocks. A line whose first token is a numeric
        # literal (LineKind.DATA_VALUES) is accepted as a
        # continuation of a previously-emitted data directive.
        self.current_section: str = ".text"
        # Most recent label emitted in the current data section, or
        # None. Used for the `.size` directive after a data block.
        self.current_data_label: Optional[str] = None
        # Bytes written since the most recent data label. Drives the
        # `.size` directive.
        self.current_data_label_bytes: int = 0
        # Type info of the most recent data directive, or None. Used
        # to interpret DATA_VALUES continuation lines: they emit
        # values of the same type as the directive they continue.
        # Tuple of (gas_directive, element_size, element_alignment,
        # keyword) — the keyword preserved for diagnostics.
        self.pending_data_type: Optional[Tuple[str, int, int, str]] = None

        # txt-block state. When non-None, we are inside an open txt
        # heredoc block; the list accumulates raw content lines.
        self.txt_in_progress: Optional[List[str]] = None
        self.txt_start_loc: Optional[SourceLoc] = None

    # ----- entry point -----

    def translate(self, source: str) -> str:
        """Translate a full SMOLA source string to a .s string."""
        self._emit_file_header()
        # Fold multi-line struct declarations so the inner field lines
        # don't get lexed as labels.
        source = _fold_multiline_structs(source)
        for line in lex_source(self.filename, source):
            self._process_line(line)
        # Any trailing pending comments at EOF flush as top-level
        # output.
        self._flush_pending_comments(target="output")
        # Any open data block at EOF gets its .size flushed.
        self._flush_data_label_size()
        if self.txt_in_progress is not None:
            raise ParseError(
                self.txt_start_loc,
                "unterminated txt block (missing `eot`)",
                hint="add `eot` on its own line to close the txt block",
            )
        if self.current_func is not None:
            raise FrameError(
                self.current_func.declared_at,
                f"function {self.current_func.name!r} was never closed",
                hint="add a matching `end` directive",
            )
        return "\n".join(self.output_lines) + "\n"

    # ----- line dispatch -----

    def _process_line(self, line: Line) -> None:
        # txt heredoc interior lines bypass all comment-flush logic —
        # the lexer already classified them in stateful mode.
        if line.kind == LineKind.TXT_LINE:
            self._handle_txt_line(line)
            return
        if line.kind == LineKind.TXT_END:
            self._handle_txt_end(line)
            return

        # Comments accumulate in the pending buffer regardless of
        # what's coming next — flush behavior depends on the next
        # non-comment line.
        if line.kind == LineKind.COMMENT:
            self.pending_comments.append(line.tail)
            return

        if line.kind == LineKind.BLANK:
            # Blanks within a comment block stay attached to the
            # block; we represent them as empty lines in the pending
            # buffer so the structure is preserved on flush.
            if self.pending_comments:
                self.pending_comments.append("")
            else:
                self._emit_to_current("")
            return

        # Any other line ends the comment block. Decide where the
        # comments go: if the next line is a `func`, attach them to
        # the function so they emit before its section header.
        # Otherwise flush them at the current position.
        if line.kind == LineKind.SMOLA and line.head == "func":
            # The func handler will attach pending_comments to the
            # FuncCtx and clear the buffer.
            pass
        elif (line.kind == LineKind.LABEL
                and _is_data_section(self.current_section)
                and self.current_data_label is not None):
            # Special case: a new label in a data section ends the
            # previous block's data. We want the `.size` directive
            # to appear right after the data, BEFORE any block
            # comment that documents the next label. Otherwise the
            # `.size` line drifts into the comment block for the
            # next label and the attribution looks confused.
            self._flush_data_label_size()
            self._flush_pending_comments(target="auto")
        else:
            self._flush_pending_comments(target="auto")

        if line.kind == LineKind.LABEL:
            self._handle_label(line)
            return
        if line.kind == LineKind.GAS_DIRECTIVE:
            self._handle_gas_directive(line)
            return
        if line.kind == LineKind.RV_INSN:
            self._handle_rv_insn(line)
            return
        if line.kind == LineKind.SMOLA:
            self._handle_smola(line)
            return
        if line.kind == LineKind.DATA_VALUES:
            self._handle_data_values(line)
            return
        if line.kind == LineKind.TXT_BLOCK:
            self._handle_txt_block(line)
            return
        if line.kind == LineKind.TXT_LINE:
            self._handle_txt_line(line)
            return
        if line.kind == LineKind.TXT_END:
            self._handle_txt_end(line)
            return

        # Shouldn't reach here — every LineKind is handled above.
        raise ParseError(line.loc, f"unhandled line kind {line.kind}")

    # ----- pending-comment management -----

    def _flush_pending_comments(self, target: str) -> None:
        """Move buffered comments to the output.

        `target` is one of:
          - "output": top-level output stream (before any function or
            between functions)
          - "current": inside the current function's body buffer
          - "auto": pick based on whether we're inside a function
        """
        if not self.pending_comments:
            return
        if target == "auto":
            target = "current" if self.current_func is not None else "output"
        # Normalize `//` to `#` for GAS.
        normalized = []
        for line in self.pending_comments:
            if line.startswith('//'):
                normalized.append('#' + line[2:])
            else:
                normalized.append(line)
        if target == "current":
            self.current_func.body_lines.extend(normalized)
        else:
            self.output_lines.extend(normalized)
        self.pending_comments = []

    # ----- label / GAS directive / raw RV instruction -----

    def _handle_label(self, line: Line) -> None:
        """Process a `<label>:` line.

        Three contexts:
        - Inside a function (code section): register the label name so
          branch operands can resolve it without a `.L` prefix.
        - In a data section: this label becomes the `current_data_label`,
          which the next data directive will associate values with.
          Any previous data block in this section gets its `.size`
          directive flushed first.
        - Top-level (.text but no function): just emit the label.
        """
        # If we're inside a function, register this label so branch
        # operands can resolve it.
        if self.current_func is not None:
            self.current_func.declared_labels.add(line.head)

        # In a data section, a new label terminates any previous data
        # block (we emit its `.size`). The new label becomes the
        # current_data_label and the byte counter resets to 0.
        if _is_data_section(self.current_section):
            self._flush_data_label_size()
            self.current_data_label = line.head
            self.current_data_label_bytes = 0
            # A label in a data section also terminates any pending
            # continuation context — values after a new label can only
            # be a new data directive (or a real RV-mnemonic style
            # error).
            self.pending_data_type = None

        text = f"{line.head}:"
        if line.trailing_comment:
            text += f"    {line.trailing_comment}"
        self._emit_to_current(text)

    def _handle_gas_directive(self, line: Line) -> None:
        """Process a GAS directive (starts with `.`).

        Side effect: if the directive is `.section`, update
        `current_section`. We also flush any pending data-block size
        on section change, because a section switch closes whatever
        data block was open.
        """
        # Pass-through with collision check. GAS directives rarely
        # reference registers, but `.equ counter, 0x10` could.
        if self.current_func is not None:
            self._check_collisions(line)

        # Detect a `.section` and update our notion of current
        # section. The directive's tail starts with the section name,
        # possibly followed by flags and a comma-separated list. We
        # take the first comma-separated token as the section name.
        if line.head == ".section":
            new_section = line.tail.split(',')[0].strip()
            # Flush any pending data-block size before transitioning.
            self._flush_data_label_size()
            self.current_section = new_section
            self.current_data_label = None
            self.current_data_label_bytes = 0
            self.pending_data_type = None

        body = f"    {line.head}"
        if line.tail:
            body += f" {line.tail}"
        if line.trailing_comment:
            body += f"    {line.trailing_comment}"
        self._emit_to_current(body)

    def _flush_data_label_size(self) -> None:
        """If there is an active data label with accumulated bytes,
        emit its `.size` directive and reset the counter.

        Called at:
          - section change (.section directive)
          - new label in a data section
          - EOF
        The flush is a no-op if there is no current data label or if
        no bytes were written under it.
        """
        if (self.current_data_label is not None
                and self.current_data_label_bytes > 0):
            self.output_lines.append(
                f"    .size {self.current_data_label}, "
                f"{self.current_data_label_bytes}"
            )
            self.current_data_label = None
            self.current_data_label_bytes = 0

    def _handle_rv_insn(self, line: Line) -> None:
        """Process a recognized RISC-V instruction line.

        Special-cases `call` with comma-separated operands (the SMOLA
        argument-shuffling form). Otherwise, resolves SMOLA variable names
        to physical registers within a function. Outside a function, passes
        the instruction through verbatim.
        """
        # Special-case `call`: a tail with no commas is a raw call;
        # a tail with commas is the SMOLA argument-shuffling form.
        if line.head == "call" and ',' in line.tail:
            self._handle_call_pseudo(line)
            return

        # Track calls for the frame planner.
        if line.head in ("call", "jal", "tail"):
            if self.current_func is not None:
                self.current_func.calls_other = True

        if self.current_func is not None:
            # Substitute any SMOLA names in operands with their
            # registers. We resolve every comma-separated operand;
            # raw-register references trigger the collision check.
            ops = _split_operands(line.tail)
            new_ops = [self._resolve_operand(op, line) for op in ops]
            text = f"    {line.head}"
            if new_ops:
                text += f" {', '.join(new_ops)}"
            if line.trailing_comment:
                # Trailing comment goes after the substituted operands.
                text += f"    {line.trailing_comment}"
            self._emit_to_current(text)
        else:
            # Outside any function — pass through unchanged. (This is
            # rare; usually instructions live inside funcs. GAS will
            # complain if they don't.)
            text = f"    {line.head}"
            if line.tail:
                text += f" {line.tail}"
            if line.trailing_comment:
                text += f"    {line.trailing_comment}"
            self._emit_to_current(text)

    def _check_collisions(self, line: Line) -> None:
        """Scan a passthrough line for register tokens that collide
        with active bindings.

        Conservative: we walk every word that could be a register name
        and check it against the active binding table. False positives
        are possible if a label happens to have the same name as a
        register (rare). False negatives are not, which is the
        important direction.
        """
        assert self.current_func is not None
        alloc = self.current_func.alloc
        full_text = (line.head + " " + line.tail) if line.tail else line.head
        for match in _TOKEN_RE.finditer(full_text):
            token = match.group(0)
            canonical = normalize_reg(token)
            if canonical is None:
                continue
            holder = alloc.reg_holder(canonical)
            if holder is not None:
                raise CollisionError(
                    line.loc,
                    f"register {canonical} is currently bound to "
                    f"variable {holder.name!r}",
                    hint=(
                        f"use {holder.name!r} instead, or "
                        f"`zap {holder.name}` before this line"
                    ),
                )

    # ----- SMOLA keyword dispatch -----

    def _handle_smola(self, line: Line) -> None:
        head = line.head

        # Block-shaping directives.
        if head == "func":
            self._open_func(line)
            return
        if head == "end":
            self._close_func(line)
            return
        if head == "scope":
            self._open_scope(line)
            return
        if head == "endscope":
            self._close_scope(line)
            return

        # Declarations.
        if head == "struct":
            self._declare_struct(line)
            return
        if head == "stack":
            self._set_user_spill(line)
            return

        # Variable declarations. Bare type keywords:
        #   int, ptr, vec, f32, f64,
        #   i8/u8/i16/u16/i32/u32/i64/u64,
        # plus their .s and .a suffixed variants. The set is computed
        # once at module load (below) so the dispatch is just a hash
        # check.
        if head in VAR_DECL_KEYWORDS:
            self._handle_var_decl(line)
            return

        if head == "zap":
            self._handle_zap(line)
            return

        # Field access.
        if head == "load_field":
            self._handle_load_field(line)
            return
        if head == "store_field":
            self._handle_store_field(line)
            return
        if head == "addr_field":
            self._handle_addr_field(line)
            return

        # String data keywords.
        if head == "str":
            self._handle_str_decl(line)
            return
        if head == "cstr":
            self._handle_cstr_decl(line)
            return
        # txt is handled as TXT_BLOCK by _process_line directly; it
        # should never reach here as a plain SMOLA line.

        # f16 / bf16 — declared but not yet implemented.
        _f16_bases = {"f16", "bf16"}
        if head.split('.')[0] in _f16_bases:
            raise ParseError(
                line.loc,
                f"`{head}` is not yet implemented",
                hint=(
                    "f16 and bf16 support is planned for a future SMOLA "
                    "release; use f32 or f64 for now"
                ),
            )

        # Sub-byte and exotic FP reserved keywords.
        _reserved_bases = {
            "fp8", "fp4", "i4", "u4", "i2", "u2", "i1", "u1",
            "b1p58", "packed",
        }
        if head.split('.')[0] in _reserved_bases:
            raise ParseError(
                line.loc,
                f"`{head}` is a reserved keyword (not yet implemented)",
                hint=(
                    "sub-byte and exotic FP types are reserved for a future "
                    "SMOLA release"
                ),
            )

        # Raw escape hatch.
        if head == "raw":
            self._handle_raw(line)
            return

        raise ParseError(line.loc, f"unhandled SMOLA keyword {head!r}")

    # ----- func / end -----

    def _open_func(self, line: Line) -> None:
        if self.current_func is not None:
            raise FrameError(
                line.loc,
                f"nested function definitions are not allowed "
                f"(currently inside {self.current_func.name!r})",
            )

        # Flush pending comments to top-level output BEFORE the
        # function header.
        self._flush_pending_comments(target="output")

        parts = line.tail.split()
        if not parts:
            raise ParseError(line.loc, "expected function name")
        name = parts[0]
        is_global = True
        for extra in parts[1:]:
            if extra == "static":
                is_global = False
            else:
                raise ParseError(
                    line.loc, f"unknown modifier {extra!r}",
                    hint="only 'static' is recognized",
                )

        # Detect Struct.method form. If the name has a dot AND a
        # matching struct exists, treat as a method (implicit self
        # binding). Otherwise emit the dot as an underscore in the
        # symbol name without method semantics.
        is_method = False
        if '.' in name:
            sname, mname = name.split('.', 1)
            if self.symbols.has_struct(sname):
                is_method = True
            emit_name = f"{sname}_{mname}"
        else:
            emit_name = name

        ctx = FuncCtx(
            name=emit_name, is_global=is_global, declared_at=line.loc,
        )
        # Build header lines.
        header: List[str] = ["",
            f"    .section .text.{emit_name}, \"ax\", @progbits"]
        if is_global:
            header.append(f"    .globl  {emit_name}")
        header.append(f"    .type   {emit_name}, @function")
        header.append("    .balign 2")
        header.append(f"{emit_name}:")
        ctx.header_lines = header

        # Implicit self binding for methods. Declared as `ptr` so
        # the bindings table reads `self: a0 (ptr, a)`.
        if is_method:
            ctx.alloc.alloc("self", VarType.PTR, Storage.A,
                            explicit_reg="a0", loc=line.loc,
                            declared_width="ptr")

        self.current_func = ctx

    def _close_func(self, line: Line) -> None:
        if self.current_func is None:
            raise FrameError(
                line.loc, "end without matching func",
            )
        ctx = self.current_func

        # Capture the full binding history BEFORE auto-free clears it.
        full_history = list(ctx.alloc.history)

        # Auto-free everything still live. Errors on unclosed scopes.
        freed = ctx.alloc.pop_all_remaining(line.loc)

        # Frame plan.
        plan = plan_frame(
            saved_int_s=set(ctx.alloc.saved_int_S),
            saved_flt_s=set(ctx.alloc.saved_flt_S),
            calls_other=ctx.calls_other,
            user_spill_bytes=ctx.user_spill_bytes,
        )

        # Stitch: header -> prologue -> bindings table -> body ->
        # epilogue -> .size -> flt pool (if any).
        out = list(ctx.header_lines)
        out.extend(emit_prologue(plan))
        if self.emit_provenance:
            out.extend(self._format_bindings_table(full_history))
        out.extend(ctx.body_lines)
        out.extend(emit_epilogue(plan))
        out.append(f"    .size {ctx.name}, .-{ctx.name}")
        # Flt literal pool at the end of the function's section.
        if ctx.flt_pool:
            out.append(f"    .balign 8")
            for label, bits in ctx.flt_pool:
                out.append(f"{label}:")
                # GAS .dword takes a value; we emit the 64-bit pattern
                # in hex with proper width.
                out.append(f"    .dword 0x{bits:016x}")
        out.append("")
        self.output_lines.extend(out)
        self.current_func = None

    def _format_bindings_table(self, history: List[Binding]) -> List[str]:
        """Build the auto-generated bindings table comment block.

        Lists every named variable that lived in the function, in
        declaration order, with its physical register, declared type
        (the keyword the user wrote: `int`, `u8`, `f32`, `ptr`, ...),
        and storage class. Bindings inside nested scopes get a (scope
        N) annotation.

        Internal SMOLA-generated transient bindings (names starting
        with `.smola_`) are filtered out — they exist for one or two
        instructions during float initialization and would just be
        noise in the user-facing table.

        The declared-width string is what makes the bindings table
        readable: a binding shown as `counter: t0 (u32, t)` tells
        the user immediately that `counter` was meant to hold a 32-
        bit unsigned value. Without it, the bindings table could
        only say `counter: t0 (int, t)` and the user would have to
        scan the code to recover the width intent.
        """
        # Filter user bindings only.
        user_bindings = [b for b in history
                         if not b.name.startswith('.smola_')]
        if not user_bindings:
            return ["    # smola: bindings — (none)"]
        lines = ["    # smola: bindings —"]
        for b in user_bindings:
            scope_suffix = ""
            if b.scope_depth > 1:
                scope_suffix = f", scope {b.scope_depth}"
            # Prefer the user's declared width keyword over the
            # internal var_type. Fall back to var_type for bindings
            # constructed without a declared_width (e.g. the implicit
            # `self -> a0` in method functions, which uses var_type
            # alone).
            type_str = b.declared_width if b.declared_width else b.var_type.value
            lines.append(
                f"    #   {b.name}: {b.reg} "
                f"({type_str}, {b.storage.value}{scope_suffix})"
            )
        return lines

    # ----- scope / endscope -----

    def _open_scope(self, line: Line) -> None:
        """Push a lifetime scope. Variables declared after this are freed at `endscope`."""
        ctx = self._ensure_func(line)
        ctx.alloc.push_scope()
        if self.emit_provenance:
            ctx.body_lines.append(
                f"    # smola: scope begin (depth {ctx.alloc.current_depth})"
            )

    def _close_scope(self, line: Line) -> None:
        """Pop the current scope and free all variables declared inside it."""
        ctx = self._ensure_func(line)
        depth_before = ctx.alloc.current_depth
        freed = ctx.alloc.pop_scope(line.loc)
        if self.emit_provenance:
            if freed:
                ctx.body_lines.append(
                    f"    # smola: scope end (depth {depth_before}) "
                    f"— freed: {', '.join(freed)}"
                )
            else:
                ctx.body_lines.append(
                    f"    # smola: scope end (depth {depth_before})"
                )

    # ----- struct / stack -----

    def _declare_struct(self, line: Line) -> None:
        text = line.tail.strip()
        if '{' not in text or '}' not in text:
            raise StructError(
                line.loc,
                "struct declaration must be: struct Name { field: type, ... }",
            )
        name_part, _, rest = text.partition('{')
        body, _, _ = rest.partition('}')
        name = name_part.strip()
        if not name:
            raise StructError(line.loc, "struct must have a name")
        raw_fields: List[Tuple[str, str]] = []
        for ft in body.split(','):
            ft = ft.strip()
            if not ft:
                continue
            if ':' not in ft:
                raise StructError(line.loc, f"field {ft!r} must be name: type")
            fname, _, tname = ft.partition(':')
            raw_fields.append((fname.strip(), tname.strip()))
        if not raw_fields:
            raise StructError(line.loc, f"struct {name!r} has no fields")
        sdef = define_struct(name, raw_fields, loc=line.loc)
        self.symbols.add_struct(sdef)

        # Emit the GAS .set lines so raw-assembly code can reference
        # offsets symbolically.
        if self.emit_provenance:
            self.output_lines.append(
                f"    # smola: struct {name} "
                f"({sdef.size} bytes, align {sdef.align})"
            )
        for f in sdef.fields:
            self.output_lines.append(
                f"    .set {name}_{f.name}_offset, {f.offset}"
            )
        self.output_lines.append(f"    .set {name}_size, {sdef.size}")
        self.output_lines.append(f"    .set {name}_align, {sdef.align}")
        self.output_lines.append("")

    def _set_user_spill(self, line: Line) -> None:
        """Parse `stack N` and record N extra bytes of stack space for frame planning."""
        ctx = self._ensure_func(line)
        try:
            n = int(line.tail.strip(), 0)
        except ValueError:
            raise ParseError(
                line.loc,
                f"expected integer byte count, got {line.tail!r}",
            )
        if n < 0:
            raise ParseError(line.loc, "stack size must be non-negative")
        ctx.user_spill_bytes = n

    # ----- variable declarations -----

    def _handle_var_decl(self, line: Line) -> None:
        """Dispatch to either the code-section variable declaration
        handler or the data-section data-declaration handler based
        on the current section.

        The same keywords (`i8`, `u8`, ... `f64`, `ptr`, plus `int`,
        `vec`, and storage suffixes) have two meanings:
          - In a code section: declare a variable bound to a register.
          - In a data section: declare a labeled data block.

        `int` and `vec` are forbidden in data declarations (the user
        must commit to a width); the data handler rejects them with
        a helpful hint.
        """
        if _is_data_section(self.current_section):
            self._handle_data_decl(line)
        else:
            self._handle_code_var_decl(line)

    def _handle_code_var_decl(self, line: Line) -> None:
        """Parse and handle code-section variable declarations.

        Examples (each shows the new keyword vocabulary):

          int x                  # default integer
          u8 byte_counter        # width-typed (documentation)
          ptr base               # pointer
          f32 gain 0.75          # f32 with init
          f64 precise 0.5        # f64 with init
          int.s persistent       # callee-saved
          int.a x = a3           # pinned argument
          i32 counter 10         # width-typed with init

        The width-typed integer variants (i8/u8/i16/.../u64) all
        allocate from VarType.INT — the integer register file is
        64-bit on RV64 regardless of declared width. The declared
        width is stored on the Binding (via Allocator.alloc) and
        surfaces in the bindings table at the function head.
        """
        ctx = self._ensure_func(line)
        keyword = line.head

        # The lexer only routes lines whose first token is in
        # VAR_DECL_KEYWORDS here, so this call cannot fail on unknown
        # keywords. It can still fail on a malformed `.suffix`, which
        # would be a SMOLA bug since SMOLA_KEYWORDS already only
        # contains valid suffixes.
        try:
            var_type, storage, declared_width = _parse_var_keyword(keyword)
        except ParseError as e:
            raise ParseError(line.loc, e.message, hint=e.hint)

        # Float-precision tracking for init emission. f32 produces
        # the inline `li`+`fmv.w.x` sequence; f64 emits a literal
        # pool entry and `la`+`fld`. For non-float types this is
        # None.
        precision = declared_width if declared_width in ("f32", "f64") else None

        # Parse the tail. Allowed shapes:
        #   <name>
        #   <name> <initializer>
        #   <name> = <reg>          (only for .a storage)
        #   <initializer>            (anonymous — reserved for v0.4)
        tail = line.tail.strip()
        if tail == "":
            raise ParseError(
                line.loc, f"`{keyword}` requires a variable name",
            )

        # Check for the reserved anonymous form: tail's first token
        # is a numeric literal, not an identifier. v0.3 reserves this
        # syntax — in *code* for v0.4 anonymous temporaries, in *data*
        # it would be anonymous data (also reserved pending a
        # concrete use case; labels always allowed and recommended).
        first_token = tail.split()[0] if tail.split() else ""
        if _looks_like_immediate(first_token) and not _is_ident(first_token):
            raise ParseError(
                line.loc,
                "anonymous declarations reserved for v0.4",
                hint=(
                    f"name the binding explicitly (e.g. "
                    f"'{keyword} tmp {first_token}'); "
                    "in data sections, a label is required"
                ),
            )

        # Check for explicit pinning syntax (only .a storage).
        explicit_reg: Optional[str] = None
        if '=' in tail:
            decl_part, _, reg_part = tail.partition('=')
            decl_part = decl_part.strip()
            explicit_reg = reg_part.strip()
            if storage != Storage.A:
                raise ParseError(
                    line.loc,
                    "explicit register pinning is only valid for .a storage",
                    hint="use .a suffix or remove the '= <reg>'",
                )
            tokens = decl_part.split()
            if len(tokens) != 1:
                raise ParseError(
                    line.loc,
                    "expected: <type>.a <name> = <reg>",
                )
            name = tokens[0]
            initializer = None
        else:
            tokens = tail.split(maxsplit=1)
            name = tokens[0]
            initializer = tokens[1].strip() if len(tokens) > 1 else None

        # Allocate the register and stash the declared-width string
        # on the Binding for later display in the bindings table.
        reg = ctx.alloc.alloc(name, var_type, storage,
                              loc=line.loc, explicit_reg=explicit_reg,
                              declared_width=declared_width)

        # Inline provenance comment at the declaration site.
        if self.emit_provenance:
            storage_label = {
                Storage.T: "temp",
                Storage.S: "saved",
                Storage.A: "arg",
            }[storage]
            # The visible type uses the declared width (i.e. what the
            # user wrote). "int" stays "int", "u8" stays "u8", "f32"
            # stays "f32" — preserves the user's intent.
            ctx.body_lines.append(
                f"    # smola: {name} -> {reg} "
                f"({declared_width}, {storage_label})"
            )

        # Initialization, if present.
        if initializer is not None:
            self._emit_var_init(ctx, line, name, reg, var_type, precision,
                                 initializer)

    def _emit_var_init(self, ctx: FuncCtx, line: Line,
                        name: str, reg: str, var_type: VarType,
                        precision: Optional[str],
                        initializer: str) -> None:
        """Emit the instruction(s) needed to initialize a variable to
        the given immediate.

        Integer / pointer: emit `li reg, value`.
        f32: emit `li tN, bits; fmv.w.x reg, tN` using a transient
              temporary.
        f64: emit a literal-pool entry and `la tN, label; fld reg, 0(tN)`.
        vec: not supported for initialization (no obvious idiom).
        """
        if var_type in (VarType.INT, VarType.PTR):
            # Integer immediate. GAS's `li` pseudo-instruction handles
            # arbitrary-width constants via lui+addi or other sequences.
            ctx.body_lines.append(
                f"    li   {reg}, {initializer}    "
                f"# smola: init {name}"
            )
            return

        if var_type == VarType.FLT:
            # Parse the float literal.
            try:
                fval = float(initializer)
            except ValueError:
                raise ParseError(
                    line.loc,
                    f"expected float literal, got {initializer!r}",
                )
            if precision == "f32":
                self._emit_f32_init(ctx, name, reg, fval, line)
            else:
                self._emit_f64_init(ctx, name, reg, fval, line)
            return

        if var_type == VarType.VEC:
            raise ParseError(
                line.loc,
                "vec variables cannot be initialized at declaration",
                hint="use a vector load or vfmv after declaration",
            )

    def _emit_f32_init(self, ctx: FuncCtx, name: str, reg: str,
                        fval: float, line: Line) -> None:
        """Emit `li tN, <bits>; fmv.w.x reg, tN` for an f32 immediate.

        We need a transient integer temporary. We claim one from the
        T pool, use it, then return it. If the pool is exhausted, error
        — the user is in a corner case where they'd need to zap
        something first.
        """
        # Get the IEEE 754 single-precision bit pattern.
        bits = _struct.unpack('<I', _struct.pack('<f', fval))[0]
        # Allocate a transient temp.
        try:
            tmp_name = f".smola_init_tmp_{ctx.label_counter}"
            ctx.label_counter += 1
            tmp_reg = ctx.alloc.alloc(tmp_name, VarType.INT, Storage.T,
                                       loc=line.loc)
        except RegAllocError:
            raise ParseError(
                line.loc,
                "no integer temporary available for f32 initialization",
                hint=("zap an unused int variable before this declaration"),
            )
        ctx.body_lines.append(
            f"    li   {tmp_reg}, 0x{bits:08x}    "
            f"# smola: init {name} (f32 bit pattern)"
        )
        ctx.body_lines.append(
            f"    fmv.w.x {reg}, {tmp_reg}    "
            f"# smola: init {name}"
        )
        # Release the transient.
        ctx.alloc.zap(tmp_name, loc=line.loc)

    def _emit_f64_init(self, ctx: FuncCtx, name: str, reg: str,
                        fval: float, line: Line) -> None:
        """Emit a literal-pool entry plus `la tN, label; fld reg, 0(tN)`."""
        bits = _struct.unpack('<Q', _struct.pack('<d', fval))[0]
        label = f".Lflt_{ctx.name}_{ctx.label_counter}"
        ctx.label_counter += 1
        ctx.flt_pool.append((label, bits))
        # Need a transient int temp for the address.
        try:
            tmp_name = f".smola_init_tmp_{ctx.label_counter}"
            ctx.label_counter += 1
            tmp_reg = ctx.alloc.alloc(tmp_name, VarType.INT, Storage.T,
                                       loc=line.loc)
        except RegAllocError:
            raise ParseError(
                line.loc,
                "no integer temporary available for f64 initialization",
                hint="zap an unused int variable before this declaration",
            )
        ctx.body_lines.append(
            f"    la   {tmp_reg}, {label}    "
            f"# smola: init {name} (f64 literal pool)"
        )
        ctx.body_lines.append(
            f"    fld  {reg}, 0({tmp_reg})    "
            f"# smola: init {name}"
        )
        ctx.alloc.zap(tmp_name, loc=line.loc)

    # ----- data-section declarations -----

    def _handle_data_decl(self, line: Line) -> None:
        """Handle a type keyword used as a data declaration.

        Syntax in a data section:

            <label>:
                <type>  <value> [<value> ...]
                        [<value> <value> ...]    ; continuation lines

        Where `<type>` is one of i8/u8/i16/u16/i32/u32/i64/u64/f32/
        f64/ptr. `int` and `vec` are deliberately not allowed —
        data must commit to a width.

        Emits:
          1. A `.balign <align>` directive matching the type's
             natural alignment (only when needed: not emitted if the
             current byte position is already aligned, but we
             conservatively always emit it because the byte position
             across `.section` switches is hard to track).
          2. One GAS directive per value (`.byte`, `.hword`, `.word`,
             `.dword`, `.float`, `.double`).
          3. Updates `current_data_label_bytes` so the eventual
             `.size` directive is correct.

        Sets `pending_data_type` so a following DATA_VALUES line is
        recognized as a continuation.

        Errors:
          - `int` or `vec` in data: hint to use a width-typed
            keyword.
          - storage-suffixed forms (`i8.s`, `f32.a`) in data: these
            only make sense in code (they refer to register storage
            classes); reject with a hint.
          - empty tail: data declaration requires at least one value.
          - no preceding label: reserved for v0.4.
        """
        keyword = line.head

        # Storage-suffixed forms are meaningless in data sections.
        if '.' in keyword:
            base, _, suffix = keyword.partition('.')
            raise ParseError(
                line.loc,
                f"storage suffix `.{suffix}` is not valid in a data section",
                hint=(
                    f"use the bare type form (e.g. `{base}` instead of "
                    f"`{keyword}`); storage classes are for code variables"
                ),
            )

        # `int` and `vec` are forbidden in data.
        if keyword == "int":
            raise ParseError(
                line.loc,
                "`int` is not allowed in data sections",
                hint=(
                    "commit to a width: use `i64`/`u64` for 8-byte "
                    "integers, or `i32`/`u32` for 4-byte, etc."
                ),
            )
        if keyword == "vec":
            raise ParseError(
                line.loc,
                "`vec` is not allowed in data sections",
                hint=(
                    "use the underlying scalar type (e.g. `f32` for an "
                    "array of single-precision floats); vector loads "
                    "want element alignment, which the scalar type gives"
                ),
            )

        # Look up the type info.
        if keyword not in DATA_TYPE_INFO:
            # This shouldn't happen — only keywords in VAR_DECL_KEYWORDS
            # reach _handle_var_decl, and the `int`/`vec`/storage-suffix
            # cases were filtered above. Defensive.
            raise ParseError(
                line.loc,
                f"`{keyword}` cannot be used as a data declaration",
                hint=f"valid types: {', '.join(sorted(DATA_TYPE_INFO))}",
            )
        directive, elem_size, elem_align = DATA_TYPE_INFO[keyword]

        # Parse values from the tail.
        if not line.tail.strip():
            raise ParseError(
                line.loc,
                f"`{keyword}` data declaration requires at least one value",
            )
        # Values are whitespace-separated. We don't split on commas
        # because the user may or may not use commas; we accept both.
        values = self._split_data_values(line.tail)
        if not values:
            raise ParseError(
                line.loc,
                f"`{keyword}` data declaration requires at least one value",
            )

        # Require a preceding label. Anonymous data is reserved.
        if self.current_data_label is None:
            raise ParseError(
                line.loc,
                "data declarations require a preceding label",
                hint=(
                    "add a label on the line before the data directive; "
                    "anonymous data is reserved for v0.4"
                ),
            )

        # Emit `.balign` once per directive. This is conservative — we
        # could track byte position and skip the balign when already
        # aligned — but the cost is one zero-byte padding directive
        # that GAS optimizes away anyway in many cases.
        self.output_lines.append(f"    .balign {elem_align}")

        # Emit one directive per value. Each value passes through
        # verbatim — SMOLA doesn't validate float syntax or symbol
        # references; GAS reports any real malformation.
        for v in values:
            self.output_lines.append(f"    {directive} {v}")
        self.current_data_label_bytes += elem_size * len(values)

        # Trailing comment.
        if line.trailing_comment:
            # Attach to the last value line for readability.
            self.output_lines[-1] += f"    {line.trailing_comment}"

        # Set continuation context: subsequent DATA_VALUES lines are
        # values of the same type.
        self.pending_data_type = (directive, elem_size, elem_align, keyword)

    def _handle_data_values(self, line: Line) -> None:
        """Process a DATA_VALUES line (first token was a numeric
        literal).

        Only valid in a data section as a continuation of a previously-
        emitted data directive. Outside that context (in code, or in
        a data section before any directive), error like the lexer
        would have if it didn't recognize the line at all.
        """
        if not _is_data_section(self.current_section):
            raise ParseError(
                line.loc,
                f"unknown mnemonic or keyword {line.head!r}",
                hint=(
                    "numeric literals at the start of a line are only "
                    "valid as data continuation in a data section"
                ),
            )
        if self.pending_data_type is None:
            raise ParseError(
                line.loc,
                "data continuation line with no preceding data directive",
                hint=(
                    "data continuation lines must follow a `<type> <value>` "
                    "directive that establishes the value type"
                ),
            )
        directive, elem_size, elem_align, keyword = self.pending_data_type

        # Re-assemble the values: line.head was the first value
        # (because DATA_VALUES means the first token was a literal),
        # and line.tail is the rest of the line.
        full_text = (line.head + " " + line.tail) if line.tail else line.head
        values = self._split_data_values(full_text)
        if not values:
            # Shouldn't happen — at minimum the head was a value.
            return

        # No new label needed: continuation values accumulate under
        # the same current_data_label.
        if self.current_data_label is None:
            # The label-required check fires at directive-introduction
            # time; if we reach here it means someone deleted the
            # label between directive and continuation. Defensive.
            raise ParseError(
                line.loc,
                "data continuation has no associated label",
            )

        for v in values:
            self.output_lines.append(f"    {directive} {v}")
        self.current_data_label_bytes += elem_size * len(values)

        if line.trailing_comment:
            self.output_lines[-1] += f"    {line.trailing_comment}"

    def _split_data_values(self, text: str) -> List[str]:
        """Split a data-directive tail into individual values.

        Accepts both whitespace-separated and comma-separated formats,
        and a mix. Examples:
          "0.5 0.75 1.0"      -> ["0.5", "0.75", "1.0"]
          "0.5, 0.75, 1.0"    -> ["0.5", "0.75", "1.0"]
          "0.5 0.75, 1.0"     -> ["0.5", "0.75", "1.0"]
          "handler_a handler_b"  -> ["handler_a", "handler_b"]

        Each returned value is a stripped, non-empty token. The
        tokens are passed through to GAS verbatim — SMOLA does not
        validate format (GAS reports any real malformation).
        """
        # Replace commas with spaces, then whitespace-split.
        cleaned = text.replace(',', ' ')
        return [tok for tok in cleaned.split() if tok]

    # ----- string data (str / cstr / txt) -----

    @staticmethod
    def _encode_for_gas(content: str) -> str:
        """Encode a decoded Python string as a GAS .ascii literal body.

        Converts control characters and special chars back to GAS-safe
        escape sequences. The result is suitable for embedding between
        the double quotes of a `.ascii "..."` directive.
        """
        parts = []
        for ch in content:
            if ch == '\\':
                parts.append('\\\\')
            elif ch == '"':
                parts.append('\\"')
            elif ch == '\n':
                parts.append('\\n')
            elif ch == '\t':
                parts.append('\\t')
            elif ch == '\0':
                parts.append('\\000')
            elif ch == '\r':
                parts.append('\\r')
            elif ord(ch) < 32 or ord(ch) == 127:
                parts.append(f'\\{ord(ch):03o}')
            else:
                parts.append(ch)
        return ''.join(parts)

    @staticmethod
    def _parse_quoted_string(tail: str, loc: SourceLoc,
                             keyword: str) -> Tuple[str, int]:
        """Parse a double-quoted string from `tail`.

        Returns (content, byte_count) where content is the decoded
        string value and byte_count is the number of UTF-8 bytes it
        occupies (not counting any NUL terminator — callers add that
        themselves for cstr).

        Supported escapes: \\", \\\\, \\n, \\t, \\0, \\xHH.
        Any other escape is an error.

        Trailing content after the closing `"` is rejected.
        """
        s = tail.strip()
        if not s.startswith('"'):
            raise ParseError(
                loc,
                f"`{keyword}` operand must be a double-quoted string",
                hint=f'example: {keyword} greeting "Hello, world!"',
            )
        i = 1  # skip opening quote
        chars: List[str] = []
        while i < len(s):
            ch = s[i]
            if ch == '"':
                # Closing quote found.
                rest = s[i + 1:].strip()
                if rest:
                    raise ParseError(
                        loc,
                        f"unexpected content after closing quote: {rest!r}",
                    )
                content = "".join(chars)
                byte_count = len(content.encode('utf-8'))
                return content, byte_count
            if ch == '\\':
                if i + 1 >= len(s):
                    raise ParseError(loc, "backslash at end of string")
                esc = s[i + 1]
                if esc == '"':
                    chars.append('"'); i += 2; continue
                if esc == '\\':
                    chars.append('\\'); i += 2; continue
                if esc == 'n':
                    chars.append('\n'); i += 2; continue
                if esc == 't':
                    chars.append('\t'); i += 2; continue
                if esc == '0':
                    chars.append('\0'); i += 2; continue
                if esc == 'x':
                    if i + 3 >= len(s):
                        raise ParseError(
                            loc, r"incomplete \xHH escape sequence",
                        )
                    hex_str = s[i + 2:i + 4]
                    try:
                        chars.append(chr(int(hex_str, 16)))
                    except ValueError:
                        raise ParseError(
                            loc,
                            rf"invalid hex escape \x{hex_str!r}",
                        )
                    i += 4; continue
                raise ParseError(
                    loc,
                    rf"unknown escape sequence \{esc!r}",
                    hint=r"supported: \", \\, \n, \t, \0, \xHH",
                )
            chars.append(ch)
            i += 1
        raise ParseError(loc, "unterminated string literal (missing closing \")")

    def _require_data_section_for_string(self, loc: SourceLoc,
                                         keyword: str) -> None:
        """Raise ParseError if the current section is not a data section.

        Called at the start of str, cstr, and txt handling before parsing
        their operands.
        """
        if not _is_data_section(self.current_section):
            raise ParseError(
                loc,
                f"`{keyword}` is only valid in a data section",
                hint=(
                    "add `.section .rodata` or `.section .data` "
                    "before using string declarations"
                ),
            )

    def _handle_str_decl(self, line: Line) -> None:
        """Handle `str <label_or_quoted> "<content>"`.

        Syntax (in a data section):
            <label>:
                str "content"

        Emits:
            .balign 1
            .ascii "<content>"
            # .size is emitted by _flush_data_label_size via the
            # current_data_label_bytes counter.
        """
        self._require_data_section_for_string(line.loc, "str")
        if self.current_data_label is None:
            raise ParseError(
                line.loc,
                "`str` requires a preceding label",
                hint="add a label on the line before `str`",
            )
        content, byte_count = self._parse_quoted_string(
            line.tail, line.loc, "str"
        )
        gas_content = self._encode_for_gas(content)
        self.output_lines.append("    .balign 1")
        self.output_lines.append(f'    .ascii "{gas_content}"')
        self.current_data_label_bytes += byte_count
        if line.trailing_comment:
            self.output_lines[-1] += f"    {line.trailing_comment}"
        self.pending_data_type = None

    def _handle_cstr_decl(self, line: Line) -> None:
        """Handle `cstr "content"` — NUL-terminated string.

        Like `str` but appends a `.byte 0` and counts +1 byte.
        """
        self._require_data_section_for_string(line.loc, "cstr")
        if self.current_data_label is None:
            raise ParseError(
                line.loc,
                "`cstr` requires a preceding label",
                hint="add a label on the line before `cstr`",
            )
        content, byte_count = self._parse_quoted_string(
            line.tail, line.loc, "cstr"
        )
        gas_content = self._encode_for_gas(content)
        self.output_lines.append("    .balign 1")
        self.output_lines.append(f'    .ascii "{gas_content}"')
        self.output_lines.append("    .byte 0")
        self.current_data_label_bytes += byte_count + 1
        if line.trailing_comment:
            self.output_lines[-2] += f"    {line.trailing_comment}"
        self.pending_data_type = None

    def _handle_txt_block(self, line: Line) -> None:
        """Handle the opening `txt <label_name>` line of a heredoc block.

        The label must already have been emitted via a preceding
        `<label>:` line.  Content lines follow until `eot`.
        """
        self._require_data_section_for_string(line.loc, "txt")
        if self.current_data_label is None:
            raise ParseError(
                line.loc,
                "`txt` requires a preceding label",
                hint="add a label on the line before `txt`",
            )
        if self.txt_in_progress is not None:
            raise ParseError(
                line.loc, "nested txt blocks are not allowed",
            )
        self.txt_in_progress = []
        self.txt_start_loc = line.loc
        self.pending_data_type = None

    def _handle_txt_line(self, line: Line) -> None:
        """Accumulate one content line inside a txt block."""
        if self.txt_in_progress is None:
            raise ParseError(
                line.loc,
                "TXT_LINE seen outside a txt block (internal error)",
            )
        self.txt_in_progress.append(line.tail)

    def _handle_txt_end(self, line: Line) -> None:
        """Emit the accumulated txt block content and close the block."""
        if self.txt_in_progress is None:
            raise ParseError(
                line.loc,
                "`eot` without a matching `txt` block",
                hint="remove stray `eot` or open a `txt` block first",
            )
        lines = self.txt_in_progress
        self.txt_in_progress = None
        self.txt_start_loc = None

        total_bytes = 0
        for content_line in lines:
            gas_content = (content_line
                           .replace('\\', '\\\\')
                           .replace('"', '\\"'))
            self.output_lines.append(f'    .ascii "{gas_content}\\n"')
            total_bytes += len(content_line.encode('utf-8')) + 1  # +1 for \n
        self.current_data_label_bytes += total_bytes
        self.pending_data_type = None

    # ----- zap -----

    def _handle_zap(self, line: Line) -> None:
        """Release one or more named variables, freeing their registers."""
        ctx = self._ensure_func(line)
        names = _split_operands(line.tail)
        if not names:
            raise ParseError(line.loc, "zap requires at least one name")
        for name in names:
            ctx.alloc.zap(name, loc=line.loc)
            if self.emit_provenance:
                ctx.body_lines.append(f"    # smola: zap {name}")

    # ----- field access -----

    def _handle_load_field(self, line: Line) -> None:
        """Emit a field load: read Struct.field from the base pointer into dst."""
        ctx = self._ensure_func(line)
        ops = _split_operands(line.tail)
        if len(ops) != 3:
            raise ParseError(
                line.loc,
                "load_field takes dst, base, Struct.field",
            )
        dst_name, base_name, field_path = ops
        dst = self._resolve_operand(dst_name, line)
        base = self._resolve_operand(base_name, line)
        sdef, f = self.symbols.resolve_field(field_path, line.loc)
        provenance = (
            f"# load_field {dst_name}, {base_name}, {field_path}"
            if self.emit_provenance else ""
        )
        ctx.body_lines.append(
            f"    {f.load_mnemonic:<4} {dst}, {f.offset}({base})    {provenance}"
        )

    def _handle_store_field(self, line: Line) -> None:
        """Emit a field store: write src into Struct.field via the base pointer."""
        ctx = self._ensure_func(line)
        ops = _split_operands(line.tail)
        if len(ops) != 3:
            raise ParseError(
                line.loc,
                "store_field takes src, base, Struct.field",
            )
        src_name, base_name, field_path = ops
        src = self._resolve_operand(src_name, line)
        base = self._resolve_operand(base_name, line)
        sdef, f = self.symbols.resolve_field(field_path, line.loc)
        provenance = (
            f"# store_field {src_name}, {base_name}, {field_path}"
            if self.emit_provenance else ""
        )
        ctx.body_lines.append(
            f"    {f.store_mnemonic:<4} {src}, {f.offset}({base})    {provenance}"
        )

    def _handle_addr_field(self, line: Line) -> None:
        """Compute the address of Struct.field into dst (addi or li+add for large offsets)."""
        ctx = self._ensure_func(line)
        ops = _split_operands(line.tail)
        if len(ops) != 3:
            raise ParseError(
                line.loc,
                "addr_field takes dst, base, Struct.field",
            )
        dst_name, base_name, field_path = ops
        dst = self._resolve_operand(dst_name, line)
        base = self._resolve_operand(base_name, line)
        sdef, f = self.symbols.resolve_field(field_path, line.loc)
        provenance = (
            f"# addr_field {dst_name}, {base_name}, {field_path}"
            if self.emit_provenance else ""
        )
        if -2048 <= f.offset <= 2047:
            ctx.body_lines.append(
                f"    addi {dst}, {base}, {f.offset}    {provenance}"
            )
        else:
            ctx.body_lines.append(
                f"    li   {dst}, {f.offset}    "
                f"{provenance} (offset > 12 bits)"
            )
            ctx.body_lines.append(f"    add  {dst}, {dst}, {base}")

    # ----- SMOLA call (argument-shuffling pseudo) -----

    def _handle_call_pseudo(self, line: Line) -> None:
        """Handle `call target, arg1, arg2, ...` — the SMOLA argument-shuffling pseudo.

        Classifies each argument by its variable type, assigns it to the
        matching ABI register (a0-a7 / fa0-fa7 / v8-v23), and emits the
        moves in a topological order that avoids clobbering a source before
        it has been read.
        """
        ctx = self._ensure_func(line)
        ops = _split_operands(line.tail)
        target = ops[0]
        args = ops[1:]

        # Detect Struct.method form. If the dot-prefixed part is a
        # known struct, emit the mangled symbol.
        if '.' in target:
            sname, mname = target.split('.', 1)
            if self.symbols.has_struct(sname):
                emit_target = f"{sname}_{mname}"
            else:
                emit_target = target  # passthrough; GAS will resolve
        else:
            emit_target = target

        # Classify args by VarType, shuffle to a/fa/v registers.
        int_arg_targets = ["a0", "a1", "a2", "a3",
                           "a4", "a5", "a6", "a7"]
        flt_arg_targets = ["fa0", "fa1", "fa2", "fa3",
                           "fa4", "fa5", "fa6", "fa7"]
        vec_arg_targets = [f"v{i}" for i in range(8, 24)]

        int_idx = 0
        flt_idx = 0
        vec_idx = 0
        # moves: (dst_reg, src_or_imm, kind)
        moves: List[Tuple[str, str, str]] = []

        for arg in args:
            if _looks_like_immediate(arg):
                if int_idx >= len(int_arg_targets):
                    raise ParseError(line.loc,
                                     "too many integer arguments (max 8)")
                moves.append((int_arg_targets[int_idx], arg, "imm"))
                int_idx += 1
                continue
            if ctx.alloc.is_bound(arg):
                b = ctx.alloc.bindings[arg]
                src_reg = b.reg
                if b.var_type in (VarType.INT, VarType.PTR):
                    if int_idx >= len(int_arg_targets):
                        raise ParseError(line.loc, "too many int args")
                    moves.append((int_arg_targets[int_idx], src_reg, "int_mv"))
                    int_idx += 1
                elif b.var_type == VarType.FLT:
                    if flt_idx >= len(flt_arg_targets):
                        raise ParseError(line.loc, "too many flt args")
                    moves.append((flt_arg_targets[flt_idx], src_reg, "flt_mv"))
                    flt_idx += 1
                elif b.var_type == VarType.VEC:
                    if vec_idx >= len(vec_arg_targets):
                        raise ParseError(line.loc, "too many vec args")
                    moves.append((vec_arg_targets[vec_idx], src_reg, "vec_mv"))
                    vec_idx += 1
            else:
                canonical = normalize_reg(arg)
                if canonical is None:
                    raise RegAllocError(
                        line.loc, f"unknown name {arg!r}",
                        hint=("declare it with int/ptr/flt/vec, or "
                              "pass an immediate"),
                    )
                if canonical[0] == 'f':
                    if flt_idx >= len(flt_arg_targets):
                        raise ParseError(line.loc, "too many flt args")
                    moves.append((flt_arg_targets[flt_idx], canonical, "flt_mv"))
                    flt_idx += 1
                elif canonical[0] == 'v':
                    if vec_idx >= len(vec_arg_targets):
                        raise ParseError(line.loc, "too many vec args")
                    moves.append((vec_arg_targets[vec_idx], canonical, "vec_mv"))
                    vec_idx += 1
                else:
                    if int_idx >= len(int_arg_targets):
                        raise ParseError(line.loc, "too many int args")
                    moves.append((int_arg_targets[int_idx], canonical, "int_mv"))
                    int_idx += 1

        # Cycle detection per kind.
        graph = {}
        for dst, src, kind in moves:
            if kind == "imm":
                continue
            if src == dst:
                continue
            graph[src] = dst
        for src in list(graph.keys()):
            seen = set()
            cur = src
            while cur in graph:
                if cur in seen:
                    raise ParseError(
                        line.loc,
                        "argument shuffle has a cycle; "
                        "move one operand to a temporary first",
                    )
                seen.add(cur)
                cur = graph[cur]

        # Topological emit.
        pending = list(moves)
        emitted: List[str] = []
        while pending:
            progressed = False
            for i, (dst, src, kind) in enumerate(pending):
                if kind == "imm":
                    emitted.append(f"li   {dst}, {src}")
                    pending.pop(i)
                    progressed = True
                    break
                others = [m for j, m in enumerate(pending) if j != i]
                conflict = any(
                    o_kind != "imm" and o_src == dst
                    for (_, o_src, o_kind) in others
                )
                if conflict:
                    continue
                if dst != src:
                    if kind == "flt_mv":
                        emitted.append(f"fmv.d {dst}, {src}")
                    elif kind == "vec_mv":
                        emitted.append(f"vmv.v.v {dst}, {src}")
                    else:
                        emitted.append(f"mv   {dst}, {src}")
                pending.pop(i)
                progressed = True
                break
            if not progressed:
                raise ParseError(
                    line.loc, "argument shuffle blocked (smola bug)",
                )

        provenance = (
            f"# call {target}" + (f", {', '.join(args)}" if args else "")
            if self.emit_provenance else ""
        )
        for em in emitted:
            ctx.body_lines.append(f"    {em}")
        ctx.body_lines.append(f"    call {emit_target}    {provenance}")
        ctx.calls_other = True

    # ----- raw escape hatch -----

    def _handle_raw(self, line: Line) -> None:
        """Emit the line's tail verbatim with leading indentation.
        Provenance comment notes the rawness."""
        text = f"    {line.tail}"
        if line.trailing_comment:
            text += f"    {line.trailing_comment}"
        if self.emit_provenance:
            text += "    # raw"
        self._emit_to_current(text)

    # ----- operand resolution with collision detection -----

    def _resolve_operand(self, op: str, line: Line) -> str:
        """Resolve an operand for a SMOLA pseudo-instruction.

        Handles three shapes:
          - `imm(name)` memory operand
          - immediate or local label
          - bare name (resolved) or raw register (collision check)
        """
        ctx = self.current_func
        assert ctx is not None
        # Memory operand.
        m = _MEM_OPERAND_RE.match(op)
        if m:
            imm = m.group(1) or "0"
            base_name = m.group(2)
            if _looks_like_immediate(base_name):
                base = base_name
            else:
                base = self._resolve_bare(base_name, line)
            return f"{imm}({base})"
        # Immediate or label.
        if _looks_like_immediate(op):
            return op
        return self._resolve_bare(op, line)

    def _resolve_bare(self, name: str, line: Line) -> str:
        """Resolve a bare-name operand with collision check.

        If `name` is a raw register currently bound to a variable,
        error. If `name` is a declared label in this function, pass
        it through. Otherwise return the canonical ABI form (for raw
        regs) or the bound register (for SMOLA names).
        """
        ctx = self.current_func
        assert ctx is not None
        canonical = normalize_reg(name)
        if canonical is not None:
            holder = ctx.alloc.reg_holder(canonical)
            if holder is not None:
                raise CollisionError(
                    line.loc,
                    f"register {canonical} is currently bound to "
                    f"variable {holder.name!r}",
                    hint=(
                        f"use {holder.name!r} instead, or "
                        f"`zap {holder.name}` first"
                    ),
                )
            return canonical
        if ctx.alloc.is_bound(name):
            return ctx.alloc.bindings[name].reg
        # Recognized label declared earlier in this function? Pass
        # through. This handles bare `loop` in `bnez counter, loop`.
        if name in ctx.declared_labels:
            return name
        # Forward labels — labels declared *later* in the function —
        # are accepted too if they look like identifiers. This is a
        # small concession: the alternative would require a two-pass
        # walk to collect labels first. We accept any identifier-
        # shaped name in branch-operand position as a probable label
        # rather than a typo. GAS will catch genuinely-undefined
        # references at link time with a much better diagnostic than
        # SMOLA could give.
        if _is_ident(name):
            return name
        return ctx.alloc.resolve(name, line.loc)

    # ----- output helpers -----

    def _emit_to_current(self, text: str) -> None:
        """Emit text into the current function's body buffer, or to
        the top-level output if no function is active."""
        if self.current_func is not None:
            self.current_func.body_lines.append(text)
        else:
            self.output_lines.append(text)

    def _ensure_func(self, line: Line) -> FuncCtx:
        if self.current_func is None:
            raise FrameError(
                line.loc,
                f"`{line.head}` must appear inside a function",
                hint="open a function with `func`",
            )
        return self.current_func

    def _emit_file_header(self) -> None:
        """Emit the "Generated by SMOLA" provenance header and a blank separator line."""
        self.output_lines.append(
            f"# Generated by SMOLA v{__version__} from {self.filename}"
        )
        self.output_lines.append(
            "# Do not edit -- regenerate from the .smola source."
        )
        self.output_lines.append("")


def _fold_multiline_structs(source: str) -> str:
    """Join multi-line `struct` declarations onto a single line before
    lexing. Field lines like `    x: i64,` would otherwise lex as
    labels and confuse the parser. Blank placeholder lines preserve
    line numbering for downstream errors."""
    out = []
    src_lines = source.splitlines(keepends=False)
    i = 0
    while i < len(src_lines):
        line = src_lines[i]
        stripped = line.strip()
        if (stripped.startswith('struct')
                and '{' in stripped and '}' not in stripped):
            buf = stripped
            consumed = 1
            j = i + 1
            found = False
            while j < len(src_lines):
                buf += " " + src_lines[j].strip()
                consumed += 1
                if '}' in src_lines[j]:
                    found = True
                    break
                j += 1
            if not found:
                out.append(line)
                i += 1
                continue
            out.append(buf)
            for _ in range(consumed - 1):
                out.append("")
            i += consumed
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def _is_ident(s: str) -> bool:
    """Local helper: C-style identifier check."""
    if not s:
        return False
    if not (s[0].isalpha() or s[0] == '_'):
        return False
    return all(c.isalnum() or c == '_' for c in s)
