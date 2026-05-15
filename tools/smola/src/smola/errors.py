"""SMOLA error reporting.

Every error carries source location and a human-readable explanation.
SMOLA halts on the first error; no recovery is attempted.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class SourceLoc:
    """A position in a SMOLA source file."""
    filename: str
    line_no: int            # 1-based
    line_text: str          # the full source line, without newline

    def format(self) -> str:
        return f"{self.filename}:{self.line_no}: {self.line_text}"


class SmolaError(Exception):
    """Base class for all SMOLA preprocessing errors.

    Always carries a SourceLoc and may carry extra context.
    """

    def __init__(self, loc: Optional[SourceLoc], message: str,
                 hint: Optional[str] = None):
        self.loc = loc
        self.message = message
        self.hint = hint
        super().__init__(self._format())

    def _format(self) -> str:
        parts = []
        if self.loc is not None:
            parts.append(f"{self.loc.filename}:{self.loc.line_no}: error: {self.message}")
            parts.append(f"    {self.loc.line_text}")
        else:
            parts.append(f"error: {self.message}")
        if self.hint is not None:
            parts.append(f"hint: {self.hint}")
        return "\n".join(parts)


class LexError(SmolaError):
    """A line could not be lexed."""


class ParseError(SmolaError):
    """A line was lexed but did not parse as any known directive."""


class RegAllocError(SmolaError):
    """The register allocator hit an inconsistent state.

    Examples: pool exhausted, double-bind, use-after-free.
    """


class StructError(SmolaError):
    """A struct declaration or field reference was malformed."""


class FrameError(SmolaError):
    """A function-frame issue: unclosed function, etc."""
