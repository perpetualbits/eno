"""SMOLA lexer.

Line-oriented. Each source line becomes one Line object carrying:
  - its source location
  - its classified kind
  - the tokens that follow the kind discriminator

The lexer does not interpret directives. It only splits and classifies.
The parser decides what each line means.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .errors import LexError, SourceLoc


class LineKind(Enum):
    BLANK = "blank"               # empty or whitespace-only
    COMMENT = "comment"           # starts with # or //
    PASSTHROUGH = "passthrough"   # starts with !
    SMOLA_DIRECTIVE = "smola"     # starts with .smola.
    GAS_DIRECTIVE = "gas"         # starts with . but not .smola.
    LABEL = "label"               # <ident>: (possibly followed by more)
    INSN_SMOLA = "insn_smola"     # mnemonic in ALL CAPS -> SMOLA pseudo-insn
    INSN_RAW = "insn_raw"         # mnemonic in lowercase -> raw GAS line


@dataclass
class Line:
    """One lexed line of SMOLA source."""
    loc: SourceLoc
    kind: LineKind
    head: str = ""                # the discriminator token (mnemonic, directive name, label name)
    tail: str = ""                # everything after the head, stripped, original spacing collapsed
    trailing_comment: str = ""    # any "# ..." that followed the line content


def _split_trailing_comment(text: str) -> tuple[str, str]:
    """Split off a trailing comment if present.

    Recognizes '#' and '//' as comment starts, but only when they are
    not inside a string. SMOLA assembly never has strings in directive
    or instruction arguments in v1, so we do a simple search.
    """
    # Look for # or // outside of any quotes (v1: assume none).
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


def lex_line(filename: str, line_no: int, raw: str) -> Line:
    """Lex a single source line.

    Newline stripping is the caller's responsibility, but we tolerate
    trailing whitespace.
    """
    line_text = raw.rstrip('\n').rstrip('\r')
    loc = SourceLoc(filename=filename, line_no=line_no, line_text=line_text)
    stripped = line_text.strip()

    if stripped == "":
        return Line(loc=loc, kind=LineKind.BLANK)

    # Full-line comments.
    if stripped.startswith('#') or stripped.startswith('//'):
        return Line(loc=loc, kind=LineKind.COMMENT, tail=stripped)

    # Escape hatch.
    if stripped.startswith('!'):
        # Pass through with the ! removed and the original indentation
        # preserved if reasonable. We use the stripped tail; the caller
        # may decide how to format.
        return Line(loc=loc, kind=LineKind.PASSTHROUGH,
                    tail=stripped[1:].lstrip())

    # Split off any trailing comment now so kind detection is clean.
    body, trail = _split_trailing_comment(stripped)
    if body == "":
        # The whole line was a comment after all.
        return Line(loc=loc, kind=LineKind.COMMENT, tail=trail)

    # SMOLA directives.
    if body.startswith(".smola."):
        rest = body[len(".smola."):]
        head, _, tail = rest.partition(' ')
        if head == "":
            raise LexError(loc, "empty SMOLA directive",
                           hint="expected .smola.<keyword>")
        # The tail keeps everything after the first space.
        return Line(loc=loc, kind=LineKind.SMOLA_DIRECTIVE,
                    head=head, tail=tail.strip(), trailing_comment=trail)

    # Local labels like ".Lloop:" start with '.' but end with ':'.
    # Recognize them before classifying as GAS directive.
    if (body.startswith('.') and body.endswith(':')
            and ':' not in body[:-1]):
        head = body[:-1]
        # The head looks like an identifier-ish thing; allow GAS local
        # label syntax which permits more characters than C idents.
        return Line(loc=loc, kind=LineKind.LABEL, head=head,
                    trailing_comment=trail)

    # GAS directives.
    if body.startswith('.'):
        head, _, tail = body.partition(' ')
        return Line(loc=loc, kind=LineKind.GAS_DIRECTIVE,
                    head=head, tail=tail.strip(), trailing_comment=trail)

    # Labels. A label is `<ident>:` optionally followed by more content
    # on the same line. v1: if there is anything after the colon, we
    # error and ask the user to put it on the next line. This keeps the
    # parser simple.
    if ':' in body:
        head, _, after = body.partition(':')
        head = head.strip()
        after = after.strip()
        if not _is_ident(head):
            raise LexError(loc, f"invalid label name {head!r}",
                           hint="labels must be valid identifiers")
        if after != "":
            raise LexError(loc,
                           "content after a label must be on the next line",
                           hint="this keeps SMOLA's line model strict; split into two lines")
        return Line(loc=loc, kind=LineKind.LABEL, head=head,
                    trailing_comment=trail)

    # Instruction lines. Split on first whitespace to get the mnemonic.
    head, _, tail = body.partition(' ')
    head = head.strip()
    tail = tail.strip()
    if head == "":
        raise LexError(loc, "empty instruction line")

    if _is_all_upper_ident(head):
        return Line(loc=loc, kind=LineKind.INSN_SMOLA,
                    head=head, tail=tail, trailing_comment=trail)
    else:
        return Line(loc=loc, kind=LineKind.INSN_RAW,
                    head=head, tail=tail, trailing_comment=trail)


def _is_ident(s: str) -> bool:
    if not s:
        return False
    if not (s[0].isalpha() or s[0] == '_'):
        return False
    return all(c.isalnum() or c == '_' for c in s)


def _is_all_upper_ident(s: str) -> bool:
    """An all-uppercase mnemonic, with optional '.' and digits.

    Examples that match: ADD, LOAD_FIELD, VAR.T, VAR.A, CALL, BEQZ.
    Examples that don't:  add, c.addi, _start, ld.
    """
    if not s:
        return False
    has_letter = False
    for c in s:
        if c.isalpha():
            if c.islower():
                return False
            has_letter = True
        elif c.isdigit() or c == '_' or c == '.':
            continue
        else:
            return False
    return has_letter


def lex_source(filename: str, text: str) -> List[Line]:
    """Lex an entire source string.

    Returns a list of Line objects, one per input line, including blanks
    and comments.
    """
    lines: List[Line] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        lines.append(lex_line(filename, i, raw))
    return lines
