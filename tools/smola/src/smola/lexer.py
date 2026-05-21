"""SMOLA v0.3 lexer.

The lexer's job is line classification. In v0.3, classification depends
on *what* the first token is — a known SMOLA keyword, a known RISC-V
mnemonic, a GAS directive, a label, or a comment. Unrecognized lines
are errors. This is what makes typos strict: `addii counter, 1` no
longer silently passes through to GAS to fail there with a less
helpful message.

Classification, in priority order:

  1. Empty / whitespace only          -> BLANK
  2. Starts with `#` or `//`          -> COMMENT
  3. After trimming, body is empty    -> COMMENT
  4. Matches `<ident>:` or `.L<id>:`  -> LABEL
  5. Starts with `.` (after the
     label check above)               -> GAS_DIRECTIVE (passthrough)
  6. First token is a SMOLA keyword
     (from SMOLA_KEYWORDS)            -> SMOLA
  7. First token is a known RISC-V
     mnemonic (from mnemonics.py)     -> RV_INSN (passthrough)
  8. Anything else                    -> error: unknown mnemonic

The order matters. The label check runs before the directive check so
`.Lloop:` lexes as a label, not a GAS directive. The SMOLA keyword
check runs before the mnemonic check so a future SMOLA addition can
shadow a hypothetical mnemonic with the same name (none currently
exist; this is structural).

The `raw` keyword is special: it's a SMOLA keyword, but its body
isn't parsed further by the lexer — the entire tail of the line is
emitted verbatim. This is the escape hatch for instructions SMOLA's
mnemonic table doesn't yet know about.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List

from .errors import LexError, SourceLoc
from .mnemonics import is_known_mnemonic


# The complete set of SMOLA keywords. Maintained as a closed
# vocabulary — adding to this set requires a spec amendment. The
# lexer checks this set before the RISC-V mnemonic table; if any
# keyword ever conflicts with a real mnemonic, the keyword wins and
# we'd need to rename either it or fall back on a different mechanism.
# None currently conflict.
#
# The keyword vocabulary covers three categories of type-naming:
#
#   - default declarations: `int`, `ptr`, `f32`, `f64`, `vec`. The
#     ones you reach for when the width is the obvious default (`int`
#     = use the integer register file, width per-instruction) or when
#     the width is fixed by the type's nature (`ptr` is always 8
#     bytes, `f32` is always 4 bytes).
#
#   - width-typed integer variants: `i8`/`u8`/.../`u64`. Used when
#     the user wants to document at the declaration site exactly what
#     width the variable holds. Same allocation pool as `int` — the
#     register file is 64-bit regardless. The width is documentation
#     only and appears in the bindings table of the generated `.s`.
#
#   - struct field types: these are the same as the data-section type
#     keywords (handled as the second meaning of the same words in a
#     data section context). The struct parser uses these directly.
#
# Note: `flt` was a v0.3 keyword that is REMOVED in this refinement.
# Use `f32` or `f64` instead. The lexer will reject `flt` as an
# unknown mnemonic; the translator catches that early-but-not-too-
# early and gives a helpful migration hint.
#
# Storage suffixes `.s` (callee-saved) and `.a` (argument) are
# allowed on every register-declaration keyword. We list each
# (keyword, suffix) combination as a separate entry so the lexer can
# match the whole token in one hash lookup.
def _build_keywords() -> frozenset:
    """Build the SMOLA keyword set from a small structured spec.

    Returns a frozenset of every legal SMOLA-keyword token form. The
    function exists so the keyword set is auditable as a structure
    rather than as a flat 40-entry list — adding a new width to the
    integer family or a new storage class only edits one line here.
    """
    out = set()

    # Block-shaping and lifetime keywords.
    out.update({
        "func", "end", "scope", "endscope",
        "struct", "stack", "zap",
    })

    # Field access pseudo-instructions.
    out.update({"load_field", "store_field", "addr_field"})

    # Raw escape hatch.
    out.add("raw")

    # Register-typed declaration keywords. Bare form + .s suffix +
    # .a suffix. `vec.s` is intentionally omitted because the RVV ABI
    # defines no callee-saved vector registers; the regalloc rejects
    # the combination separately if it ever reaches that layer.
    int_widths = ["int", "i8", "u8", "i16", "u16",
                  "i32", "u32", "i64", "u64"]
    for kw in int_widths:
        out.add(kw)            # bare declaration
        out.add(f"{kw}.s")     # callee-saved
        out.add(f"{kw}.a")     # argument

    # Pointer keyword (always 8 bytes, no width variants).
    for kw in ["ptr"]:
        out.add(kw)
        out.add(f"{kw}.s")
        out.add(f"{kw}.a")

    # Float keywords. Explicit precision required — no `flt` alias.
    for kw in ["f32", "f64"]:
        out.add(kw)
        out.add(f"{kw}.s")
        out.add(f"{kw}.a")

    # Vector keyword. No .s variant (RVV ABI has no callee-saved
    # vector registers). The .a variant exists for vector arguments.
    out.add("vec")
    out.add("vec.a")

    return frozenset(out)


SMOLA_KEYWORDS = _build_keywords()


# Tokens that, if seen as the first token of a line, produce a
# helpful migration hint pointing at the v0.3 → v0.3-refined change
# rather than the generic "unknown mnemonic" error. Used by the
# lexer's error path. Each entry is (bad_token -> message_text).
DEPRECATED_KEYWORDS = {
    "flt":   "use `f32` or `f64` (the `flt` keyword was removed)",
    "flt.s": "use `f32.s` or `f64.s`",
    "flt.a": "use `f32.a` or `f64.a`",
}


class LineKind(Enum):
    """The line classifications the translator dispatches on.

    Most LineKinds are decided purely from the line's content. The
    DATA_VALUES kind is special: the lexer assigns it whenever the
    line's first token looks like a numeric literal, but the
    translator only *accepts* it as a continuation if the current
    section is a data section and the previous emission was a data
    directive. Outside that specific context, DATA_VALUES is treated
    as a strict-typo error by the translator (with the same kind of
    "unknown mnemonic" diagnostic the lexer would have produced).

    This split (lexer recognizes shape, translator owns semantics)
    keeps the lexer stateless across lines.
    """
    BLANK = "blank"             # empty / whitespace
    COMMENT = "comment"         # `#` or `//` line
    LABEL = "label"             # `<ident>:` or `.L<id>:`
    GAS_DIRECTIVE = "gas"       # starts with `.` (not a label)
    SMOLA = "smola"             # first token is a SMOLA keyword
    RV_INSN = "rv_insn"         # first token is a known RV mnemonic
    DATA_VALUES = "data_values" # first token is a numeric literal
                                # (only valid as data continuation)


@dataclass
class Line:
    """One classified source line."""

    # Source position. Always populated.
    loc: SourceLoc

    # Classification result.
    kind: LineKind

    # The discriminator within the kind:
    #   - SMOLA: the keyword (e.g. "func", "int", "int.s", "load_field")
    #   - LABEL: the label name (colon stripped)
    #   - RV_INSN: the mnemonic (e.g. "addi", "vfadd.vv")
    #   - GAS_DIRECTIVE: the directive name (e.g. ".section", ".globl")
    #   - BLANK / COMMENT: unused
    head: str = ""

    # Everything after the head, with surrounding whitespace stripped.
    tail: str = ""

    # Trailing `# ...` or `// ...` comment, if present. Preserved so
    # the translator can echo it into the generated `.s`.
    trailing_comment: str = ""

    def is_smola_keyword(self, kw: str) -> bool:
        """Convenience: does this line use a specific SMOLA keyword?"""
        return self.kind == LineKind.SMOLA and self.head == kw


def _split_trailing_comment(text: str) -> tuple[str, str]:
    """Cut off any trailing `#` or `//` comment from a line body.

    Returns (body_before_comment, comment_with_marker). Returns
    (text, "") if there's no comment.

    Simple scan: walk for the earliest `#` or `//`. Safe because v0.3
    has no string literals in operands.
    """
    h = text.find('#')
    s = text.find('//')
    cut = -1
    if h >= 0 and s >= 0:
        cut = min(h, s)
    elif h >= 0:
        cut = h
    elif s >= 0:
        cut = s
    if cut < 0:
        return text, ""
    return text[:cut].rstrip(), text[cut:]


def _is_ident(s: str) -> bool:
    """Is `s` a C-style identifier? (first letter or _, rest alnum or _)"""
    if not s:
        return False
    if not (s[0].isalpha() or s[0] == '_'):
        return False
    return all(c.isalnum() or c == '_' for c in s)


def lex_line(filename: str, line_no: int, raw: str) -> Line:
    """Classify a single source line.

    Raises LexError if the line doesn't fit any recognized
    classification (the strict-typo path).
    """
    # Normalize line endings.
    line_text = raw.rstrip('\n').rstrip('\r')
    loc = SourceLoc(filename=filename, line_no=line_no, line_text=line_text)
    stripped = line_text.strip()

    # Rule 1: blank.
    if stripped == "":
        return Line(loc=loc, kind=LineKind.BLANK)

    # Rule 2: full-line comment.
    if stripped.startswith('#') or stripped.startswith('//'):
        return Line(loc=loc, kind=LineKind.COMMENT, tail=stripped)

    # Cut off any trailing comment so classification only looks at
    # actual code.
    body, trail = _split_trailing_comment(stripped)
    if body == "":
        # The whole line was effectively a comment.
        return Line(loc=loc, kind=LineKind.COMMENT, tail=trail)

    # Rule 4: labels. We check this before the GAS-directive rule so
    # `.Lloop:` is recognized correctly.
    #
    # Local labels (`.L<name>:`): start with `.`, end with `:`, no
    # other colons inside.
    if (body.startswith('.') and body.endswith(':')
            and ':' not in body[:-1]):
        return Line(loc=loc, kind=LineKind.LABEL, head=body[:-1],
                    trailing_comment=trail)
    # Plain labels (`<ident>:`): identifier followed by colon, nothing
    # after.
    if ':' in body:
        head, _, after = body.partition(':')
        head = head.strip()
        after = after.strip()
        if _is_ident(head):
            if after != "":
                raise LexError(
                    loc,
                    "content after a label must be on the next line",
                    hint="split the label onto its own line",
                )
            return Line(loc=loc, kind=LineKind.LABEL, head=head,
                        trailing_comment=trail)
        # Falls through to the rest of the rules. A colon in the middle
        # without a valid identifier is unusual but we let it through
        # to be classified by content.

    # Rule 5: GAS directives. Pass through verbatim.
    if body.startswith('.'):
        head, _, tail = body.partition(' ')
        return Line(loc=loc, kind=LineKind.GAS_DIRECTIVE,
                    head=head, tail=tail.strip(),
                    trailing_comment=trail)

    # Split off the first token for keyword/mnemonic classification.
    head, _, tail = body.partition(' ')
    head = head.strip()
    tail = tail.strip()

    # Rule 6: SMOLA keyword. The `head` is matched exactly against
    # SMOLA_KEYWORDS. The translator handles any further parsing
    # within the line.
    if head in SMOLA_KEYWORDS:
        return Line(loc=loc, kind=LineKind.SMOLA,
                    head=head, tail=tail,
                    trailing_comment=trail)

    # Rule 6b: deprecated SMOLA keyword. Catches the removed `flt`
    # family and any future deprecated forms before falling through
    # to the generic "unknown mnemonic" error. The hint is more
    # actionable for these specific cases.
    if head in DEPRECATED_KEYWORDS:
        raise LexError(
            loc,
            f"keyword {head!r} is no longer supported",
            hint=DEPRECATED_KEYWORDS[head],
        )

    # Rule 7: known RISC-V mnemonic.
    if is_known_mnemonic(head):
        return Line(loc=loc, kind=LineKind.RV_INSN,
                    head=head, tail=tail,
                    trailing_comment=trail)

    # Rule 7b: data-values continuation candidate. The line's first
    # token looks like a numeric literal — a hex/dec/octal integer,
    # a float, or a sign-prefixed number. The lexer doesn't have
    # enough state to know if this is a legitimate data continuation
    # or a stray fragment of text; it classifies as DATA_VALUES and
    # lets the translator decide.
    #
    # Symbol-reference continuations (e.g. a jump table where each
    # entry is an identifier) are NOT caught here — they'd look like
    # bare identifiers and trip the unknown-mnemonic check below.
    # For those, the user repeats the type keyword on each line.
    # Numeric-data continuations (coefficient blocks, byte arrays)
    # work seamlessly.
    if _looks_like_numeric_literal(head):
        return Line(loc=loc, kind=LineKind.DATA_VALUES,
                    head=head, tail=tail,
                    trailing_comment=trail)

    # Rule 8: unrecognized. Strict-typo error.
    #
    # Give the user a helpful hint about what they might have meant.
    # Common typo categories:
    #   - `int counter` typed as something else like `INT counter`
    #     (we deliberately don't accept case variation in v0.3; this
    #     keeps the surface narrow)
    #   - mnemonic typos like `addii` for `addi`
    #   - missing leading `.` on a GAS directive like `section`
    # For v0.3 we just say "unknown mnemonic" and let the user figure
    # it out. A fuzzy-match hint would be nice but is a v0.4 polish.
    raise LexError(
        loc,
        f"unknown mnemonic or keyword {head!r}",
        hint=(
            "expected a known RISC-V instruction, a SMOLA keyword, "
            "a GAS directive starting with '.', or a label"
        ),
    )


def _looks_like_numeric_literal(s: str) -> bool:
    """Does `s` look like a numeric literal in GAS-compatible form?

    Accepts:
      - integer literals with optional sign: `42`, `-5`, `+1`
      - hex literals: `0x1A`, `-0xff`
      - octal literals: `0755`
      - binary literals: `0b1010` (some GAS dialects accept)
      - decimal floats: `0.5`, `-1.5`, `.5`
      - scientific notation: `1e3`, `1.5e-10`, `-1.234e+5`
      - hex floats: `0x1.fp3` (C99-style, accepted by recent GAS)

    Does NOT accept identifiers that happen to start with a digit
    (which would be invalid anyway), and does NOT accept symbol
    references (which the data-continuation rule doesn't cover).

    The function is a syntactic shape check, not a full parser —
    `1.2.3` would pass the shape check but GAS would reject it.
    SMOLA passes the literal through unchanged; GAS reports any
    real numeric malformation at assembly time. We just need to be
    confident "this looks like a number, not an identifier."
    """
    if not s:
        return False
    # Strip a leading sign for the rest of the analysis.
    rest = s[1:] if s[0] in '+-' else s
    if not rest:
        return False
    # Hex literal (optionally with hex float).
    if rest.startswith(('0x', '0X')):
        return len(rest) > 2 and all(
            c in '0123456789abcdefABCDEF.pP+-' for c in rest[2:]
        )
    # Plain numeric: must start with a digit or `.<digit>`.
    if rest[0].isdigit():
        return True
    if rest[0] == '.' and len(rest) > 1 and rest[1].isdigit():
        return True
    return False


def lex_source(filename: str, text: str) -> List[Line]:
    """Lex an entire source string, one Line per input line.

    Blanks and comments are preserved (not filtered) because the
    translator re-emits them — comment transfer to the generated `.s`
    requires keeping them in the stream.
    """
    return [
        lex_line(filename, i, raw)
        for i, raw in enumerate(text.splitlines(), start=1)
    ]
