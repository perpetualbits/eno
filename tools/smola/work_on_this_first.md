# SMOLA v0.3.x — string data + f16/bf16 stubs + sub-byte reservations

This is a self-contained prompt for Claude Code working in the ENO
monorepo. Read it once end-to-end before doing anything. The design
is locked; your job is implementation, tests, examples, spec, and
session bookkeeping.

---

## Where you are

```
~/git/eno/                     # monorepo root
├── docs/
│   ├── smola_design.md        # canonical SMOLA spec, currently v0.3 + data-section refinements
│   ├── eno_project_index.md   # the map
│   ├── eno_decision_log.md    # append-only log of decisions
│   └── ...
└── tools/
    └── smola/                 # the SMOLA tool
        ├── src/
        │   ├── bin/smola
        │   └── smola/
        │       ├── __init__.py        # __version__ — bump on this turn
        │       ├── mnemonics.py       # RV mnemonic table (untouched)
        │       ├── lexer.py           # SMOLA_KEYWORDS, LineKind, classification
        │       ├── symbols.py         # struct table (untouched)
        │       ├── regalloc.py        # Binding, allocator (untouched)
        │       ├── frame.py           # prologue/epilogue (untouched)
        │       ├── translator.py      # the orchestrator (main work here)
        │       ├── errors.py          # SmolaError + subclasses
        │       └── cli.py
        ├── tests/                     # 114 tests passing currently
        ├── examples/                  # 5 examples
        ├── Makefile
        └── README.md
```

**Start by running `make test` in `tools/smola/`** to confirm you
have the 114-passing baseline before making changes. If that
doesn't pass cleanly, stop and investigate — something is off
with the local install.

## What this turn adds

Three things, listed in priority order. Each can be reverted
independently if needed.

### A. Three new string keywords

Add to the SMOLA keyword vocabulary:

- `str`  — quoted single-line string, no terminator
- `cstr` — quoted single-line string, NUL terminator appended
- `txt`  — heredoc multi-line text, no terminator

All three are **data-section keywords only**. They error in code
sections with the same kind of hint as other data-only keywords.

### B. `f16` and `bf16` stub keywords

Add `f16` and `bf16` to the keyword set, both as code-variable
declarations *and* as data-section declarations. Both error on use
with a "not yet implemented" hint that explains the situation
(Zvfh, vendor extensions, deferred design). The reservation holds
the namespace so future implementation doesn't change source.

### C. Reservation of sub-byte and exotic FP keywords

A keyword pattern `packed.<type>` and the bare tokens `fp8`, `fp4`,
`i4`, `u4`, `i2`, `u2`, `i1`, `u1`, `b1p58` (BitNet 1.58-bit)
recognized by the lexer with a "reserved for future use" error.
Holds the namespace; no semantics committed.

---

## A. String keywords — complete design

### Keyword surface

```
<label>:
    str "..."           # quoted single-line, no terminator
    cstr "..."          # quoted single-line, NUL terminator appended

<label>:
txt <first line of content>
    <continuation line>
    <continuation line>
eot
```

### A.1 `str` — quoted single-line

**Syntax:**
- Exactly: `str "..."` on one line.
- The opening `"` follows `str ` (one space).
- Content runs from the first `"` to the matching closing `"`.
- Anything after the closing `"` may be: nothing, whitespace,
  trailing comment (`#` or `//`).
- Trailing content other than whitespace or comment is a format
  error.

**Escape sequences (full set):**
- `\"` — literal double quote
- `\\` — literal backslash
- `\n` — newline (0x0A)
- `\t` — tab (0x09)
- `\0` — NUL byte (0x00)
- `\xHH` — arbitrary byte where HH is two hex digits
- Any other `\<char>` sequence is a format error.

**UTF-8 handling:**
- The source file is UTF-8. Any UTF-8 bytes inside the quotes
  pass through verbatim into the data section.
- SMOLA does not validate UTF-8 well-formedness. GAS will accept
  whatever bytes you emit; if the user produces malformed UTF-8,
  that's their problem.

**Emission:**

```asm
greeting:
    str "Hello, world!"
```

becomes:

```asm
greeting:
    .balign 1
    .ascii "Hello, world!"
    .size greeting, 13
```

For escapes, decode to bytes and emit via `.ascii` with re-encoded
escapes that GAS understands:

```asm
note:
    str "Line 1\nLine 2"
```

becomes:

```asm
note:
    .balign 1
    .ascii "Line 1\nLine 2"
    .size note, 13
```

(Note: GAS `.ascii` accepts the same `\n`, `\t`, `\\`, `\"`, `\xHH`
escapes, so SMOLA can pass them through with no decode/re-encode
needed *except* for validating that they're in the allowed set.
Reject unknown escapes at SMOLA time so the user gets a clear
SMOLA-level error instead of a downstream GAS error.)

**Byte-count for `.size`:** the count must reflect the actual
byte length of the emitted data (after escape decoding), not the
source character count. `"Hello\n"` is 6 bytes. `"日本"` is 6 bytes
(UTF-8). `"\xff\x00\xaa"` is 3 bytes.

### A.2 `cstr` — quoted with NUL terminator

Identical to `str` in surface and parsing. The only difference:
emit a `.byte 0` after the `.ascii` directive, and add 1 to the
`.size` count.

```asm
title:
    cstr "Epsilon Null"
```

becomes:

```asm
title:
    .balign 1
    .ascii "Epsilon Null"
    .byte 0
    .size title, 13
```

`cstr` is for strings that get passed to C library functions
(`puts`, `printf`, `dlopen`, `open`, Cairo/Pango text rendering,
etc.). These all expect NUL-terminated input.

### A.3 `txt` — heredoc multi-line

**Syntax:**
- The keyword `txt` followed by exactly one space, then the
  first line of content, then end-of-line.
- Continuation lines: each line begins with exactly 4 spaces;
  everything from column 5 onward is content.
- A line containing exactly `eot` (three characters, no leading
  whitespace, no trailing characters except the newline)
  terminates the block.
- Lines that don't match the format are errors with a clear hint.

**Specifically:**

1. **Blank lines inside the block** (zero characters before the
   newline) are accepted as content blank lines. They emit a `\n`
   byte. This handles `txt` blocks with paragraph breaks.
2. **Lines with content but no 4-space prefix** are errors:
   *"continuation line must begin with 4 spaces; got <N> spaces"*.
3. **Lines starting with 4+ spaces** have exactly the first 4
   stripped; the remainder is content. Additional leading spaces
   beyond the first 4 *are* content. Trailing whitespace is also
   content.
4. **No escape sequences in `txt` body.** What you see is what you
   get. The user wants escapes, they use `str` instead.
5. **The terminating newline before `eot`** is part of the content.
   The `eot` line itself is not.

**Example:**

```
greeting:
txt After the Fall, groups of survivors were few and far in between
    اربك تكست هو اول موقع يسمح لزواره الكرام بتحويل الكتابة العربي الى كتابة مفهومة من قبل اغلب برامج التصميم مثل الفوتوشوب و الافترايفكتس
    读写汉字 - 学中文
eot
```

emits the three lines (with their UTF-8 bytes), each followed by
a newline, totaling whatever byte count comes out.

The "eot inside content" edge case:

```
quirky:
txt eot
eot
```

This emits 4 bytes: `e`, `o`, `t`, `\n`. The first `eot` is content
(on the `txt ` line). The second `eot` is the terminator (flush-
left, alone).

**Emission strategy for `txt`:**

Emit one `.ascii` directive per source line, each with an explicit
`\n` at the end:

```asm
greeting:
    .balign 1
    .ascii "After the Fall, groups of survivors were few and far in between\n"
    .ascii "اربك تكست ...\n"
    .ascii "读写汉字 - 学中文\n"
    .size greeting, NNN
```

The byte count for `.size` is the sum of: (each line's UTF-8 byte
length) + 1 (for the newline) over all content lines.

**Forbidden in code sections.** Same error path as other
data-only keywords. Hint: "use a data section (.rodata) for
string literals".

### A.4 Alignment policy for all three

Default: `.balign 1`. Strings are byte-aligned.

If the user needs SIMD-friendly alignment (e.g. loading 16 UTF-8
bytes with `vle8.v` and wanting cache-line alignment), they place
a raw GAS `.balign <N>` directive before the label. SMOLA passes
GAS directives through unchanged, so this works without any
SMOLA-level feature.

A future `align <N>` keyword as part of the SMOLA vocabulary is
reserved (don't implement now). If a user writes `align 16` in
this turn, error with "reserved for future use".

### A.5 Lexer changes

Add to `SMOLA_KEYWORDS`:

```python
"str", "cstr", "txt"
```

Add a new `LineKind`:

```python
class LineKind(Enum):
    ...
    TXT_BLOCK = "txt_block"   # the `txt` keyword line
    TXT_LINE  = "txt_line"    # a continuation line in a txt body
    TXT_END   = "txt_end"     # the flush-left `eot` terminator
```

**Lexer state for `txt` blocks:** The lexer needs to know when
it's inside a `txt` body so that lines with content but no
SMOLA-keyword/RV-mnemonic shape (just text) are classified as
TXT_LINE instead of erroring.

Implementation: the lexer's main classification function takes
a `txt_active: bool` parameter (or maintains state across calls).
When a `txt` keyword line is emitted, set `txt_active = True`.
While `txt_active`, classify lines as:

- A flush-left line containing exactly `eot` → TXT_END;
  set `txt_active = False`.
- Any other line → TXT_LINE. The line's full text (after the
  4-space indent, or empty for blank lines, or error if
  malformed) goes in `line.tail`.

Reject inside `txt_active`:
- A line with content but fewer than 4 leading spaces (and not
  just `eot`). Error: "continuation line must begin with 4 spaces".

`str` and `cstr` lex as regular SMOLA keyword lines (their bodies
are on a single line; no state machine needed). The translator
parses the quoted content with its own escape-handling logic.

### A.6 Translator changes

Add handlers:

- `_handle_str_decl(line)` — parse `"..."`, validate escapes,
  emit `.balign 1 / .ascii / .size`.
- `_handle_cstr_decl(line)` — same, plus `.byte 0` and +1 to size.
- `_handle_txt_block(line)` — opens a `txt` block. Records the
  current_data_label, sets a state flag.
- `_handle_txt_line(line)` — accumulates content for the current
  `txt` block.
- `_handle_txt_end(line)` — closes the `txt` block, emits the
  full sequence of `.ascii` directives, updates byte count.

State on `Translator`:

```python
self.txt_in_progress: Optional[List[str]] = None
# List of content strings (one per source line) accumulated inside
# the active txt block. None when no block is in progress.
```

Routing in `_handle_var_decl` (data section path): if the keyword
is `str` or `cstr`, route to the new string handler. If `txt`,
open a block.

Error paths to implement:
- `str` / `cstr` / `txt` used in a code section: routes to the
  data handler which errors with the data-only message.
- Unterminated `txt` block (EOF reached with `txt_in_progress`
  still set): error at EOF.
- Invalid escape in `str`/`cstr`: error with the specific
  offending sequence quoted.
- Missing closing `"` in `str`/`cstr`: error.
- Content after the closing `"` (other than whitespace or comment):
  error.
- `txt` continuation line with < 4 leading spaces: lexer-level
  error with hint.
- `str`/`cstr`/`txt` without preceding label: same "label required"
  error as other data-section keywords.

### A.7 Examples

Add `examples/strings.smola`:

```asm
# Demonstrates the three string keywords.
#
# str   — one-line, no terminator
# cstr  — one-line, NUL-terminated (for C calls)
# txt   — multi-line heredoc, no terminator

.section .rodata

# Application identity strings.
app_name:
    cstr "ε₀ (Epsilon Null)"

app_version:
    cstr "v0.0.1"

# A short note with no NUL — known length consumers use this.
build_note:
    str "compiled with smola"

# Multi-line prose for an about screen.
about_text:
txt ε₀ — a demoscene project exploring tiny RISC-V demos.
    Crafted with care; written in assembly; built to last 64k.
    
    For the people who build small things that mean a lot.
eot

.section .text

# render_about — placeholder kernel that would consume about_text.
# Real implementation would call into Cairo/Pango for rendering.
func render_about
    ptr text_ptr
    la text_ptr, about_text
    # ... (rendering elided)
end
```

Update `examples/render_square.smola` to use a `cstr` for a
sample status message if natural; otherwise leave it.

### A.8 Tests

Add `tests/test_strings.py` with these test cases. Each is a
small `translate()` call followed by assertions on the output
or on the raised exception.

**Happy path:**
- `str "Hello"` → `.ascii "Hello"`, `.size foo, 5`.
- `cstr "Hello"` → `.ascii "Hello"` + `.byte 0`, `.size foo, 6`.
- `str` with each escape (`\n`, `\t`, `\\`, `\"`, `\0`, `\xff`).
- `str ""` (empty string) → emits `.size foo, 0`, no `.ascii`.
- `str` with UTF-8 multibyte content; verify byte count is correct
  (not character count).
- `cstr ""` (empty string) → emits `.byte 0`, `.size foo, 1`.
- `txt` block with three content lines; verify byte count includes
  newlines.
- `txt` block with a blank line in the middle; verify the blank
  emits a `\n`.
- `txt` block with the `txt eot / eot` pattern; verify `eot` ends
  up in the data.
- `str` with trailing whitespace inside the quotes; verify the
  whitespace is preserved.
- `str` with trailing whitespace after the closing `"`; verify
  no error.
- `str` with trailing comment after the closing `"`; verify
  comment is captured.

**Error paths:**
- `str` without quotes: error.
- `str "unterminated`: error.
- `str "extra" extra`: error (content after closing quote).
- `str "bad \z escape"`: error naming `\z`.
- `txt` line not starting with 4 spaces: error.
- `txt` reaching EOF without `eot`: error.
- `str` in code section: error (data-only).
- `cstr` in code section: error.
- `txt` in code section: error.
- `str` without preceding label: error.

**Alignment:**
- `str` block followed by `i32` block: verify SMOLA emits
  `.balign 1` for str and `.balign 4` for i32; GAS handles the
  padding.

**Spec property:**
- Multiple `str` declarations under separate labels: each gets
  its own `.size` directive.

Aim for at least 20 tests in this file; this is the most complex
syntactic addition to date.

---

## B. f16 / bf16 stubs

### B.1 Lexer

Add to `SMOLA_KEYWORDS`:

```python
"f16", "f16.s", "f16.a",
"bf16", "bf16.s", "bf16.a",
```

(No `.t` variant because `.t` is the default — bare keyword.)

### B.2 Translator

Add to `_handle_code_var_decl` and `_handle_data_decl`: if
keyword's base is `f16` or `bf16`, raise a `ParseError` with a
clear hint:

> `f16` and `bf16` are reserved keywords; not yet implemented.
> Half-precision FP requires Zvfh (not in RVA23 baseline) or
> vendor extensions (SpacemiT K1/K3, others). The hook will be
> wired when a target chip is selected and verified.

Error type: `ParseError` (same as other data-only errors).

### B.3 Tests

Two tests, in `tests/test_reserved.py` (new file):

- `f16 gain 0.5` in code section: error with "not yet implemented".
- `bf16 0.5 1.0` in `.rodata`: error with "not yet implemented".

### B.4 Spec

In §2.11 ("What v0.3 does NOT have"), add a line:

> - `f16` and `bf16` keywords are *reserved* but not yet
>   implemented. The implementation waits on a target chip whose
>   half-precision support (Zvfh, Zvfhmin, or vendor) is verified
>   end-to-end.

---

## C. Sub-byte and exotic FP reservations

### C.1 Lexer

Add to `SMOLA_KEYWORDS` (these are reserved tokens; they parse as
SMOLA keywords but the translator rejects them):

```python
"fp8", "fp8.s", "fp8.a",
"fp4", "fp4.s", "fp4.a",
"i4", "i4.s", "i4.a",
"u4", "u4.s", "u4.a",
"i2", "i2.s", "i2.a",
"u2", "u2.s", "u2.a",
"i1", "i1.s", "i1.a",
"u1", "u1.s", "u1.a",
"b1p58", "b1p58.s", "b1p58.a",   # BitNet 1.58-bit ternary
```

Also reserve `packed` as a single token that, if seen, errors with
a hint. The dotted form `packed.<type>` requires more parser work
to handle and isn't reserved for this turn beyond the bare
`packed` token.

### C.2 Translator

Reject all of these in both code and data contexts with:

> `<keyword>` is a reserved keyword; sub-byte and exotic FP
> formats are not yet implemented. These will be added when a
> target chip's bit layout and instruction encoding are
> verified. See the decision log entry from <date> for context.

### C.3 Tests

In `tests/test_reserved.py`:

- One test per reserved keyword, asserting the error fires.
  A simple loop over the list is fine; this is more about locking
  in the namespace than exercising each path independently.

### C.4 Spec

Append to §2.11:

> - Sub-byte integer types (`i4`/`u4`/`i2`/`u2`/`i1`/`u1`) and
>   exotic FP formats (`fp8`/`fp4`/`b1p58`) are *reserved*. Bit
>   layout and packing conventions are hardware-dependent; the
>   keywords cannot be implemented without a verified target. See
>   the decision log entry from <date>.

---

## D. README updates

In `tools/smola/README.md`, add to the keyword table:

| `str`, `cstr`, `txt` | String data in data sections             |
| `f16`, `bf16`        | Half-precision floats (reserved)         |

In the "Data sections" example, add a string demonstration:

```asm
.section .rodata

greeting:
    cstr "Hello, world!"

about:
txt ε₀ is a demoscene project.
    Tiny tools doing improbable things.
eot
```

---

## E. Spec amendment — full text to add

Insert a new §2.13 ("String data") in `docs/smola_design.md`,
after the existing §2.12 ("Data-section declarations").

The text below is what goes into the spec verbatim (or close to
it; you may adjust wording for flow):

```markdown
### 2.13 String data

The three string keywords introduce string-typed data blocks.
All three are valid only in data sections.

| Keyword | Surface | NUL terminator | Use case                       |
|---------|---------|----------------|--------------------------------|
| `str`   | quoted  | no             | length-aware consumers          |
| `cstr`  | quoted  | yes (`\0`)     | calls to C library functions    |
| `txt`   | heredoc | no             | multi-line prose, large blobs   |

#### 2.13.1 `str` and `cstr`

Single-line quoted form:

    <label>:
        str "..."
        cstr "..."

Rules:
- One space between keyword and opening `"`.
- Content runs from the first `"` to the matching closing `"`.
- Escapes: `\"`, `\\`, `\n`, `\t`, `\0`, `\xHH`. Unknown
  backslash sequences are format errors.
- After the closing `"`: nothing, whitespace, or a trailing
  comment. Anything else is a format error.
- Content is treated as UTF-8 bytes; multibyte sequences pass
  through verbatim. Byte count for `.size` reflects encoded bytes.

Emission for `str`:
- `.balign 1`
- `.ascii "<content>"` (escapes re-emitted in GAS form)
- `.size <label>, <bytes>`

Emission for `cstr`: same as `str` plus `.byte 0` and +1 to size.

#### 2.13.2 `txt`

Multi-line heredoc form:

    <label>:
    txt <first line>
        <continuation>
        <continuation>
    eot

Rules:
- `txt` followed by one space, then the first content line.
- Each continuation line begins with exactly 4 spaces; content
  starts at column 5.
- A line consisting of exactly `eot` (flush-left, no trailing
  content beyond the newline) terminates the block.
- Blank lines (zero characters) inside the block emit `\n` as
  content.
- No escape sequences. Content is literal UTF-8 bytes.
- The newline preceding `eot` is part of the content; the `eot`
  line itself is not.

Emission:
- `.balign 1`
- One `.ascii "..."` directive per source content line, each
  with a trailing `\n` in the GAS string.
- `.size <label>, <total bytes including newlines>`

#### 2.13.3 Alignment

All three string keywords use `.balign 1` by default. For SIMD
or cache-line alignment, place a raw GAS `.balign <N>` directive
before the label. SMOLA passes GAS directives through unchanged.

A future SMOLA-native `align <N>` keyword is reserved (errors in
v0.3.x with "reserved for future use").

#### 2.13.4 Code sections

All three string keywords are forbidden in code sections. They
emit a "string declarations are only valid in data sections"
error.
```

In §2.11 ("What v0.3 does NOT have"), append the f16/bf16 and
sub-byte reservation notes from sections B.4 and C.4 above.

In §2.3 ("SMOLA keywords"), update the table to include `str`,
`cstr`, `txt` (with brief one-line descriptions matching the
table above). Reserved keywords (f16/bf16, sub-byte family) are
*not* added to the visible keyword table but *are* listed as
reserved in §2.11.

In §2.5 ("Anonymous declarations reserved"), no changes needed.

---

## F. Decision log append

Add this entry verbatim to `docs/eno_decision_log.md`, preserving
all earlier entries above it:

```markdown
## 2026-05-21 (evening, via Claude Code) — SMOLA string data + f16 stubs

### Context

After the morning's v0.3 refinements (width-typed declarations
and data-section semantics), SMOLA had no story for textual
data. ENO will extensively call into C libraries (Cairo, Pango,
GL, audio APIs) that consume NUL-terminated strings, and
demos benefit from compact text blocks (titles, prose, error
messages, font glyph maps). The two ideation chats settled on
three string keywords and a reservation policy for
sub-byte / exotic FP formats.

### Decisions

**Three string keywords:**
- `str` — quoted single-line, no terminator
- `cstr` — quoted single-line, NUL-terminated (for C library calls)
- `txt` — heredoc multi-line (`txt` ... `eot`), no terminator

**Escape sequences** in `str`/`cstr`: standard set
(`\"`, `\\`, `\n`, `\t`, `\0`, `\xHH`). Unknown sequences error.

**`txt` body rules:** exactly one space after `txt`, then content;
continuation lines indented exactly 4 spaces; blank lines emit
`\n`; flush-left `eot` terminates; no escapes (literal UTF-8).

**Alignment:** all three default to `.balign 1`. SIMD-aligned
strings via a raw GAS `.balign <N>` before the label. SMOLA-native
`align <N>` keyword reserved for future use.

**Forbidden in code sections.** Strings live in data sections.

**`f16` and `bf16` reserved.** Half-precision FP keywords accepted
by the lexer but rejected by the translator with "not yet
implemented." Awaits target chip selection (SpacemiT K1/K3 or
similar) and Zvfh/Zvfhmin verification.

**Sub-byte and exotic FP reserved:** `fp8`, `fp4`, `i4`, `u4`,
`i2`, `u2`, `i1`, `u1`, `b1p58` (BitNet 1.58-bit ternary). Bit
layout is hardware-specific; implementation deferred until target
hardware verified. The bare token `packed` is also reserved.

### Implementation

Implemented in this Claude Code session. Tests grew from 114 to
~140 (exact count after implementation). Examples grew from 5 to
6 (`strings.smola` added).

### Open

- **Vim/neovim syntax highlighter** for `.smola` — open question
  for a separate turn. Should highlight SMOLA keywords, RV
  mnemonics (from the existing closed table), the `txt`/`eot`
  block region with its column boundary visible, and the
  reserved-keyword family in a warning color.

- **Anonymous declarations** in both code (temporaries) and data
  (sectionless data): still reserved. Will be reconsidered when
  a concrete recurring pattern in ENO code wants them.

- **`align <N>` SMOLA-native keyword**: reserved; revisit if
  hand-writing `.balign` becomes painful in real ENO code.
```

---

## G. Bump version

In `src/smola/__init__.py`:

```python
__version__ = "0.3.1"
```

Reflects the addition of string data and reserved keywords on top
of the morning's v0.3.0.

---

## H. Session summary

At the end of the session, produce
`docs/_session_<YYYY-MM-DD>_claude_code_summary.md` with:

- One-paragraph summary of what changed
- Files modified (with brief note on each)
- New files added (with brief note on each)
- Test count before / after
- Examples added
- Anything that didn't get done and why
- Pending action items for the next session
- Anything you noticed during implementation that should be
  considered for a future turn

---

## I. Validation checklist

Before declaring the session done, verify:

- [ ] `make test` passes (114 baseline + new tests, all green)
- [ ] `make examples` translates all examples cleanly
- [ ] `make check-assembles` works for all examples (if cross
      toolchain available; document if not)
- [ ] All `str`/`cstr`/`txt` happy paths work
- [ ] All error paths produce clear, hinted error messages
- [ ] UTF-8 content survives round-trip
- [ ] `.size` directives are byte-accurate (not character-accurate)
- [ ] `f16`/`bf16` reserved-error fires with the documented hint
- [ ] All sub-byte/exotic reserved keywords fire reserved-errors
- [ ] Decision log appended (don't replace existing entries)
- [ ] Version bumped to 0.3.1
- [ ] README updated
- [ ] Spec amended (§2.11, §2.13 added; §2.3 keyword table updated)
- [ ] Session summary produced

---

## J. Style and code-comment expectations

This codebase follows the ENO project's commenting rules:
- Block comments before non-trivial functions explaining intent.
- End-of-line comments on subtle lines.
- Python files aim for substantial documentation density.
- Assembly (none generated this turn directly, but provenance
  comments in output `.s` should remain clear) follows the
  half-comments rule.

For the SMOLA Python source: each new function gets a
docstring explaining what it does and why; tricky logic gets
inline comments; the lexer's state-machine logic for `txt`
blocks especially should be commented because state machines
get unreadable without it.

---

## K. Things to avoid

- **Do not** add to the RISC-V mnemonic table. Not part of this
  turn.
- **Do not** change the existing v0.3 syntax surface in ways that
  would invalidate existing `.smola` source. This is purely
  additive.
- **Do not** implement vim syntax highlighting now. Reserved for
  a separate turn (mentioned in decision log open questions).
- **Do not** implement the `align <N>` SMOLA keyword. Reserved.
- **Do not** implement sub-byte or exotic FP semantics. Reserved.
- **Do not** implement `f16`/`bf16` arithmetic or codegen. Reserved
  pending target chip.
- **Do not** add anonymous string declarations (string without a
  preceding label). Same reservation policy as other anonymous
  data.

---

## L. If you get stuck

If you encounter design ambiguity not covered by this prompt:

1. Default to the most conservative interpretation.
2. Add the ambiguity to the session summary's open-questions
   section.
3. Don't invent new design; better to leave something unfinished
   than to add a feature that diverges from the spec.

If you encounter a real bug in the existing v0.3 code (not just
something you'd do differently): fix it and document in the
session summary. Bug fixes are always welcome; redesign isn't.

---

End of prompt. Acknowledge by saying you've read it and naming
the three string keywords, then proceed.
