"""SMOLA translator.

Top-level orchestration:
  - lex the source
  - walk lines, maintaining global state (symbol table) and per-function
    state (allocator, body buffer, frame info)
  - on .smola.endfunc, run the frame planner and stitch prologue +
    body + epilogue together
  - emit a complete .s file

The translator is stateful but linear: it walks lines in order. No
look-ahead, no backtracking. The buffered body is rewritten only by
prepending the prologue.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from . import __version__
from .errors import (FrameError, LexError, ParseError, RegAllocError,
                     SmolaError, SourceLoc, StructError)
from .frame import FramePlan, emit_epilogue, emit_prologue, plan_frame
from .lexer import Line, LineKind, lex_source
from .regalloc import Allocator, RegKind, normalize_reg
from .symbols import StructDef, SymbolTable, define_struct


# Regex for parsing memory operands like "0(self)" or "-4(sp)".
_MEM_OPERAND_RE = re.compile(r'^\s*([+-]?(?:0x[0-9a-fA-F]+|\d+|[A-Za-z_][\w]*))\s*\(\s*([A-Za-z_]\w*)\s*\)\s*$')


def _split_operands(tail: str) -> List[str]:
    """Split a comma-separated operand list, respecting parens.

    Examples:
        "a, b, c"          -> ["a", "b", "c"]
        "x, 0(self)"       -> ["x", "0(self)"]
        ""                  -> []
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


@dataclass
class FuncCtx:
    """Per-function state. Created at .smola.func, destroyed at .smola.endfunc."""
    name: str
    is_global: bool
    declared_at: SourceLoc
    alloc: Allocator = field(default_factory=Allocator)
    body_lines: List[str] = field(default_factory=list)
    calls_other: bool = False
    user_spill_bytes: int = 0
    # Header lines that were emitted at .smola.func time (section,
    # globl, type, balign, label). The prologue gets inserted AFTER
    # these but BEFORE the body.
    header_lines: List[str] = field(default_factory=list)
    # Trailer: .size directive emitted at endfunc time.


class Translator:
    """Translates a SMOLA source string into a GAS .s source string."""

    def __init__(self, filename: str = "<input>", emit_provenance: bool = True):
        self.filename = filename
        self.emit_provenance = emit_provenance
        self.symbols = SymbolTable()
        self.current_func: Optional[FuncCtx] = None
        # All output, in order, fully formed.
        self.output_lines: List[str] = []

    # ----- public entry -----

    def translate(self, source: str) -> str:
        self._emit_file_header()
        # Pre-pass: fold multi-line .smola.struct declarations into one
        # line before lexing. This avoids the lexer trying to interpret
        # the inner "field: type," lines as labels.
        source = _fold_multiline_structs(source)
        lines = lex_source(self.filename, source)
        for line in lines:
            self._process_line(line)

        if self.current_func is not None:
            raise FrameError(
                self.current_func.declared_at,
                f"function {self.current_func.name!r} was never closed",
                hint="add a matching .smola.endfunc or .smola.endmethod",
            )

        return "\n".join(self.output_lines) + "\n"

    # ----- line dispatch -----

    def _process_line(self, line: Line) -> None:
        if line.kind == LineKind.BLANK:
            self._emit_to_current("")
            return

        if line.kind == LineKind.COMMENT:
            # Normalize // -> # for GAS.
            text = line.tail
            if text.startswith('//'):
                text = '#' + text[2:]
            self._emit_to_current(text)
            return

        if line.kind == LineKind.PASSTHROUGH:
            self._emit_to_current(line.tail)
            return

        if line.kind == LineKind.SMOLA_DIRECTIVE:
            self._handle_smola_directive(line)
            return

        if line.kind == LineKind.GAS_DIRECTIVE:
            self._emit_to_current(self._format_passthrough(line))
            return

        if line.kind == LineKind.LABEL:
            self._emit_to_current(f"{line.head}:" + self._fmt_trail(line))
            return

        if line.kind == LineKind.INSN_RAW:
            # Track if it's a call so the frame planner knows.
            if line.head in ("call", "jal", "tail"):
                if self.current_func is not None:
                    # 'jal ra, target' implies ra-clobber; 'jal x0, target'
                    # does not. Be conservative: any jal counts.
                    self.current_func.calls_other = True
            self._emit_to_current(self._format_passthrough(line))
            return

        if line.kind == LineKind.INSN_SMOLA:
            self._handle_smola_insn(line)
            return

        raise ParseError(line.loc, f"unhandled line kind {line.kind}")

    # ----- SMOLA directive handling -----

    def _handle_smola_directive(self, line: Line) -> None:
        head = line.head
        if head in ("func", "method"):
            self._open_func(line, is_method=(head == "method"))
        elif head in ("endfunc", "endmethod"):
            self._close_func(line)
        elif head == "struct":
            self._declare_struct(line)
        elif head == "stack":
            self._set_user_spill(line)
        else:
            raise ParseError(
                line.loc,
                f"unknown SMOLA directive .smola.{head}",
            )

    def _open_func(self, line: Line, is_method: bool) -> None:
        if self.current_func is not None:
            raise FrameError(
                line.loc,
                f"nested function definitions are not allowed "
                f"(currently inside {self.current_func.name!r})",
            )
        # Parse "<name>" optionally followed by "static".
        parts = line.tail.split()
        if not parts:
            raise ParseError(line.loc, "expected function name")
        name = parts[0]
        is_global = True
        if len(parts) > 1:
            if parts[1] == "static":
                is_global = False
            else:
                raise ParseError(
                    line.loc,
                    f"unknown modifier {parts[1]!r}",
                    hint="only 'static' is recognized",
                )
        # For methods, the name has a '.' which becomes '_' in the
        # emitted symbol.
        if is_method:
            if '.' not in name:
                raise ParseError(
                    line.loc,
                    "method name must be Struct.name",
                )
            struct_name, method_name = name.split('.', 1)
            # Verify the struct exists. We don't *require* it -- a method
            # could be declared on a struct that's defined later, but
            # v1 enforces declare-before-use for clarity.
            self.symbols.get_struct(struct_name, line.loc)
            emit_name = f"{struct_name}_{method_name}"
        else:
            emit_name = name

        ctx = FuncCtx(
            name=emit_name,
            is_global=is_global,
            declared_at=line.loc,
        )
        # Build the header lines.
        header: List[str] = []
        header.append("")
        header.append(f"    .section .text.{emit_name}, \"ax\", @progbits")
        if is_global:
            header.append(f"    .globl  {emit_name}")
        header.append(f"    .type   {emit_name}, @function")
        header.append("    .balign 2")
        header.append(f"{emit_name}:")
        ctx.header_lines = header

        # For methods, implicitly bind 'self' to a0.
        if is_method:
            ctx.alloc.alloc_A("self", explicit_reg="a0", loc=line.loc)
            if self.emit_provenance:
                ctx.body_lines.append(
                    "    # smola: bind self -> a0  (argument, implicit)"
                )

        self.current_func = ctx

    def _close_func(self, line: Line) -> None:
        if self.current_func is None:
            raise FrameError(
                line.loc,
                ".smola.endfunc / .smola.endmethod without matching open",
            )
        ctx = self.current_func
        # Plan the frame.
        plan = plan_frame(
            saved_s_regs=set(ctx.alloc.saved_S),
            calls_other=ctx.calls_other,
            user_spill_bytes=ctx.user_spill_bytes,
        )
        # Stitch together.
        out = list(ctx.header_lines)
        if plan.frame_size > 0 or plan.save_ra:
            for pl in emit_prologue(plan):
                out.append(pl)
        out.extend(ctx.body_lines)
        for el in emit_epilogue(plan):
            out.append(el)
        out.append(f"    .size {ctx.name}, .-{ctx.name}")
        out.append("")
        self.output_lines.extend(out)
        self.current_func = None

    def _declare_struct(self, line: Line) -> None:
        # Parse: <Name> { <field>: <type>, <field>: <type>, ... }
        text = line.tail.strip()
        # Find '{' and '}'.
        if '{' not in text or '}' not in text:
            raise StructError(
                line.loc,
                "struct declaration must be: Name { field: type, ... }",
            )
        name_part, _, rest = text.partition('{')
        body, _, _ = rest.partition('}')
        name = name_part.strip()
        if not name:
            raise StructError(line.loc, "struct must have a name")
        fields_raw: List[Tuple[str, str]] = []
        for field_text in body.split(','):
            ft = field_text.strip()
            if not ft:
                continue
            if ':' not in ft:
                raise StructError(
                    line.loc,
                    f"field {ft!r} must be name: type",
                )
            fname, _, tname = ft.partition(':')
            fields_raw.append((fname.strip(), tname.strip()))
        if not fields_raw:
            raise StructError(line.loc, f"struct {name!r} has no fields")
        sdef = define_struct(name, fields_raw, loc=line.loc)
        self.symbols.add_struct(sdef)
        # Emit GAS .set lines for the offsets so user pass-through code
        # can reference them.
        if self.emit_provenance:
            self.output_lines.append(f"    # smola: struct {name} ({sdef.size} bytes, align {sdef.align})")
        for f in sdef.fields:
            self.output_lines.append(
                f"    .set {name}_{f.name}_offset, {f.offset}"
            )
        self.output_lines.append(f"    .set {name}_size, {sdef.size}")
        self.output_lines.append(f"    .set {name}_align, {sdef.align}")
        self.output_lines.append("")

    def _set_user_spill(self, line: Line) -> None:
        if self.current_func is None:
            raise FrameError(
                line.loc,
                ".smola.stack must appear inside a function",
            )
        try:
            n = int(line.tail.strip(), 0)
        except ValueError:
            raise ParseError(
                line.loc,
                f"expected integer byte count, got {line.tail!r}",
            )
        if n < 0:
            raise ParseError(line.loc, "stack size must be non-negative")
        self.current_func.user_spill_bytes = n

    # ----- SMOLA pseudo-instruction handling -----

    def _handle_smola_insn(self, line: Line) -> None:
        head = line.head
        operands = _split_operands(line.tail)

        if head in ("VAR.T", "VAR.S", "VAR.A", "VAR.RET", "VAR.ALIAS"):
            self._handle_var_directive(head, operands, line)
            return
        if head == "FREE":
            self._handle_free(operands, line)
            return
        if head == "LOAD_FIELD":
            self._handle_load_field(operands, line)
            return
        if head == "STORE_FIELD":
            self._handle_store_field(operands, line)
            return
        if head == "LA_FIELD":
            self._handle_la_field(operands, line)
            return
        if head == "CALL":
            self._handle_call(operands, line)
            return

        # Generic pseudo-instruction: substitute names with registers.
        self._handle_generic_insn(line, operands)

    def _ensure_func(self, line: Line) -> FuncCtx:
        if self.current_func is None:
            raise FrameError(
                line.loc,
                f"{line.head} must appear inside a function",
                hint="open a function with .smola.func or .smola.method",
            )
        return self.current_func

    def _handle_var_directive(self, head: str, operands: List[str], line: Line) -> None:
        ctx = self._ensure_func(line)
        if head == "VAR.T":
            if len(operands) != 1:
                raise ParseError(line.loc, "VAR.T takes exactly one name")
            name = operands[0]
            reg = ctx.alloc.alloc_T(name, loc=line.loc)
            if self.emit_provenance:
                ctx.body_lines.append(
                    f"    # smola: bind {name} -> {reg}  (caller-saved)"
                )
        elif head == "VAR.S":
            if len(operands) != 1:
                raise ParseError(line.loc, "VAR.S takes exactly one name")
            name = operands[0]
            reg = ctx.alloc.alloc_S(name, loc=line.loc)
            if self.emit_provenance:
                ctx.body_lines.append(
                    f"    # smola: bind {name} -> {reg}  (callee-saved, frame slot reserved)"
                )
        elif head == "VAR.A":
            if len(operands) == 1:
                name = operands[0]
                reg = ctx.alloc.alloc_A(name, loc=line.loc)
            elif len(operands) == 2:
                name, explicit = operands
                reg = ctx.alloc.alloc_A(name, explicit_reg=explicit, loc=line.loc)
            else:
                raise ParseError(line.loc, "VAR.A takes name [, register]")
            if self.emit_provenance:
                ctx.body_lines.append(
                    f"    # smola: bind {name} -> {reg}  (argument)"
                )
        elif head == "VAR.RET":
            if len(operands) != 1:
                raise ParseError(line.loc, "VAR.RET takes exactly one name")
            name = operands[0]
            reg = ctx.alloc.alloc_A(name, explicit_reg="a0", loc=line.loc)
            if self.emit_provenance:
                ctx.body_lines.append(
                    f"    # smola: bind {name} -> {reg}  (return value)"
                )
        elif head == "VAR.ALIAS":
            # Syntax: VAR.ALIAS new = old
            joined = ", ".join(operands)
            if '=' not in joined:
                raise ParseError(line.loc, "VAR.ALIAS syntax: VAR.ALIAS new = old")
            new_name, _, old_name = joined.partition('=')
            new_name = new_name.strip()
            old_name = old_name.strip()
            reg = ctx.alloc.alias(new_name, old_name, loc=line.loc)
            if self.emit_provenance:
                ctx.body_lines.append(
                    f"    # smola: alias {new_name} -> {reg}  (same as {old_name})"
                )

    def _handle_free(self, operands: List[str], line: Line) -> None:
        ctx = self._ensure_func(line)
        for name in operands:
            ctx.alloc.free(name, loc=line.loc)
            if self.emit_provenance:
                ctx.body_lines.append(f"    # smola: free {name}")

    def _handle_load_field(self, operands: List[str], line: Line) -> None:
        # LOAD_FIELD dst, base, Struct.field
        ctx = self._ensure_func(line)
        if len(operands) != 3:
            raise ParseError(
                line.loc,
                "LOAD_FIELD takes dst, base, Struct.field",
            )
        dst_name, base_name, field_path = operands
        dst = ctx.alloc.resolve(dst_name, line.loc)
        base = ctx.alloc.resolve(base_name, line.loc)
        sdef, f = self.symbols.resolve_field(field_path, line.loc)
        provenance = (f"# LOAD_FIELD {dst_name}, {base_name}, {field_path}"
                      if self.emit_provenance else "")
        ctx.body_lines.append(
            f"    {f.load_mnemonic:<4} {dst}, {f.offset}({base})    {provenance}"
        )

    def _handle_store_field(self, operands: List[str], line: Line) -> None:
        ctx = self._ensure_func(line)
        if len(operands) != 3:
            raise ParseError(
                line.loc,
                "STORE_FIELD takes src, base, Struct.field",
            )
        src_name, base_name, field_path = operands
        src = ctx.alloc.resolve(src_name, line.loc)
        base = ctx.alloc.resolve(base_name, line.loc)
        sdef, f = self.symbols.resolve_field(field_path, line.loc)
        provenance = (f"# STORE_FIELD {src_name}, {base_name}, {field_path}"
                      if self.emit_provenance else "")
        ctx.body_lines.append(
            f"    {f.store_mnemonic:<4} {src}, {f.offset}({base})    {provenance}"
        )

    def _handle_la_field(self, operands: List[str], line: Line) -> None:
        ctx = self._ensure_func(line)
        if len(operands) != 3:
            raise ParseError(
                line.loc,
                "LA_FIELD takes dst, base, Struct.field",
            )
        dst_name, base_name, field_path = operands
        dst = ctx.alloc.resolve(dst_name, line.loc)
        base = ctx.alloc.resolve(base_name, line.loc)
        sdef, f = self.symbols.resolve_field(field_path, line.loc)
        provenance = (f"# LA_FIELD {dst_name}, {base_name}, {field_path}"
                      if self.emit_provenance else "")
        if -2048 <= f.offset <= 2047:
            ctx.body_lines.append(
                f"    addi {dst}, {base}, {f.offset}    {provenance}"
            )
        else:
            # Multi-instruction sequence. For v1, we delegate to the
            # assembler's pseudo-op behavior: use 'li' + 'add'.
            ctx.body_lines.append(
                f"    li   {dst}, {f.offset}    {provenance} (high offset)"
            )
            ctx.body_lines.append(
                f"    add  {dst}, {dst}, {base}"
            )

    def _handle_call(self, operands: List[str], line: Line) -> None:
        # CALL <target>, arg1, arg2, ...
        ctx = self._ensure_func(line)
        if len(operands) < 1:
            raise ParseError(line.loc, "CALL takes a target and zero or more arguments")
        target = operands[0]
        args = operands[1:]
        # If target contains a '.', treat as Struct.method.
        if '.' in target:
            struct_name, method_name = target.split('.', 1)
            # Verify the struct exists.
            self.symbols.get_struct(struct_name, line.loc)
            emit_target = f"{struct_name}_{method_name}"
        else:
            emit_target = target

        # Plan argument moves. For each arg i, we want it in a<i>.
        # First, resolve each arg name to its current register (or
        # accept that it's an immediate or label).
        target_regs = [f"a{i}" for i in range(len(args))]
        if len(args) > 8:
            raise ParseError(
                line.loc,
                f"CALL with {len(args)} args; v1 supports at most 8 in a0..a7",
            )

        # Resolve sources. A source can be a bound name, a raw register,
        # or an integer literal. Strings starting with a digit or '-' are
        # treated as immediates; we emit 'li' for those.
        moves: List[Tuple[str, str, bool]] = []  # (dst, src_or_imm, is_imm)
        for arg, dst in zip(args, target_regs):
            if _looks_like_immediate(arg):
                moves.append((dst, arg, True))
            else:
                src = ctx.alloc.resolve(arg, line.loc)
                moves.append((dst, src, False))

        # Cycle detection: build a graph dst<-src and look for cycles.
        # For v1 we only need to detect; we don't resolve.
        # Build map of register sources to register dests.
        graph = {}  # src_reg -> dst_reg
        for dst, src, is_imm in moves:
            if is_imm:
                continue
            if src == dst:
                continue
            graph[src] = dst
        # Detect cycles by walking from each src.
        for src in list(graph.keys()):
            seen = set()
            cur = src
            while cur in graph:
                if cur in seen:
                    raise ParseError(
                        line.loc,
                        "argument shuffle has a cycle; v1 cannot resolve "
                        "this. Move one operand to a temporary first.",
                    )
                seen.add(cur)
                cur = graph[cur]

        # Emit moves. Naive: for now, emit in order. This is safe only
        # when no later move clobbers an earlier source. To be safe,
        # we use the standard topological emit: repeatedly emit moves
        # whose dst is not currently a source, then break ties.
        pending = list(moves)
        emitted: List[str] = []
        # Determine all current sources.
        while pending:
            progressed = False
            for i, (dst, src, is_imm) in enumerate(pending):
                if is_imm:
                    emitted.append(f"li   {dst}, {src}")
                    pending.pop(i)
                    progressed = True
                    break
                # Check if dst is the source of any remaining move.
                others = [m for j, m in enumerate(pending) if j != i]
                conflict = any((not o_imm) and o_src == dst
                               for (_, o_src, o_imm) in others)
                if not conflict:
                    if dst != src:
                        emitted.append(f"mv   {dst}, {src}")
                    pending.pop(i)
                    progressed = True
                    break
            if not progressed:
                # Should have been caught by cycle detection.
                raise ParseError(
                    line.loc,
                    "argument shuffle blocked; this is a SMOLA bug if "
                    "cycle detection above missed it.",
                )

        provenance = f"# CALL {target}, {', '.join(args)}" if self.emit_provenance else ""
        for em in emitted:
            ctx.body_lines.append(f"    {em}")
        ctx.body_lines.append(f"    call {emit_target}    {provenance}")
        ctx.calls_other = True

    def _handle_generic_insn(self, line: Line, operands: List[str]) -> None:
        ctx = self._ensure_func(line)
        # Substitute each operand. Operands may be:
        #   - a bare name -> resolve to register
        #   - a memory operand 'imm(name)' -> resolve the name
        #   - a label, immediate, or raw register -> pass through
        new_operands: List[str] = []
        for op in operands:
            new_operands.append(self._substitute_operand(op, line))
        mnemonic = line.head.lower()
        provenance = ""
        if self.emit_provenance:
            provenance = f"# {line.head} {line.tail}"
        joined = ", ".join(new_operands)
        ctx.body_lines.append(f"    {mnemonic:<4} {joined}    {provenance}")

    def _substitute_operand(self, op: str, line: Line) -> str:
        ctx = self.current_func
        assert ctx is not None
        # Memory operand?
        m = _MEM_OPERAND_RE.match(op)
        if m:
            imm = m.group(1)
            base_name = m.group(2)
            # If the inner name is a known binding or raw register,
            # resolve it. If it's a label-like immediate, pass through.
            # If it's an unknown name, error.
            if _looks_like_immediate(base_name):
                base = base_name
            else:
                base = ctx.alloc.resolve(base_name, line.loc)
            return f"{imm}({base})"
        # Numeric immediate or local label (starts with '.')?
        if _looks_like_immediate(op):
            return op
        # Raw register name?
        if normalize_reg(op) is not None:
            return ctx.alloc.resolve(op, line.loc)
        # Otherwise: must be a bound name, or error.
        if ctx.alloc.is_bound(op):
            return ctx.alloc.resolve(op, line.loc)
        # Final fallback: unresolved. Report a clean error rather than
        # silently passing the name through as a label.
        raise RegAllocError(
            line.loc,
            f"unknown name {op!r}",
            hint=(
                "declare it with VAR.T/VAR.S/VAR.A first, "
                "or use the '!' escape hatch for raw assembly with global labels"
            ),
        )

    # ----- output helpers -----

    def _emit_to_current(self, text: str) -> None:
        if self.current_func is not None:
            self.current_func.body_lines.append(text)
        else:
            self.output_lines.append(text)

    def _format_passthrough(self, line: Line) -> str:
        # Indent instructions, but leave directives/labels at column 0.
        if line.kind in (LineKind.INSN_RAW,):
            body = f"    {line.head}"
            if line.tail:
                body += f" {line.tail}"
        elif line.kind == LineKind.GAS_DIRECTIVE:
            body = f"    {line.head}"
            if line.tail:
                body += f" {line.tail}"
        else:
            body = line.head + (f" {line.tail}" if line.tail else "")
        if line.trailing_comment:
            body += f"    {line.trailing_comment}"
        return body

    def _fmt_trail(self, line: Line) -> str:
        return f"    {line.trailing_comment}" if line.trailing_comment else ""

    def _emit_file_header(self) -> None:
        self.output_lines.append(f"# Generated by SMOLA v{__version__} from {self.filename}")
        self.output_lines.append("# Do not edit -- regenerate from the .smola source.")
        self.output_lines.append("")


def _fold_multiline_structs(source: str) -> str:
    """Join multi-line .smola.struct declarations onto a single line.

    The lexer cannot handle field lines like '    x: i64,' because they
    look like labels. We fold them before lexing.

    Brace-depth tracking is line-based and shallow: we only need to
    handle one '{' ... '}' per struct, no nesting.
    """
    out_lines = []
    src_lines = source.splitlines(keepends=False)
    i = 0
    while i < len(src_lines):
        line = src_lines[i]
        stripped = line.strip()
        if (stripped.startswith('.smola.struct')
                and '{' in stripped and '}' not in stripped):
            # Accumulate until '}' is seen on some line. Each
            # accumulated line is appended after a space, preserving
            # field separation. We also emit blank placeholder lines
            # for skipped originals so source line numbers stay aligned
            # for any errors emitted AFTER the struct.
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
                # Let the lexer/parser report this as an unclosed
                # struct on the original line; we leave the source
                # unchanged.
                out_lines.append(line)
                i += 1
                continue
            out_lines.append(buf)
            for _ in range(consumed - 1):
                out_lines.append("")
            i += consumed
            continue
        out_lines.append(line)
        i += 1
    return "\n".join(out_lines)


def _looks_like_immediate(s: str) -> bool:
    """Heuristic: does this operand look like a numeric immediate or label?"""
    s = s.strip()
    if not s:
        return False
    if s[0] in '-+':
        rest = s[1:]
    else:
        rest = s
    if rest.startswith('0x') or rest.startswith('0X'):
        return all(c in '0123456789abcdefABCDEF' for c in rest[2:])
    if rest and rest[0].isdigit():
        return rest.isdigit()
    # Labels starting with '.' (e.g. .Ldone) — also treated as immediates
    # (i.e. pass-through unchanged).
    if s.startswith('.'):
        return True
    return False
