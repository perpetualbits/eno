#!/usr/bin/env python3
"""
tools/spine/expand.py — SPINE v0.2 Prototype A expander.

Reads a .spine text file, parses the six core ops (DEF, USE, SET, MOD,
LNK, GRP), applies reachability pruning from `demo_root`, and expands
the result into a flat global-time event list using the v0.2 music
dialect.

Deliberately minimal. No grammar generator, no AST classes, no plugin
system — just enough to make Prototype A produce a diffable expansion.

Architecture (matches the layering in spine_core_v0_2_design.md):

    Parser              dialect-blind. Produces a Statement list.
    Definition table    DEFs and MODs collected, indexed by id.
    Reachability        walks from demo_root, marks reachable ids.
    Expander            evaluates GRPs into global-time events using
                        the music dialect for everything music.*.

Usage:
    python3 expand.py path/to/file.spine
    python3 expand.py path/to/file.spine --root demo_root
    python3 expand.py path/to/file.spine --dump-reachable
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from typing import Any


# =====================================================================
# Tokenizer + parser. Dialect-blind. Knows only the six core ops and
# the textual format from §7 of the design doc.
# =====================================================================

# A statement is the parsed form of one line (or one GRP block). The
# `kind` field tells the rest of the pipeline which fields are meaningful.
@dataclass
class Statement:
    kind: str                      # "DEF" | "USE" | "SET" | "MOD" | "LNK" | "GRP"
    id: str | None = None          # primary id (DEF id, MOD new_id, USE entity_id, GRP id)
    type_id: str | None = None     # DEF domain.type
    params: dict[str, Any] = field(default_factory=dict)  # DEF params or USE overrides
    instance_id: str | None = None # USE "as <id>"
    at: float | None = None        # USE at
    dur: float | None = None       # USE dur
    loc: str | None = None         # USE loc
    src_id: str | None = None      # MOD source
    ops: list[tuple[str, Any]] = field(default_factory=list)  # MOD ops: [(name, args), ...]
    set_target: str | None = None  # SET target.param
    set_param: str | None = None
    set_value: Any = None
    lnk_src: str | None = None     # LNK source port
    lnk_dst: str | None = None     # LNK destination port
    children: list["Statement"] = field(default_factory=list)  # GRP contents
    seed: int | None = None        # GRP seed attribute (v0.3)


def strip_comments(text: str) -> str:
    """Remove # comments and process line continuations.

    A backslash at end of line (after comment removal) means "join
    with the next line." This lets long MOD chains span multiple
    lines for readability:

        MOD vib_decel = base_vibrato_warm decelerando 0.7 \\
                                          with_depth ref(fall_smooth)
    """
    out = []
    for line in text.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        out.append(line)
    joined = "\n".join(out)
    # Process backslash-newline continuations.
    joined = re.sub(r"\\\s*\n\s*", " ", joined)
    return joined


# Token classes for the value lexer. Strings are kept simple; expressions
# are explicitly deferred per design §4.4.
_NUMBER_RE = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")


def parse_value(tok: str) -> Any:
    """Parse a single parameter value token.

    Supports the v0.2 value types from §4.4:
      int, float, symbol, reference, vector, string.
    """
    tok = tok.strip()
    if not tok:
        raise ValueError("empty value")
    if tok.startswith('"') and tok.endswith('"'):
        return tok[1:-1]
    if tok.startswith("[") and tok.endswith("]"):
        inner = tok[1:-1].strip()
        if not inner:
            return []
        # Split on commas, respecting nothing fancier than that. Vectors
        # in v0.2 hold ints, floats, or symbols. No nested vectors.
        return [parse_value(p) for p in _split_top_level(inner, ",")]
    if tok.startswith("ref(") and tok.endswith(")"):
        return ("ref", tok[4:-1].strip())
    if _NUMBER_RE.match(tok):
        # Prefer int when possible — keeps `mute=[2]` etc. clean.
        if any(c in tok for c in ".eE"):
            return float(tok)
        return int(tok)
    # Otherwise it's a bare symbol (pitch name, enum, etc.).
    return tok


def _split_top_level(s: str, sep: str) -> list[str]:
    """Split on `sep` while respecting [...] and "..." nesting."""
    out, depth, in_str, start = [], 0, False, 0
    for i, c in enumerate(s):
        if in_str:
            if c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        elif c == sep and depth == 0:
            out.append(s[start:i].strip())
            start = i + 1
    tail = s[start:].strip()
    if tail:
        out.append(tail)
    return out


def parse_param_block(text: str) -> dict[str, Any]:
    """Parse the contents of a `{ k=v k=v }` block (already brace-stripped).

    Accepts whitespace around `=` and between pairs. Values may contain
    nested brackets, quoted strings, signed numbers, and bare symbols.
    """
    params: dict[str, Any] = {}
    text = text.strip()
    if not text:
        return params
    # Tokenize key=value pairs by scanning: read a key (word chars),
    # skip whitespace, expect `=`, skip whitespace, read a value (one
    # token, respecting brackets and strings).
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        # Read key.
        key_start = i
        while i < n and (text[i].isalnum() or text[i] == "_"):
            i += 1
        if i == key_start:
            raise SyntaxError(f"expected key at offset {i} in {text!r}")
        key = text[key_start:i]
        # Skip whitespace, expect `=`.
        while i < n and text[i].isspace():
            i += 1
        if i >= n or text[i] != "=":
            raise SyntaxError(f"expected '=' after {key!r} in {text!r}")
        i += 1
        # Skip whitespace, read value (one balanced token).
        while i < n and text[i].isspace():
            i += 1
        value_start = i
        i = _read_value_token(text, i, n)
        params[key] = parse_value(text[value_start:i].strip())
    return params


def _read_value_token(text: str, start: int, end: int) -> int:
    """Read one value token starting at `start`, return index after it.

    A value token is: a quoted string, a bracketed vector, or a bare
    word/number. Stops at unquoted whitespace at depth 0.
    """
    i = start
    depth = 0
    in_str = False
    while i < end:
        c = text[i]
        if in_str:
            if c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
            i += 1
            continue
        if c == "[":
            depth += 1
            i += 1
            continue
        if c == "]":
            depth -= 1
            i += 1
            continue
        if c.isspace() and depth == 0:
            break
        i += 1
    return i


def _split_pairs(s: str) -> list[str]:
    """Split `k=v k=v` on whitespace, respecting brackets and strings."""
    out, depth, in_str, start = [], 0, False, 0
    i = 0
    while i < len(s):
        c = s[i]
        if in_str:
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        elif c.isspace() and depth == 0:
            piece = s[start:i].strip()
            if piece:
                out.append(piece)
            start = i + 1
        i += 1
    tail = s[start:].strip()
    if tail:
        out.append(tail)
    return out


def extract_braced(text: str, start: int) -> tuple[str, int]:
    """Given text and the index of '{', return (inner, index_after_close)."""
    assert text[start] == "{"
    depth, in_str, i = 0, False, start
    while i < len(text):
        c = text[i]
        if in_str:
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    raise SyntaxError("unclosed '{'")


def parse(text: str) -> list[Statement]:
    """Top-level parse. Returns a flat list of Statements; GRPs hold children."""
    text = strip_comments(text)
    pos = 0
    return _parse_block(text, pos, len(text))[0]


def _parse_block(text: str, pos: int, end: int) -> tuple[list[Statement], int]:
    """Parse statements between pos and end. Returns (statements, new_pos)."""
    stmts: list[Statement] = []
    while pos < end:
        # Skip whitespace.
        while pos < end and text[pos].isspace():
            pos += 1
        if pos >= end:
            break
        # Find the end of this statement: either a newline (for simple
        # statements) or the end of a `{...}` block (for DEF with params,
        # USE with overrides, or GRP).
        # Strategy: read the line up to newline; if the line contains an
        # unmatched `{`, extend to its matching `}`.
        line_start = pos
        nl = text.find("\n", pos)
        if nl < 0:
            nl = end
        line = text[line_start:nl]
        # Check for a brace-opening that extends past the newline.
        brace_pos = _find_unquoted(line, "{")
        if brace_pos >= 0:
            # Extract the full braced section, possibly spanning lines.
            abs_brace = line_start + brace_pos
            _, after = extract_braced(text, abs_brace)
            stmt_text = text[line_start:after]
            pos = after
        else:
            stmt_text = line
            pos = nl
        stmt_text = stmt_text.strip()
        if not stmt_text:
            continue
        stmts.append(_parse_statement(stmt_text))
    return stmts, pos


def _find_unquoted(s: str, target: str) -> int:
    in_str = False
    for i, c in enumerate(s):
        if in_str:
            if c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == target:
            return i
    return -1


# Regex helpers for each statement kind. Order matters: GRP must come
# before DEF and USE because all three may be followed by a `{...}`.
_RE_DEF = re.compile(r"^DEF\s+(\w+)\s*:\s*([\w.]+)\s*(\{.*\})?\s*$", re.DOTALL)
_RE_USE = re.compile(
    r"^USE\s+(\w+)"
    r"(?:\s+as\s+(\w+))?"
    r"(?:\s+at\s+([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?))?"
    r"(?:\s+dur\s+([+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?))?"
    r"(?:\s+loc\s+([\w.]+))?"
    r"\s*(\{.*\})?\s*$",
    re.DOTALL,
)
_RE_SET = re.compile(r"^SET\s+([\w#]+)\.(\w+)\s*=\s*(.+)$", re.DOTALL)
_RE_MOD = re.compile(r"^MOD\s+(\w+)\s*=\s*(\w+)\s+(.+)$", re.DOTALL)
_RE_LNK = re.compile(r"^LNK\s+([\w.#]+)\s*->\s*([\w.#]+)\s*$", re.DOTALL)
_RE_GRP = re.compile(
    r"^GRP\s+(\w+)"
    r"(?:\s+seed\s+([+-]?\d+))?"
    r"\s*(\{.*\})\s*$",
    re.DOTALL,
)


def _parse_statement(s: str) -> Statement:
    if s.startswith("DEF"):
        m = _RE_DEF.match(s)
        if not m:
            raise SyntaxError(f"bad DEF: {s!r}")
        id_, type_id, block = m.groups()
        params = parse_param_block(block[1:-1]) if block else {}
        return Statement(kind="DEF", id=id_, type_id=type_id, params=params)

    if s.startswith("USE"):
        m = _RE_USE.match(s)
        if not m:
            raise SyntaxError(f"bad USE: {s!r}")
        id_, inst, at, dur, loc, block = m.groups()
        overrides = parse_param_block(block[1:-1]) if block else {}
        return Statement(
            kind="USE", id=id_, instance_id=inst,
            at=float(at) if at is not None else None,
            dur=float(dur) if dur is not None else None,
            loc=loc, params=overrides,
        )

    if s.startswith("SET"):
        m = _RE_SET.match(s)
        if not m:
            raise SyntaxError(f"bad SET: {s!r}")
        target, param, value = m.groups()
        return Statement(
            kind="SET", set_target=target, set_param=param,
            set_value=parse_value(value.strip()),
        )

    if s.startswith("MOD"):
        m = _RE_MOD.match(s)
        if not m:
            raise SyntaxError(f"bad MOD: {s!r}")
        new_id, src_id, ops_text = m.groups()
        ops = _parse_mod_ops(ops_text)
        return Statement(kind="MOD", id=new_id, src_id=src_id, ops=ops)

    if s.startswith("LNK"):
        m = _RE_LNK.match(s)
        if not m:
            raise SyntaxError(f"bad LNK: {s!r}")
        src, dst = m.groups()
        return Statement(kind="LNK", lnk_src=src, lnk_dst=dst)

    if s.startswith("GRP"):
        m = _RE_GRP.match(s)
        if not m:
            raise SyntaxError(f"bad GRP: {s!r}")
        id_, seed_str, block = m.groups()
        inner = block[1:-1]
        children, _ = _parse_block(inner, 0, len(inner))
        seed_val = int(seed_str) if seed_str is not None else None
        return Statement(
            kind="GRP", id=id_, children=children, seed=seed_val,
        )

    raise SyntaxError(f"unknown statement: {s!r}")


# Operators that take more than one argument. Default arity is 1.
# Listed by operator name; the parser groups the extra args into a tuple
# delivered as the op's `arg`. Kept tiny and dialect-aware.
_MOD_OP_ARITY: dict[str, int] = {
    "set": 2,    # set <key> <value>  (patch dialect)
    # Arity-0 flag operators (cello dialect):
    "slur_from_prev": 0,
}

# Operators that accept verb-form arguments (v0.3). The parser looks at
# the token immediately after the operator name: if it's a registered
# verb for this operator, consume verb + N args (where N is verb-defined).
# Otherwise fall back to the operator's normal arity (default 1).
#
# Structure: operator_name -> { verb_name: verb_arity, ... }
# The verb_arity counts arguments AFTER the verb token itself.
_MOD_OP_VERBS: dict[str, dict[str, int]] = {
    "with_pressure":     {"rise": 2, "fall": 2, "hold": 1},
    "with_depth":        {"rise": 2, "fall": 2, "grow": 2, "hold": 1},
    "with_attack":       {"sharper": 1, "softer": 1},
    "with_bow_pressure": {"rise": 2, "fall": 2, "hold": 1},
    # `humanize` may optionally take `seed <int>` after its float arg.
    # Handled specially in the parser below since it's two arities.
}


def _parse_mod_ops(text: str) -> list[tuple[str, Any]]:
    """Parse the operator list of a MOD statement.

    For each operator we try, in order:
      1. Verb-form: if the next token is a verb registered under this
         operator, consume verb + verb_arity args. The op's arg becomes
         a tuple `(verb_name, arg1, arg2, ...)`.
      2. Multi-arg: if the operator is in `_MOD_OP_ARITY`, consume that
         many args as a tuple.
      3. Single-arg: consume one arg.

    Special case for `humanize`: takes 1 float, optionally followed by
    `seed <int>`. Encoded as a tuple `(amount,)` or `(amount, seed)`.

    Whitespace is the only separator.
    """
    tokens = _split_pairs(text)
    ops: list[tuple[str, Any]] = []
    i = 0
    while i < len(tokens):
        name = tokens[i]
        # Verb-form check.
        verbs = _MOD_OP_VERBS.get(name)
        if verbs and i + 1 < len(tokens) and tokens[i + 1] in verbs:
            verb = tokens[i + 1]
            verb_arity = verbs[verb]
            if i + 1 + verb_arity >= len(tokens):
                raise SyntaxError(
                    f"MOD operator {name!r} verb {verb!r} "
                    f"expects {verb_arity} argument(s)"
                )
            verb_args = tuple(
                parse_value(tokens[i + 2 + k]) for k in range(verb_arity)
            )
            ops.append((name, (verb,) + verb_args))
            i += 2 + verb_arity
            continue

        # humanize special case: 1 mandatory arg + optional "seed <int>"
        if name == "humanize":
            if i + 1 >= len(tokens):
                raise SyntaxError("humanize requires an amount argument")
            amount = parse_value(tokens[i + 1])
            # Check for optional seed.
            if (i + 3 < len(tokens) and tokens[i + 2] == "seed"):
                seed_val = parse_value(tokens[i + 3])
                ops.append(("humanize", (amount, seed_val)))
                i += 4
            else:
                ops.append(("humanize", (amount,)))
                i += 2
            continue

        # Multi-arg via arity table.
        arity = _MOD_OP_ARITY.get(name, 1)
        if arity > 0 and i + arity >= len(tokens):
            raise SyntaxError(
                f"MOD operator {name!r} expects {arity} argument(s)"
            )
        if arity == 0:
            arg: Any = None
        elif arity == 1:
            arg = parse_value(tokens[i + 1])
        else:
            arg = tuple(parse_value(tokens[i + 1 + k]) for k in range(arity))
        ops.append((name, arg))
        i += 1 + arity
    return ops


# =====================================================================
# Reachability. Walks from `demo_root` through USE, MOD, LNK references.
# =====================================================================

def collect_top_level_ids(stmts: list[Statement]) -> dict[str, Statement]:
    """Index DEF, MOD, and GRP statements at any nesting depth by id."""
    table: dict[str, Statement] = {}

    def walk(s: Statement) -> None:
        if s.kind in ("DEF", "MOD", "GRP") and s.id is not None:
            if s.id in table:
                raise ValueError(f"duplicate id: {s.id}")
            table[s.id] = s
        for child in s.children:
            walk(child)

    for s in stmts:
        walk(s)
    return table


def reachable_from(
    table: dict[str, Statement],
    root: str,
    top_level: list[Statement] | None = None,
) -> set[str]:
    """Compute the set of ids reachable from `root` via USE/MOD/LNK references.

    Reachability follows:
      - GRP -> ids referenced by its child USEs, MODs, LNKs
      - MOD -> its src_id
      - top-level LNKs whose endpoints touch a reachable entity pull in
        the other endpoint
    """
    if root not in table:
        raise ValueError(f"root id not found: {root}")

    # Collect top-level LNKs once so we can keep applying them as new
    # entities become reachable.
    top_lnks: list[Statement] = []
    if top_level is not None:
        for s in top_level:
            if s.kind == "LNK":
                top_lnks.append(s)

    seen: set[str] = set()
    stack = [root]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        s = table.get(cur)
        if s is None:
            continue

        # Helper: walk a value, follow any `('ref', id)` it contains.
        def follow_refs(value: Any) -> None:
            if isinstance(value, tuple) and len(value) >= 2 and value[0] == "ref":
                stack.append(value[1])
            elif isinstance(value, list):
                for v in value:
                    follow_refs(v)

        # MOD reaches its source and any ref()-valued op arguments.
        if s.kind == "MOD" and s.src_id:
            stack.append(s.src_id)
        if s.kind == "MOD":
            for _, arg in s.ops:
                # arg may itself be a ref tuple, or a verb-form tuple
                # whose elements may include nested ref tuples.
                follow_refs(arg)
                if isinstance(arg, tuple):
                    for sub in arg:
                        follow_refs(sub)

        # DEF params may contain refs (e.g. cello.note's gesture=ref(...)).
        if s.kind == "DEF":
            for _, v in s.params.items():
                follow_refs(v)

        if s.kind == "GRP":
            for child in s.children:
                if child.kind == "USE" and child.id:
                    stack.append(child.id)
                    # USE override values may reference other entities
                    # (e.g. transition_from=ref(prev_gesture)).
                    for _, v in child.params.items():
                        follow_refs(v)
                elif child.kind == "LNK":
                    for endpoint in (child.lnk_src, child.lnk_dst):
                        if endpoint:
                            stack.append(endpoint.split(".", 1)[0])
                elif child.kind == "MOD" and child.src_id:
                    stack.append(child.src_id)

        # After each new entity is seen, sweep top-level LNKs to see if
        # any now connect a reachable entity to an unreached one.
        for lnk in top_lnks:
            src_head = (lnk.lnk_src or "").split(".", 1)[0]
            dst_head = (lnk.lnk_dst or "").split(".", 1)[0]
            if src_head in seen and dst_head and dst_head not in seen:
                stack.append(dst_head)
            elif dst_head in seen and src_head and src_head not in seen:
                stack.append(src_head)
    return seen


# =====================================================================
# Music dialect interpreter. The expander resolves MOD chains, expands
# GRP contents into global-time events, and applies overrides.
# =====================================================================

# Pitch parsing: scientific notation "C4", "D#3", "Bb2".
_PITCH_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")
_PITCH_BASE = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pitch_to_midi(p: str) -> int:
    m = _PITCH_RE.match(p)
    if not m:
        raise ValueError(f"bad pitch: {p!r}")
    letter, accidental, octave = m.groups()
    semitone = _PITCH_BASE[letter.upper()]
    if accidental == "#":
        semitone += 1
    elif accidental == "b":
        semitone -= 1
    return 12 * (int(octave) + 1) + semitone


def midi_to_pitch(m: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    octave = (m // 12) - 1
    return f"{names[m % 12]}{octave}"


@dataclass
class Event:
    """A flat global-time event produced by expansion."""
    t: float
    kind: str                  # "note" | "rest"
    pitch: str | None = None
    velocity: float = 1.0
    dur: float = 1.0

    def as_line(self) -> str:
        if self.kind == "note":
            return (
                f"t={self.t:>8.4f}  note  pitch={self.pitch:<4}"
                f"  dur={self.dur:.4f}  vel={self.velocity:.3f}"
            )
        return f"t={self.t:>8.4f}  rest                  dur={self.dur:.4f}"


# Modifier stack applied during MOD chain or override expansion. A
# modifier is anything that transforms the events of a USE.
@dataclass
class Modifiers:
    transpose: int = 0          # semitones, additive
    stretch: float = 1.0        # multiplicative
    mute: list[int] = field(default_factory=list)  # indices to silence
    gain: float = 1.0           # velocity multiplier

    def compose(self, op: str, arg: Any) -> "Modifiers":
        """Return a new Modifiers with `op arg` stacked on top."""
        new = Modifiers(
            transpose=self.transpose,
            stretch=self.stretch,
            mute=list(self.mute),
            gain=self.gain,
        )
        if op == "transpose":
            new.transpose += int(arg)
        elif op == "stretch":
            new.stretch *= float(arg)
        elif op == "mute":
            indices = arg if isinstance(arg, list) else [arg]
            new.mute.extend(int(i) for i in indices)
        elif op == "gain":
            new.gain *= float(arg)
        else:
            raise ValueError(f"music dialect: unknown operator {op!r}")
        return new


def resolve_mod_chain(
    entity_id: str,
    table: dict[str, Statement],
    base: Modifiers | None = None,
) -> tuple[str, Modifiers]:
    """Walk a chain of MODs back to the original DEF or GRP.

    Returns (root_entity_id, accumulated_modifiers). Modifiers compose
    in order from the root outward — so `MOD x = y transpose +7` applied
    to a USE of x yields a +7 transpose stacked on top of y's content.
    """
    mods = base or Modifiers()
    cur = entity_id
    chain: list[Statement] = []
    while cur in table and table[cur].kind == "MOD":
        chain.append(table[cur])
        cur = table[cur].src_id
        if cur is None:
            raise ValueError("MOD with missing source")
    # Apply MODs from oldest (closest to root) to newest. Since we
    # walked from new to old, reverse.
    for mod_stmt in reversed(chain):
        for op_name, op_arg in mod_stmt.ops:
            mods = mods.compose(op_name, op_arg)
    return cur, mods


def expand(
    stmts: list[Statement],
    root: str = "demo_root",
) -> list[Event]:
    """Top-level expansion. Returns a sorted list of global-time events."""
    table = collect_top_level_ids(stmts)
    if root not in table:
        raise ValueError(f"root not found: {root}")

    reachable = reachable_from(table, root, top_level=stmts)
    events: list[Event] = []
    _expand_grp(table[root], 0.0, None, Modifiers(), table, reachable, events)
    events.sort(key=lambda e: (e.t, e.pitch or ""))
    return events


def _expand_grp(
    grp: Statement,
    global_at: float,
    global_dur: float | None,
    mods: Modifiers,
    table: dict[str, Statement],
    reachable: set[str],
    out: list[Event],
) -> float:
    """Expand a GRP. Returns the global end time it occupied.

    `global_at` is the global time the GRP starts at.
    `global_dur` is the duration the enclosing USE wants this GRP to
    occupy. If None, the GRP runs at its natural local duration.
    """
    # First pass: resolve implicit `at` for sequential-mode positioning.
    # Per §4.3, a USE inside a music GRP without an explicit `at` starts
    # where the previous USE ended.
    resolved: list[tuple[Statement, float, float]] = []
    cursor = 0.0
    local_end = 0.0
    for child in grp.children:
        if child.kind != "USE":
            # Non-USE children inside a GRP (nested DEF/MOD/LNK) are
            # handled by the top-level table already; v0.2 does not
            # support GRP-local DEFs that differ from top-level DEFs.
            continue
        local_at = child.at if child.at is not None else cursor
        local_dur = child.dur if child.dur is not None else _natural_dur(child.id, table)
        resolved.append((child, local_at, local_dur))
        cursor = local_at + local_dur
        local_end = max(local_end, cursor)

    # Compute the local-to-global scale.
    if global_dur is None or local_end == 0.0:
        scale = 1.0
    else:
        scale = global_dur / local_end

    # Second pass: emit events for each child USE.
    for child, local_at, local_dur in resolved:
        child_global_at = global_at + local_at * scale
        child_global_dur = local_dur * scale
        # Compose any per-use overrides as a modifier stack.
        use_mods = mods
        for k, v in child.params.items():
            use_mods = use_mods.compose(k, v)
        _expand_use(
            child.id, child_global_at, child_global_dur,
            use_mods, table, reachable, out,
        )

    return global_at + local_end * scale


def _expand_use(
    entity_id: str,
    global_at: float,
    global_dur: float,
    mods: Modifiers,
    table: dict[str, Statement],
    reachable: set[str],
    out: list[Event],
) -> None:
    """Expand a single USE of an entity at the given global time."""
    if entity_id not in reachable:
        # Should never happen; reachability is computed from the same
        # graph. Useful guard anyway.
        return
    if entity_id not in table:
        # Reference to an entity outside the document.
        return

    # Walk MOD chain back to root, accumulating modifiers from the
    # root outward. Then stack the USE's own modifiers on top.
    root_id, mod_mods = resolve_mod_chain(entity_id, table)
    # Combine MOD-chain modifiers with the inherited stack. IMPORTANT:
    # build a fresh Modifiers, never mutate the caller's `mods` — it is
    # reused across sibling USEs in the same GRP.
    combined = Modifiers(
        transpose=mods.transpose + mod_mods.transpose,
        stretch=mods.stretch * mod_mods.stretch,
        mute=list(mods.mute) + list(mod_mods.mute),
        gain=mods.gain * mod_mods.gain,
    )

    target = table.get(root_id)
    if target is None:
        return

    if target.kind == "GRP":
        # Recursively expand the group, passing the combined modifiers
        # down. The group's natural local duration is what stretch
        # was computed against; we already pre-applied stretch via
        # global_dur, so pass it straight through.
        _expand_grp(target, global_at, global_dur, combined, table, reachable, out)
        return

    if target.kind != "DEF":
        return

    type_id = target.type_id or ""
    if type_id == "music.note":
        _emit_note(target, global_at, global_dur, combined, out, index=0)
    elif type_id == "music.rest":
        out.append(Event(t=global_at, kind="rest", dur=global_dur))
    elif type_id == "music.phrase":
        _expand_phrase(target, global_at, global_dur, combined, out)
    elif type_id == "music.instrument":
        # Instruments do not emit events in v0.2; they are routing targets.
        pass
    else:
        # Unknown dialect or type. Print a warning to stderr; don't crash.
        print(f"warning: unknown type {type_id!r} for {root_id!r}",
              file=sys.stderr)


def _emit_note(
    note_def: Statement,
    global_at: float,
    global_dur: float,
    mods: Modifiers,
    out: list[Event],
    index: int,
) -> None:
    if index in mods.mute:
        out.append(Event(t=global_at, kind="rest", dur=global_dur))
        return
    pitch_sym = note_def.params.get("pitch")
    if pitch_sym is None:
        raise ValueError(f"note {note_def.id!r} missing pitch")
    midi = pitch_to_midi(str(pitch_sym)) + mods.transpose
    velocity = float(note_def.params.get("velocity", 1.0)) * mods.gain
    out.append(Event(
        t=global_at, kind="note",
        pitch=midi_to_pitch(midi),
        velocity=velocity,
        dur=global_dur,
    ))


def _expand_phrase(
    phrase_def: Statement,
    global_at: float,
    global_dur: float,
    mods: Modifiers,
    out: list[Event],
) -> None:
    notes = phrase_def.params.get("notes", [])
    step = float(phrase_def.params.get("step", 1.0))
    if not notes:
        return
    natural = len(notes) * step * mods.stretch
    scale = (global_dur / natural) if natural > 0 else 1.0
    note_dur = step * mods.stretch * scale
    for i, pitch_sym in enumerate(notes):
        t = global_at + i * note_dur
        if i in mods.mute:
            out.append(Event(t=t, kind="rest", dur=note_dur))
            continue
        midi = pitch_to_midi(str(pitch_sym)) + mods.transpose
        out.append(Event(
            t=t, kind="note",
            pitch=midi_to_pitch(midi),
            velocity=1.0 * mods.gain,
            dur=note_dur,
        ))


def _natural_dur(entity_id: str | None, table: dict[str, Statement]) -> float:
    """Compute the natural local duration of an entity for sequential mode."""
    if entity_id is None or entity_id not in table:
        return 1.0
    root_id, mods = resolve_mod_chain(entity_id, table)
    target = table.get(root_id)
    if target is None:
        return 1.0
    if target.kind == "GRP":
        # Recursively compute the sum of natural durations.
        total = 0.0
        cursor = 0.0
        for child in target.children:
            if child.kind != "USE":
                continue
            at = child.at if child.at is not None else cursor
            dur = child.dur if child.dur is not None else _natural_dur(child.id, table)
            cursor = at + dur
            total = max(total, cursor)
        return total * mods.stretch
    if target.kind == "DEF" and target.type_id == "music.phrase":
        notes = target.params.get("notes", [])
        step = float(target.params.get("step", 1.0))
        return len(notes) * step * mods.stretch
    if target.kind == "DEF" and target.type_id == "music.note":
        return float(target.params.get("duration", 1.0)) * mods.stretch
    return 1.0


# =====================================================================
# Patch dialect. Non-time-positioned graph of nodes connected by LNK.
# Expansion resolves the graph: it gathers reachable patch nodes,
# applies MOD parameter overrides, validates LNK port shapes (cross-
# dialect mismatches produce warnings), topologically sorts the nodes,
# and returns a graph description.
# =====================================================================

# Per-type catalogue. Each entry has:
#   inputs/outputs: port name -> shape (signal, value, event)
#   lifetime: how the runtime treats instances of this type
#     "streaming"     produces output every tick while active
#     "event-driven"  responds only to incoming events
#     "precomputed"   computed once before activation, then read-only
#     "sink"          terminal; consumes input, no output
# Ports are documented in spine_dialect_template.md §1.3.
# Lifetime is documented in §1.7 (added with Prototype C — see
# tools/spine/docs/PROTOTYPE_C.md for the rationale).
PATCH_PORTS: dict[str, dict[str, Any]] = {
    # --- Sources / oscillators / noise -------------------------------
    "patch.oscillator": {
        "inputs": {"freq_mod": "value", "phase_mod": "value"},
        "outputs": {"out": "signal"},
        "lifetime": "streaming",
    },
    "patch.lfo": {
        # Same shape as oscillator but conventionally low-frequency.
        # Distinguishing the type keeps probes readable and lets the
        # eventual softsynth pick a cheaper implementation.
        "inputs": {"freq_mod": "value"},
        "outputs": {"out": "value"},
        "lifetime": "streaming",
    },
    "patch.noise": {
        "inputs": {},
        "outputs": {"out": "signal"},
        "lifetime": "streaming",
    },

    # --- Time / triggers ---------------------------------------------
    "patch.clock": {
        # Emits a trigger event every `period` seconds. The simulator
        # ticks the phase and fires when it wraps.
        "inputs": {"rate_mod": "value"},
        "outputs": {"trigger": "event"},
        "lifetime": "streaming",
    },
    "patch.dice": {
        # Sample-and-hold randomizer. On each incoming trigger, picks
        # a new value in [-1, 1] (or [0,1] if `unipolar=true`). Holds
        # that value on `out` between triggers.
        "inputs": {"trigger": "event"},
        "outputs": {"out": "value"},
        "lifetime": "event-driven",
    },

    # --- Envelopes ---------------------------------------------------
    "patch.envelope": {
        "inputs": {"trigger": "event"},
        "outputs": {"out": "value"},
        "lifetime": "event-driven",
    },

    # --- Filters -----------------------------------------------------
    "patch.filter": {
        # Kept from Prototype B for backward compatibility.
        "inputs": {"in": "signal", "cutoff_mod": "value"},
        "outputs": {"out": "signal"},
        "lifetime": "streaming",
    },
    "patch.lowpass": {
        "inputs": {"in": "signal", "cutoff_mod": "value"},
        "outputs": {"out": "signal"},
        "lifetime": "streaming",
    },
    "patch.highpass": {
        "inputs": {"in": "signal", "cutoff_mod": "value"},
        "outputs": {"out": "signal"},
        "lifetime": "streaming",
    },

    # --- Delays (feedback-capable) -----------------------------------
    # An edge into the `in` port of a delay or allpass_delay is allowed
    # to participate in a cycle. See topo_sort_patch().
    "patch.delay": {
        "inputs": {"in": "signal", "time_mod": "value", "fb_mod": "value"},
        "outputs": {"out": "signal"},
        "lifetime": "streaming",
    },
    "patch.allpass_delay": {
        "inputs": {"in": "signal", "time_mod": "value", "fb_mod": "value"},
        "outputs": {"out": "signal"},
        "lifetime": "streaming",
    },

    # --- Mixing and sinks --------------------------------------------
    "patch.gain": {
        "inputs": {"in": "signal", "gain_mod": "value"},
        "outputs": {"out": "signal"},
        "lifetime": "streaming",
    },
    "patch.mixer": {
        # Accepts up to 8 numbered signal inputs. The simulator sums
        # whichever are connected and divides by the connected count.
        "inputs": {
            "in0": "signal", "in1": "signal", "in2": "signal",
            "in3": "signal", "in4": "signal", "in5": "signal",
            "in6": "signal", "in7": "signal",
        },
        "outputs": {"out": "signal"},
        "lifetime": "streaming",
    },
    "patch.output": {
        # Prototype B's terminal node. Kept; superseded by scene_out
        # for streaming-aware work.
        "inputs": {"in": "signal"},
        "outputs": {},
        "lifetime": "sink",
    },
    "patch.scene_out": {
        # Streaming-aware terminal. The simulator probes this every
        # tick as the canonical "what the listener hears."
        "inputs": {"in": "signal"},
        "outputs": {},
        "lifetime": "sink",
    },
}

# The set of (type_id, port_name) pairs that may be the destination of
# a feedback edge. Other cycles are errors. Kept minimal: only the
# delay-line signal inputs.
PATCH_FEEDBACK_INPUTS: set[tuple[str, str]] = {
    ("patch.delay", "in"),
    ("patch.allpass_delay", "in"),
}

# Music dialect ports for cross-dialect LNK shape checking.
MUSIC_PORTS: dict[str, dict[str, Any]] = {
    "music.note": {
        "inputs": {},
        "outputs": {"out": "event", "note_on": "event", "note_off": "event"},
        "lifetime": "event-driven",
    },
    "music.rest": {
        "inputs": {},
        "outputs": {"out": "event"},
        "lifetime": "event-driven",
    },
    "music.phrase": {
        "inputs": {},
        "outputs": {"out": "event", "note_on": "event", "note_off": "event"},
        "lifetime": "event-driven",
    },
    "music.instrument": {
        "inputs": {"in": "event"},
        "outputs": {"out": "signal"},
        "lifetime": "streaming",
    },
}

# Cello dialect — v0.3 sketch. See `spine_dialect_template.md` §3 for
# the contract. Base gestures are precomputed (trajectory templates
# load once); notes are event-driven (one performance event per USE).
CELLO_PORTS: dict[str, dict[str, Any]] = {
    "cello.gesture.détaché": {
        "inputs": {}, "outputs": {}, "lifetime": "precomputed",
    },
    "cello.gesture.martelé": {
        "inputs": {}, "outputs": {}, "lifetime": "precomputed",
    },
    "cello.gesture.legato": {
        "inputs": {}, "outputs": {}, "lifetime": "precomputed",
    },
    "cello.gesture.vibrato_warm": {
        "inputs": {}, "outputs": {}, "lifetime": "precomputed",
    },
    "cello.gesture.vibrato_narrow": {
        "inputs": {}, "outputs": {}, "lifetime": "precomputed",
    },
    "cello.gesture.sul_tasto": {
        "inputs": {}, "outputs": {}, "lifetime": "precomputed",
    },
    "cello.gesture.pizzicato": {
        "inputs": {}, "outputs": {}, "lifetime": "precomputed",
    },
    "cello.note": {
        "inputs": {},
        "outputs": {"out": "event"},
        "lifetime": "event-driven",
    },
    "cello.curve.standard": {
        "inputs": {},
        "outputs": {"out": "value"},
        "lifetime": "precomputed",
    },
}

# Union view used by the resolver.
ALL_PORTS = {**PATCH_PORTS, **MUSIC_PORTS, **CELLO_PORTS}


# Cello-dialect base gestures. The score writer cannot DEF a new base
# gesture; only MOD-derive variants of these. Used by the cello resolver
# to detect "is this a known base gesture vs a MOD-derived variant."
CELLO_BASE_GESTURES: set[str] = {
    "cello.gesture.détaché",
    "cello.gesture.martelé",
    "cello.gesture.legato",
    "cello.gesture.vibrato_warm",
    "cello.gesture.vibrato_narrow",
    "cello.gesture.sul_tasto",
    "cello.gesture.pizzicato",
}


# Cello transition table — from-gesture base type, to-gesture base type,
# resolver name. The matching is by base type (after walking MOD chains
# to the root), and falls back to a default if no exact match found.
# `runtime_state_needed` flags resolvers that may need live state of
# the previous gesture (see runtime model §9.6).
CELLO_TRANSITIONS: list[dict[str, Any]] = [
    {"from": "cello.gesture.legato",   "to": "cello.gesture.legato",
     "resolver": "continue_bow",       "runtime_state_needed": False},
    {"from": "cello.gesture.détaché",  "to": "cello.gesture.legato",
     "resolver": "continue_bow",       "runtime_state_needed": False},
    {"from": "cello.gesture.legato",   "to": "cello.gesture.détaché",
     "resolver": "continue_bow",       "runtime_state_needed": False},
    {"from": "cello.gesture.martelé",  "to": "cello.gesture.legato",
     "resolver": "lift_and_settle",    "runtime_state_needed": True},
    {"from": "cello.gesture.martelé",  "to": "cello.gesture.détaché",
     "resolver": "lift_and_settle",    "runtime_state_needed": True},
    {"from": "cello.gesture.legato",   "to": "cello.gesture.martelé",
     "resolver": "reattack",           "runtime_state_needed": False},
    {"from": "cello.gesture.détaché",  "to": "cello.gesture.martelé",
     "resolver": "reattack",           "runtime_state_needed": False},
    {"from": "*",                       "to": "cello.gesture.pizzicato",
     "resolver": "pluck_attack",       "runtime_state_needed": False},
    {"from": "cello.gesture.pizzicato","to": "*",
     "resolver": "bow_recover",        "runtime_state_needed": False},
]


def lifetime_of(type_id: str) -> str | None:
    """Lookup the runtime lifetime classification for a type id."""
    entry = ALL_PORTS.get(type_id)
    return entry.get("lifetime") if entry else None


def is_cello_entity(type_id: str | None) -> bool:
    return type_id is not None and type_id.startswith("cello.")


def is_cello_gesture(type_id: str | None) -> bool:
    return type_id is not None and type_id.startswith("cello.gesture.")


@dataclass
class PatchNode:
    """A resolved patch node — original DEF with MOD overrides applied."""
    id: str
    type_id: str
    params: dict[str, Any]

    def as_lines(self) -> list[str]:
        lines = [f"node {self.id} : {self.type_id}"]
        for k in sorted(self.params):
            lines.append(f"    {k} = {self.params[k]!r}")
        return lines


@dataclass
class PatchEdge:
    src_node: str
    src_port: str
    dst_node: str
    dst_port: str
    shape_src: str | None       # port shape on the source side
    shape_dst: str | None       # port shape on the destination side
    warning: str | None = None  # set if shapes mismatched or unknown
    is_feedback: bool = False   # set if this edge participates in an
                                # allowed feedback cycle (e.g. into a
                                # delay-line input). Such edges are
                                # ignored for topological ordering.

    def as_line(self) -> str:
        shape = (
            f"  [{self.shape_src} -> {self.shape_dst}]"
            if self.shape_src and self.shape_dst else ""
        )
        flag = f"  WARNING: {self.warning}" if self.warning else ""
        fb = "  [feedback]" if self.is_feedback else ""
        return (
            f"edge {self.src_node}.{self.src_port}"
            f" -> {self.dst_node}.{self.dst_port}{shape}{fb}{flag}"
        )


@dataclass
class PatchGraph:
    nodes: list[PatchNode] = field(default_factory=list)
    edges: list[PatchEdge] = field(default_factory=list)
    order: list[str] = field(default_factory=list)  # topo order of node ids
    warnings: list[str] = field(default_factory=list)


def is_patch_entity(type_id: str | None) -> bool:
    return type_id is not None and type_id.startswith("patch.")


def resolve_patch_mod_chain(
    entity_id: str,
    table: dict[str, Statement],
) -> tuple[str, dict[str, Any]]:
    """Walk a MOD chain for a patch entity, accumulating `set` overrides.

    The patch dialect's MOD operators in v0.2:
      set <key> <value>   — override one parameter on the source

    The parser delivers `set` as a three-token op: ('set', (key, value)).
    """
    overrides: dict[str, Any] = {}
    chain: list[Statement] = []
    cur = entity_id
    while cur in table and table[cur].kind == "MOD":
        chain.append(table[cur])
        cur = table[cur].src_id
        if cur is None:
            raise ValueError("MOD with missing source")
    for mod_stmt in reversed(chain):
        for op_name, op_arg in mod_stmt.ops:
            if op_name == "set":
                if not isinstance(op_arg, tuple) or len(op_arg) != 2:
                    raise ValueError(
                        f"patch.set expects (key, value), got {op_arg!r}"
                    )
                key, value = op_arg
                overrides[str(key)] = value
            else:
                raise ValueError(
                    f"patch dialect: unknown MOD operator {op_name!r}"
                )
    return cur, overrides


def collect_patch_nodes(
    stmts: list[Statement],
    reachable: set[str],
    table: dict[str, Statement],
) -> dict[str, PatchNode]:
    """Build the set of resolved patch nodes (with MOD overrides applied)."""
    nodes: dict[str, PatchNode] = {}
    # Direct DEFs that are patch entities.
    for sid in reachable:
        s = table.get(sid)
        if s is None or s.kind != "DEF":
            continue
        if not is_patch_entity(s.type_id):
            continue
        nodes[sid] = PatchNode(
            id=sid, type_id=s.type_id, params=dict(s.params),
        )
    # MOD-derived variants whose root is a patch entity.
    for sid in reachable:
        s = table.get(sid)
        if s is None or s.kind != "MOD":
            continue
        root_id, overrides = resolve_patch_mod_chain(sid, table)
        root = table.get(root_id)
        if root is None or root.kind != "DEF":
            continue
        if not is_patch_entity(root.type_id):
            continue
        params = dict(root.params)
        params.update(overrides)
        nodes[sid] = PatchNode(
            id=sid, type_id=root.type_id, params=params,
        )
    return nodes


def _lookup_port_shape(type_id: str, port: str, direction: str) -> str | None:
    """Return the shape of `type_id`.`port` as input/output, or None."""
    catalog = ALL_PORTS.get(type_id)
    if catalog is None:
        return None
    return catalog.get(direction, {}).get(port)


def resolve_patch_graph(
    stmts: list[Statement],
    reachable: set[str],
    table: dict[str, Statement],
) -> PatchGraph:
    """Collect nodes, resolve LNK edges, check port shapes, topo-sort.

    Walks every LNK statement (top-level and inside reachable GRPs)
    whose source node is reachable and is either a patch node or any
    other reachable entity feeding a patch input. Records edges with
    port-shape annotations and warnings for mismatches.
    """
    graph = PatchGraph()
    nodes = collect_patch_nodes(stmts, reachable, table)
    graph.nodes = list(nodes.values())

    # Gather every LNK statement that's reachable. Top-level LNKs are
    # always considered; LNKs inside reachable GRPs are also included.
    lnk_stmts: list[Statement] = []
    for s in stmts:
        if s.kind == "LNK":
            lnk_stmts.append(s)
        elif s.kind == "GRP" and s.id in reachable:
            for child in s.children:
                if child.kind == "LNK":
                    lnk_stmts.append(child)

    # All reachable entities that could be edge endpoints. Includes
    # patch nodes plus music entities that may feed into the patch.
    endpoint_types: dict[str, str] = {}
    for sid in reachable:
        s = table.get(sid)
        if s is None:
            continue
        if s.kind == "DEF" and s.type_id:
            endpoint_types[sid] = s.type_id
        elif s.kind == "MOD":
            root_id, _ = resolve_patch_mod_chain(sid, table) \
                if is_mod_targeting_patch(sid, table) \
                else (s.src_id, {})
            # Resolve type by walking to a DEF if possible.
            cur = sid
            while cur in table and table[cur].kind == "MOD":
                cur = table[cur].src_id
            root = table.get(cur) if cur else None
            if root and root.kind == "DEF" and root.type_id:
                endpoint_types[sid] = root.type_id

    for lnk in lnk_stmts:
        src = lnk.lnk_src or ""
        dst = lnk.lnk_dst or ""
        src_node, _, src_port = src.partition(".")
        dst_node, _, dst_port = dst.partition(".")
        # If neither endpoint is a patch node, this LNK belongs to a
        # different concern and the patch resolver does not record it.
        # We DO record cross-dialect LNKs where one end is a patch node.
        src_in_patch = src_node in nodes
        dst_in_patch = dst_node in nodes
        if not (src_in_patch or dst_in_patch):
            continue

        src_type = endpoint_types.get(src_node)
        dst_type = endpoint_types.get(dst_node)
        shape_src = _lookup_port_shape(src_type, src_port, "outputs") \
            if src_type else None
        shape_dst = _lookup_port_shape(dst_type, dst_port, "inputs") \
            if dst_type else None

        warning = None
        if shape_src is None or shape_dst is None:
            warning = (
                f"unknown port shape "
                f"({src_type}.{src_port}={shape_src}, "
                f"{dst_type}.{dst_port}={shape_dst})"
            )
        elif shape_src != shape_dst:
            warning = (
                f"port shape mismatch: {shape_src} -> {shape_dst}"
            )

        # is_feedback is set later by topo_sort_patch, only for edges
        # that actually participate in a cycle through a feedback-
        # eligible input. Edges into delay inputs that don't form a
        # cycle stay is_feedback=False so they constrain ordering.
        edge = PatchEdge(
            src_node=src_node, src_port=src_port,
            dst_node=dst_node, dst_port=dst_port,
            shape_src=shape_src, shape_dst=shape_dst,
            warning=warning, is_feedback=False,
        )
        graph.edges.append(edge)
        if warning:
            graph.warnings.append(
                f"{src_node}.{src_port} -> {dst_node}.{dst_port}: {warning}"
            )

    graph.order = topo_sort_patch(graph)
    return graph


def is_mod_targeting_patch(
    sid: str, table: dict[str, Statement]
) -> bool:
    cur = sid
    while cur in table and table[cur].kind == "MOD":
        cur = table[cur].src_id
        if cur is None:
            return False
    root = table.get(cur) if cur else None
    if root is None or root.kind != "DEF":
        return False
    return is_patch_entity(root.type_id)


def topo_sort_patch(graph: PatchGraph) -> list[str]:
    """Two-pass Kahn's algorithm with selective feedback-edge removal.

    Pass 1: try to topo-sort using all edges. If it succeeds, done.

    Pass 2: if cycles remain, mark cycle-participant edges into delay-
    line inputs as actual feedback edges (those become is_feedback=True
    on the edge) and re-run. If cycles remain after that, the cycle
    routes through something other than a delay and is a real error.

    Edges that are merely eligible to be feedback (into a delay input)
    but not actually closing a cycle keep is_feedback=False, so they
    constrain ordering normally. This avoids the bug where a simple
    `mixer -> delay -> out` chain put the mixer last because the
    mixer's only out-edge targeted a delay.
    """
    node_ids = {n.id for n in graph.nodes}

    def _kahn(skip_predicate) -> tuple[list[str], set[str]]:
        incoming: dict[str, int] = {nid: 0 for nid in node_ids}
        succ: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for e in graph.edges:
            if skip_predicate(e):
                continue
            if e.src_node in node_ids and e.dst_node in node_ids:
                incoming[e.dst_node] += 1
                succ[e.src_node].append(e.dst_node)
        ready = sorted(nid for nid, deg in incoming.items() if deg == 0)
        order: list[str] = []
        while ready:
            nid = ready.pop(0)
            order.append(nid)
            for nxt in succ[nid]:
                incoming[nxt] -= 1
                if incoming[nxt] == 0:
                    ready.append(nxt)
            ready.sort()
        unresolved = node_ids - set(order)
        return order, unresolved

    # Pass 1: full graph, no feedback edges ignored. Don't honor any
    # is_feedback flags yet — the flag will be set in pass 2 only if
    # actually needed.
    order, unresolved = _kahn(lambda e: False)
    if not unresolved:
        # Clear any premature is_feedback flags from edge construction:
        # they were eligible but not needed.
        for e in graph.edges:
            e.is_feedback = False
        return order

    # Pass 2: mark cycle-participating delay-input edges as feedback,
    # and try again skipping them.
    for e in graph.edges:
        is_eligible = (
            (e.src_node in node_ids and e.dst_node in node_ids)
            and (
                # The eligibility test from edge construction.
                _edge_targets_feedback_input(e, graph)
            )
        )
        # Mark only the eligible edges that lie inside the unresolved
        # set (i.e., participate in a cycle).
        if (is_eligible
            and e.src_node in unresolved
            and e.dst_node in unresolved):
            e.is_feedback = True
        else:
            e.is_feedback = False

    order2, unresolved2 = _kahn(lambda e: e.is_feedback)
    if unresolved2:
        cycle_members = sorted(unresolved2)
        graph.warnings.append(
            f"cycle detected without delay feedback path; "
            f"unordered members: {cycle_members}"
        )
        order2.extend(cycle_members)
    return order2


def _edge_targets_feedback_input(
    edge: "PatchEdge", graph: "PatchGraph",
) -> bool:
    """Look up whether `edge` targets a port listed in
    PATCH_FEEDBACK_INPUTS."""
    type_by_id = {n.id: n.type_id for n in graph.nodes}
    dst_type = type_by_id.get(edge.dst_node)
    if dst_type is None:
        return False
    return (dst_type, edge.dst_port) in PATCH_FEEDBACK_INPUTS


def render_patch_graph(graph: PatchGraph) -> str:
    """Stable text dump of the resolved patch graph."""
    lines: list[str] = []
    lines.append(f"# patch graph: {len(graph.nodes)} nodes, "
                 f"{len(graph.edges)} edges")
    if graph.warnings:
        lines.append(f"# warnings: {len(graph.warnings)}")
        for w in graph.warnings:
            lines.append(f"# WARN  {w}")
    lines.append("")
    lines.append("# topological order:")
    for nid in graph.order:
        lines.append(f"#   {nid}")
    lines.append("")
    # Emit nodes in topo order.
    by_id = {n.id: n for n in graph.nodes}
    for nid in graph.order:
        node = by_id.get(nid)
        if node is None:
            continue
        lines.extend(node.as_lines())
        lines.append("")
    # Edges in source-then-destination order, stable.
    for edge in sorted(
        graph.edges,
        key=lambda e: (e.src_node, e.src_port, e.dst_node, e.dst_port),
    ):
        lines.append(edge.as_line())
    return "\n".join(lines) + "\n"


def expand_patch(
    stmts: list[Statement],
    root: str = "demo_root",
) -> PatchGraph:
    """Top-level patch expansion driver."""
    table = collect_top_level_ids(stmts)
    if root not in table:
        raise ValueError(f"root not found: {root}")
    reachable = reachable_from(table, root, top_level=stmts)
    return resolve_patch_graph(stmts, reachable, table)


# =====================================================================
# Cello dialect resolver (Prototype D / v0.3 sketch).
#
# Walks reachable cello entities, resolves gesture MOD chains to (root
# base gesture + transformation stack), propagates seed values through
# GRP nesting, captures transition_from markers on note USEs, and emits
# a per-note dump for diffable verification.
#
# This is not a synthesizer. The output is a stable text record of
# WHAT a synthesizer would receive, not what it would sound like.
# Synthesis lives in the cello-dialect chat plus eventual softsynth.
# =====================================================================


@dataclass
class CelloGestureResolved:
    """A gesture variant resolved to (base, ops). Mirrors a MOD chain."""
    id: str                     # the entity's id (DEF or final MOD)
    base: str                   # root base gesture type id
    ops: list[tuple[str, Any]]  # accumulated transformation stack
    humanize_amount: float | None = None
    humanize_seed_explicit: int | None = None

    def as_lines(self) -> list[str]:
        lines = [f"gesture {self.id} base={self.base}"]
        for op_name, op_arg in self.ops:
            lines.append(f"    {op_name} {op_arg!r}")
        if self.humanize_amount is not None:
            seed_str = (
                f"seed={self.humanize_seed_explicit}"
                if self.humanize_seed_explicit is not None else "seed=inherited"
            )
            lines.append(f"    humanize {self.humanize_amount} {seed_str}")
        return lines


@dataclass
class CelloNoteResolved:
    """One performance event with resolved gesture binding."""
    t: float                     # global time
    pitch: str
    dur: float
    gesture_id: str | None       # which (possibly MOD-derived) gesture
    transition_from: str | None  # the previous gesture id, if marked
    transition_resolver: str | None  # looked up from CELLO_TRANSITIONS
    transition_runtime_state: bool   # does the resolver need runtime state?
    inherited_seed: int | None   # the score-level seed reached via GRP
    seed_tuple: tuple[int, str, int] | None
                                 # (parent_seed, gesture_id, instance_counter)
                                 # for offline hashing; v0.3 records it as
                                 # a tuple, doesn't yet hash

    def as_line(self) -> str:
        parts = [
            f"t={self.t:>8.4f}",
            f"pitch={self.pitch:<4}",
            f"dur={self.dur:.4f}",
            f"gesture={self.gesture_id or '(none)'}",
        ]
        if self.transition_from:
            parts.append(
                f"transition_from={self.transition_from} "
                f"resolver={self.transition_resolver}"
                f"{' (runtime_state)' if self.transition_runtime_state else ''}"
            )
        if self.seed_tuple:
            parts.append(f"seed_tuple={self.seed_tuple}")
        return "  ".join(parts)


@dataclass
class CelloResolution:
    gestures: dict[str, CelloGestureResolved] = field(default_factory=dict)
    notes: list[CelloNoteResolved] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def resolve_cello_gesture_chain(
    entity_id: str,
    table: dict[str, Statement],
) -> CelloGestureResolved | None:
    """Walk a MOD chain back to a base cello.gesture.*; collect ops.

    Returns None if the chain does not root at a cello base gesture.
    """
    chain: list[Statement] = []
    cur = entity_id
    while cur in table and table[cur].kind == "MOD":
        chain.append(table[cur])
        cur = table[cur].src_id
        if cur is None:
            return None
    root = table.get(cur) if cur else None
    if root is None or root.kind != "DEF" or not is_cello_gesture(root.type_id):
        return None
    base = root.type_id

    # Collect ops oldest-first (root outward).
    ops: list[tuple[str, Any]] = []
    humanize_amount = None
    humanize_seed_explicit = None
    for mod_stmt in reversed(chain):
        for op_name, op_arg in mod_stmt.ops:
            if op_name == "humanize":
                # humanize is recorded separately (it has special seed
                # semantics) rather than as one of the transformation
                # ops. (amount,) or (amount, seed) tuple.
                if isinstance(op_arg, tuple):
                    humanize_amount = float(op_arg[0])
                    if len(op_arg) >= 2:
                        humanize_seed_explicit = int(op_arg[1])
                else:
                    humanize_amount = float(op_arg)
            else:
                ops.append((op_name, op_arg))
    return CelloGestureResolved(
        id=entity_id, base=base, ops=ops,
        humanize_amount=humanize_amount,
        humanize_seed_explicit=humanize_seed_explicit,
    )


def lookup_cello_transition(
    from_base: str | None,
    to_base: str | None,
) -> tuple[str, bool]:
    """Return (resolver_name, runtime_state_needed) for a transition.

    Falls back to ('brief_silence', False) if no rule matches.
    """
    if from_base is None or to_base is None:
        return ("brief_silence", False)
    for rule in CELLO_TRANSITIONS:
        f_match = rule["from"] == "*" or rule["from"] == from_base
        t_match = rule["to"] == "*" or rule["to"] == to_base
        if f_match and t_match:
            return (rule["resolver"], bool(rule["runtime_state_needed"]))
    return ("brief_silence", False)


def expand_cello(
    stmts: list[Statement],
    root: str = "demo_root",
) -> CelloResolution:
    """Resolve all reachable cello entities and produce a phrase dump."""
    table = collect_top_level_ids(stmts)
    if root not in table:
        raise ValueError(f"root not found: {root}")
    reachable = reachable_from(table, root, top_level=stmts)

    res = CelloResolution()

    # Resolve every reachable cello-gesture MOD chain.
    for sid in reachable:
        s = table.get(sid)
        if s is None:
            continue
        # Direct DEF of a base gesture (no ops).
        if s.kind == "DEF" and is_cello_gesture(s.type_id):
            res.gestures[sid] = CelloGestureResolved(
                id=sid, base=s.type_id or "", ops=[],
            )
        elif s.kind == "MOD":
            resolved = resolve_cello_gesture_chain(sid, table)
            if resolved is not None:
                res.gestures[sid] = resolved

    # Walk GRPs from root, collecting note USEs with their full context.
    # `_expand_cello_grp` recurses, tracking inherited seed and global time.
    _expand_cello_grp(
        grp=table[root],
        global_at=0.0,
        global_dur=None,
        inherited_seed=None,
        prev_gesture_id=None,  # for fallback transition_from
        table=table,
        reachable=reachable,
        res=res,
        instance_counters={},
    )
    return res


def _natural_cello_dur(
    entity_id: str | None,
    table: dict[str, Statement],
) -> float:
    """Compute the natural local duration of a cello entity."""
    if entity_id is None or entity_id not in table:
        return 1.0
    s = table[entity_id]
    if s.kind == "GRP":
        total = 0.0
        cursor = 0.0
        for child in s.children:
            if child.kind != "USE":
                continue
            at = child.at if child.at is not None else cursor
            if child.dur is not None:
                dur = child.dur
            else:
                dur = _natural_cello_dur(child.id, table)
            cursor = at + dur
            total = max(total, cursor)
        return total
    if s.kind == "DEF" and s.type_id == "cello.note":
        # cello.note DEFs do not carry duration; the USE supplies it.
        # Default 1.0 if neither end supplies one.
        return 1.0
    return 1.0


def _expand_cello_grp(
    grp: Statement,
    global_at: float,
    global_dur: float | None,
    inherited_seed: int | None,
    prev_gesture_id: str | None,
    table: dict[str, Statement],
    reachable: set[str],
    res: CelloResolution,
    instance_counters: dict[str, int],
) -> tuple[float, str | None]:
    """Expand a GRP. Returns (end_time, last_gesture_id_seen).

    The last_gesture_id_seen lets transition_from work even without
    being explicitly written: a cello.note USE without
    `transition_from=` inherits the previous note's gesture as the
    transition source.
    """
    # GRP-level seed takes effect for this scope.
    effective_seed = grp.seed if grp.seed is not None else inherited_seed

    # Sequential timing (the cello dialect uses sequential mode).
    cursor = 0.0
    local_end = 0.0
    resolved_uses: list[tuple[Statement, float, float]] = []
    for child in grp.children:
        if child.kind != "USE":
            continue
        local_at = child.at if child.at is not None else cursor
        if child.dur is not None:
            local_dur = child.dur
        else:
            local_dur = _natural_cello_dur(child.id, table)
        resolved_uses.append((child, local_at, local_dur))
        cursor = local_at + local_dur
        local_end = max(local_end, cursor)

    scale = 1.0
    if global_dur is not None and local_end > 0.0:
        scale = global_dur / local_end

    last_gesture = prev_gesture_id

    for child, local_at, local_dur in resolved_uses:
        child_global_at = global_at + local_at * scale
        child_global_dur = local_dur * scale
        target = table.get(child.id) if child.id else None
        if target is None:
            continue

        # Recurse into reachable cello-containing GRPs.
        if target.kind == "GRP":
            _, last_gesture = _expand_cello_grp(
                grp=target,
                global_at=child_global_at,
                global_dur=child_global_dur,
                inherited_seed=effective_seed,
                prev_gesture_id=last_gesture,
                table=table, reachable=reachable, res=res,
                instance_counters=instance_counters,
            )
            continue

        # A direct USE of a cello.note DEF.
        if target.kind == "DEF" and target.type_id == "cello.note":
            note = _resolve_cello_note(
                use=child, note_def=target,
                global_at=child_global_at, global_dur=child_global_dur,
                inherited_seed=effective_seed,
                prev_gesture=last_gesture,
                table=table, res=res,
                instance_counters=instance_counters,
            )
            res.notes.append(note)
            last_gesture = note.gesture_id

    return (global_at + local_end * scale, last_gesture)


def _resolve_cello_note(
    use: Statement,
    note_def: Statement,
    global_at: float,
    global_dur: float,
    inherited_seed: int | None,
    prev_gesture: str | None,
    table: dict[str, Statement],
    res: CelloResolution,
    instance_counters: dict[str, int],
) -> CelloNoteResolved:
    """Resolve one USE of a cello.note DEF into a CelloNoteResolved."""
    # Pitch: from DEF, or overridden in the USE (cello.note's `pitch`
    # parameter; conventionally on the DEF, but USE override allowed).
    pitch = use.params.get("pitch") or note_def.params.get("pitch") or "?"

    # Gesture: from USE override `gesture=`, or DEF param `gesture=`.
    # In both cases we expect a `('ref', 'gesture_id')` value.
    gesture_value = (
        use.params.get("gesture") or note_def.params.get("gesture")
    )
    gesture_id: str | None = None
    if isinstance(gesture_value, tuple) and gesture_value[0] == "ref":
        gesture_id = gesture_value[1]
    elif isinstance(gesture_value, str):
        gesture_id = gesture_value

    # Transition: explicit USE override `transition_from=ref(g)` or the
    # previous note's gesture (implicit chaining).
    trans_value = use.params.get("transition_from")
    explicit_trans: str | None = None
    if isinstance(trans_value, tuple) and trans_value[0] == "ref":
        explicit_trans = trans_value[1]
    elif isinstance(trans_value, str):
        explicit_trans = trans_value

    transition_from = explicit_trans  # explicit wins; implicit not auto-set
    # Implicit chaining: cello musicians naturally play one note after
    # another; the transition is implicit. v0.3 keeps the marker
    # EXPLICIT — authors who want the implicit case write
    # `transition_from=ref(prev_id)` themselves. This avoids surprise
    # behavior. Recorded here for future reconsideration.

    # Resolve transition rule.
    trans_resolver: str | None = None
    trans_runtime: bool = False
    if transition_from:
        from_base = _base_of(transition_from, res)
        to_base = _base_of(gesture_id, res) if gesture_id else None
        trans_resolver, trans_runtime = lookup_cello_transition(
            from_base, to_base,
        )

    # Seed bookkeeping: instance counter is per-gesture-id-within-scene.
    seed_tuple: tuple[int, str, int] | None = None
    if gesture_id and gesture_id in res.gestures:
        g = res.gestures[gesture_id]
        if g.humanize_amount is not None:
            # Determine parent seed for this humanize:
            # explicit MOD seed wins; otherwise inherited GRP seed.
            parent = (
                g.humanize_seed_explicit
                if g.humanize_seed_explicit is not None
                else inherited_seed
            )
            if parent is None:
                res.warnings.append(
                    f"humanize on {gesture_id} has no seed source; "
                    f"add a GRP seed= or explicit seed in the MOD"
                )
                parent = 0
            counter = instance_counters.get(gesture_id, 0)
            seed_tuple = (parent, gesture_id, counter)
            instance_counters[gesture_id] = counter + 1

    # USE-level seed override (extends the model; very rarely written).
    use_seed = use.params.get("seed")
    if use_seed is not None and seed_tuple is not None:
        seed_tuple = (int(use_seed), seed_tuple[1], seed_tuple[2])

    return CelloNoteResolved(
        t=global_at, pitch=str(pitch), dur=global_dur,
        gesture_id=gesture_id,
        transition_from=transition_from,
        transition_resolver=trans_resolver,
        transition_runtime_state=trans_runtime,
        inherited_seed=inherited_seed,
        seed_tuple=seed_tuple,
    )


def _base_of(gesture_id: str, res: CelloResolution) -> str | None:
    g = res.gestures.get(gesture_id)
    return g.base if g else None


def render_cello_resolution(res: CelloResolution) -> str:
    """Stable text dump for diffable reference output."""
    lines: list[str] = []
    lines.append(f"# cello resolution: "
                 f"{len(res.gestures)} gestures, {len(res.notes)} notes")
    if res.warnings:
        lines.append(f"# warnings: {len(res.warnings)}")
        for w in res.warnings:
            lines.append(f"# WARN  {w}")
    lines.append("")
    lines.append("# gesture variants (sorted by id):")
    for gid in sorted(res.gestures):
        lines.extend(res.gestures[gid].as_lines())
        lines.append("")
    lines.append("# note events (in performance order):")
    for note in res.notes:
        lines.append(note.as_line())
    return "\n".join(lines) + "\n"




def detect_dialects(
    stmts: list[Statement],
    root: str = "demo_root",
) -> set[str]:
    """Return the set of dialect prefixes used by reachable DEFs."""
    table = collect_top_level_ids(stmts)
    reachable = reachable_from(table, root, top_level=stmts)
    dialects: set[str] = set()
    for sid in reachable:
        s = table.get(sid)
        if s is None:
            continue
        if s.kind == "DEF" and s.type_id:
            dialects.add(s.type_id.split(".", 1)[0])
        elif s.kind == "MOD":
            cur = sid
            while cur in table and table[cur].kind == "MOD":
                cur = table[cur].src_id
            root_def = table.get(cur) if cur else None
            if root_def and root_def.kind == "DEF" and root_def.type_id:
                dialects.add(root_def.type_id.split(".", 1)[0])
    return dialects


# =====================================================================
# CLI driver.
# =====================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", help="path to .spine file")
    ap.add_argument("--root", default="demo_root",
                    help="root GRP id for reachability (default: demo_root)")
    ap.add_argument("--dump-reachable", action="store_true",
                    help="print the reachability set and exit")
    ap.add_argument("--mode", choices=["auto", "music", "patch", "cello"],
                    default="auto",
                    help="output mode (default: auto-detect by dialect)")
    args = ap.parse_args()

    with open(args.file, "r", encoding="utf-8") as f:
        text = f.read()

    stmts = parse(text)

    if args.dump_reachable:
        table = collect_top_level_ids(stmts)
        reachable = reachable_from(table, args.root, top_level=stmts)
        all_ids = set(table.keys())
        dropped = all_ids - reachable
        print(f"reachable from {args.root!r}: {sorted(reachable)}")
        print(f"dropped (unreachable):       {sorted(dropped)}")
        return 0

    mode = args.mode
    if mode == "auto":
        dialects = detect_dialects(stmts, root=args.root)
        if "cello" in dialects:
            mode = "cello"
        elif "patch" in dialects:
            mode = "patch"
        else:
            mode = "music"

    if mode == "music":
        events = expand(stmts, root=args.root)
        for ev in events:
            print(ev.as_line())
    elif mode == "patch":
        graph = expand_patch(stmts, root=args.root)
        sys.stdout.write(render_patch_graph(graph))
        if graph.warnings:
            for w in graph.warnings:
                print(f"warning: {w}", file=sys.stderr)
    elif mode == "cello":
        res = expand_cello(stmts, root=args.root)
        sys.stdout.write(render_cello_resolution(res))
        if res.warnings:
            for w in res.warnings:
                print(f"warning: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
