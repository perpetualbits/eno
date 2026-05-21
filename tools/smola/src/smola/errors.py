"""SMOLA error reporting.

Every error carries a source location (filename, line number, line
text) plus a human-readable message and optional hint. SMOLA halts on
the first error; there is no recovery. The CLI catches SmolaError
and prints the formatted result to stderr.

Any non-SmolaError exception escaping the translator is treated as an
internal bug and produces exit code 2 instead of 1. This split matters:
a SmolaError means "the user wrote something we don't accept" (normal,
expected); anything else means "the tool itself has a problem" (worth
reporting as a bug).
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SourceLoc:
    """A position in a SMOLA source file.

    Captured at lex time and propagated through every later stage. We
    deliberately store the line text on the SourceLoc itself (rather
    than re-reading the file at error-format time), so a SmolaError
    remains useful even if the original file changed or was deleted
    between when the error was raised and when it's printed.
    """
    # Filename as the user passed it on the command line. For stdin,
    # the literal string "<stdin>". We don't canonicalize; the user
    # sees the path they typed.
    filename: str

    # 1-based line number, matching what every editor displays.
    line_no: int

    # The original line, with newline stripped. Used for the
    # under-the-message display.
    line_text: str


class SmolaError(Exception):
    """Base class for every user-facing SMOLA error.

    Carries a SourceLoc (optional only for top-level config errors
    that aren't tied to a specific line), a message, and an optional
    hint. The __init__ formats these into the exception's string for
    the CLI to print.
    """

    def __init__(self, loc: Optional[SourceLoc], message: str,
                 hint: Optional[str] = None):
        # Stash so tests and CLI code can inspect programmatically.
        self.loc = loc
        self.message = message
        self.hint = hint
        # Build the pretty form once and pass to Exception so that
        # str(e) gives the user-facing message directly.
        super().__init__(self._format())

    def _format(self) -> str:
        """Build the multi-line message.

        With location:
            <filename>:<line_no>: error: <message>
                <the offending source line>
            hint: <hint>           (if hint provided)

        Without location:
            error: <message>
            hint: <hint>
        """
        parts = []
        if self.loc is not None:
            # Compiler-style first line. Editors that parse error
            # streams (Emacs compilation-mode, VS Code Problems panel)
            # jump to the right line automatically.
            parts.append(
                f"{self.loc.filename}:{self.loc.line_no}: "
                f"error: {self.message}"
            )
            # Show the offending line, indented under the error.
            parts.append(f"    {self.loc.line_text}")
        else:
            parts.append(f"error: {self.message}")
        if self.hint is not None:
            parts.append(f"hint: {self.hint}")
        return "\n".join(parts)


# The subclasses below carry no extra behavior beyond their identity.
# They exist so tests and callers can distinguish between failure
# categories.

class LexError(SmolaError):
    """A line could not be classified by the lexer.

    Examples: a typo-mnemonic that isn't in the RISC-V table and isn't
    a SMOLA keyword either; a malformed token at the start of a line.
    """


class ParseError(SmolaError):
    """A line was classified but its specific content was invalid.

    Examples: `func` with no name, `int` with no name, `struct` with
    no fields.
    """


class RegAllocError(SmolaError):
    """The register allocator hit an inconsistent state.

    Examples: register pool exhausted, double-binding a name, using a
    name after `zap`, freeing an unknown name.
    """


class StructError(SmolaError):
    """A struct declaration or field reference was malformed.

    Examples: duplicate field name, unknown field type, reference to
    an unknown struct or field.
    """


class FrameError(SmolaError):
    """A function-frame issue.

    Examples: nested function definitions, `end` without matching
    `func`, function reaching EOF without `end`, `scope` used outside
    a function.
    """


class CollisionError(SmolaError):
    """A raw register reference collides with an active binding.

    Fires when the user writes (e.g.) `addi t0, t0, 1` while `t0` is
    bound to some SMOLA name. See spec §2.9.
    """
