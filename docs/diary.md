# ENO Project Diary

Running log of thought processes, design reasoning, and discoveries
from Claude Code sessions. The audience is Roland, his daughter, and
any future crew. Each entry covers the *why* and *how* — the session
summary covers the *what*.

Tags: `#subsystem`, `#design-decision`, `#bug`, `#discovery`,
`#tradeoff`, `#open-question`, `#refactor`, `#caution`.

Entries are append-only. Most recent at the bottom.

---

## 2026-05-21 — Repo migration and SMOLA v0.3.1
*#smola #design-decision #discovery #tradeoff*

### Migration session

The repo had accumulated naming debt: `lib/wavelet`, `lib/synth`,
`tools/waveviz`, `tools/shaderbake`, and `spine_runtime_model.md` all
had provisional names that the team had since settled on replacing.
The migration was straightforward except for one judgment call: the
internal filenames inside `lib/crest/` (`wavelet.h`, `wavelet.c`,
`test_wavelet.c`) were not renamed. Renaming them would have touched
build scripts, include paths, and potentially confused `git blame`.
The design doc (§9) records this as intentional deferred work, to be
done in a dedicated "crest bases" session when the C sources are
actually being touched. The lesson: renames that cross a compilation
boundary deserve their own focused session, not a piggyback.

### SMOLA v0.3.1 — why the lexer is stateful at the source level

The `txt`/`eot` heredoc block is the first multi-line construct in
SMOLA. The question was where to put the state: in `lex_line` (making
the single-line classifier stateful) or in `lex_source` (the
source-level pass that calls `lex_line` in a loop).

I kept `lex_line` stateless. The reason: `lex_line` is conceptually
a pure function — given one line of text, return a classification.
Every test that calls `lex_line` directly relies on this. Making it
stateful would require threading context through all callers or making
it a method, which ripples everywhere.

`lex_source` already owns the loop over lines; adding a `txt_active`
boolean there is a one-line change that costs almost nothing. The
`TXT_BLOCK` / `TXT_LINE` / `TXT_END` enum values in `LineKind` are
the interface between the two layers: `lex_source` produces them;
`_process_line` dispatches on them.

### SMOLA v0.3.1 — GAS encoding vs pass-through for string escapes

For `str` and `cstr`, I decode SMOLA escape sequences into Python
characters (for byte counting), then re-encode those Python characters
into GAS-safe escape sequences for emission. An alternative would have
been to validate-and-pass-through: confirm the escape is valid, then
emit the SMOLA source text unchanged, since GAS uses the same escape
set.

I chose decode + re-encode because it makes `_encode_for_gas` the
single place that knows how to emit any Python string as GAS-safe
text. The `txt` block handler can reuse the same function for its raw
content lines (which have no SMOLA escapes, only characters that need
quoting for GAS). If I had done pass-through for `str`/`cstr` and a
different path for `txt`, the two code paths would diverge and the
next person to add a string feature would have to reconcile them.

The cost of decode + re-encode is negligible at preprocessor time.

### SMOLA v0.3.1 — why _flush_data_label_size skips zero-byte labels

An empty `str ""` sets `current_data_label` and `current_data_label_bytes = 0`
but emits no `.size`. This is pre-existing behavior for numeric data
directives and I kept it consistent rather than special-casing strings.
The rationale: a zero-byte symbol with a `.size 0` directive is
technically valid GAS, but it is almost certainly a mistake, and
emitting nothing makes the mistake visible (the user gets no `.size`
and can see something is off). An empty `str ""` or `txt`/`eot` with
no content lines is an edge case that probably means the user forgot
to fill in the content.

### SMOLA v0.3.1 — f16/bf16 and reserved keywords strategy

The sub-byte and half-precision keywords were added to `SMOLA_KEYWORDS`
in this release even though they do nothing yet. The reason: if we
wait until they are implemented, user code written in the interim might
use those tokens as variable names or labels. Once that code exists,
adding the keywords becomes a breaking change. Reserving now costs
nothing and preserves the option to implement without breakage.

The split between "not yet implemented" (f16/bf16) and "reserved" (sub-
byte) is intentional: f16/bf16 are real types with a concrete plan;
the sub-byte family is more speculative. The error messages reflect this.

### Comment about the comment rule

One thing I noticed: the project requires heavy comments on all code.
In the SMOLA Python source the comments are already fairly dense (the
existing code sets a good example). But I had to be conscious of it —
my default is to write leaner comments than this project wants. Going
forward I should treat "would a non-Python person understand this
function from its comment alone?" as the bar, not just "is the purpose
clear to a Python developer."
