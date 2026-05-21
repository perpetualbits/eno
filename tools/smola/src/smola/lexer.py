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
SMOLA_KEYWORDS = frozenset({
    # Block-shaping
    "func", "end", "scope", "endscope",
    # Declarations and lifetimes
    "struct", "stack", "zap",
    # Type declarations (the bare type names act as keywords; the
    # storage suffixes like 'int.s', 'int.a', 'flt.s', 'flt.a' are
    # parsed by the translator on the first token after splitting at
    # the dot).
    "int", "ptr", "flt", "vec",
    # Variants with storage suffix. We list each explicitly so the
    # lexer doesn't need to know about the suffix syntax. The
    # translator dispatches on these.
    "int.s", "int.a", "ptr.s", "ptr.a",
    "flt.s", "flt.a", "vec.a",
    # Float field types (used in initialization, e.g. `f32 gain 0.75`).
    "f32", "f64",
    "f32.s", "f32.a", "f64.s", "f64.a",
    # Struct field access
    "load_field", "store_field", "addr_field",
    # Argument-shuffling call (raw `call` is a RISC-V pseudo-insn and
    # is handled differently; see translator's `_handle_call_line`).
    # Note: we do NOT add 'call' to SMOLA_KEYWORDS because it conflicts
    # with the standard RISC-V `call` pseudo-instruction. The
    # translator distinguishes raw `call target` from SMOLA `call
    # target, args...` by whether a comma appears in the tail.
    # Raw escape hatch.
    "raw",
})


class LineKind(Enum):
    """The five-way classification the translator dispatches on."""
    BLANK = "blank"             # empty / whitespace
    COMMENT = "comment"         # `#` or `//` line
    LABEL = "label"             # `<ident>:` or `.L<id>:`
    GAS_DIRECTIVE = "gas"       # starts with `.` (not a label)
    SMOLA = "smola"             # first token is a SMOLA keyword
    RV_INSN = "rv_insn"         # first token is a known RV mnemonic


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

    # Special case for the `call` mnemonic: GAS treats `call` as a
    # pseudo-instruction, but SMOLA needs to distinguish raw
    # `call target` from SMOLA `call target, arg1, arg2`. We classify
    # `call` as RV_INSN here; the translator examines the tail to
    # decide which path to take.
    #
    # The same logic applies in spirit to any pseudo-instruction that
    # SMOLA might want to extend, though `call` is the only one in v0.3.

    # Rule 7: known RISC-V mnemonic.
    if is_known_mnemonic(head):
        return Line(loc=loc, kind=LineKind.RV_INSN,
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
