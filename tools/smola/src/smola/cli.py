"""SMOLA command-line interface.

The thin layer between the operating system and the Translator. Parses
arguments, reads input, runs the translator, writes output, and turns
exceptions into exit codes.

Exit code conventions:
  0 — success
  1 — user error (a SmolaError raised by the translator; the user
       wrote something the tool doesn't accept, or supplied a bad
       command-line argument)
  2 — internal error (any other exception escaped the translator;
       this is a SMOLA bug worth reporting)

The 1-vs-2 split matters because Makefiles and CI scripts can
distinguish "user needs to fix their .smola" from "the tool itself
broke." If everything was exit code 1, automation would treat a
SMOLA crash as just another user error.
"""

import argparse
import sys
from pathlib import Path

from .errors import SmolaError
from .translator import Translator


def main(argv=None) -> int:
    """CLI entry point. Returns the desired exit code.

    `argv` is normally None (meaning use sys.argv); tests pass an
    explicit list to invoke the CLI without subprocess overhead.
    """
    ap = argparse.ArgumentParser(
        prog="smola",
        description=("Preprocess SMOLA source into "
                     "GAS-compatible RISC-V assembly."),
    )
    # Positional input. A literal "-" means read from stdin, the
    # standard Unix convention. Useful when SMOLA is invoked from a
    # pipeline or another tool.
    ap.add_argument("input",
                    help="Input .smola file (use '-' for stdin)")
    # Output path. If omitted, derive from the input by swapping
    # the .smola extension for .s. This matches typical compiler
    # behavior and means `smola foo.smola` Just Works.
    ap.add_argument("-o", "--output",
                    help=("Output .s file. Default: replace .smola "
                          "with .s."))
    # Convenience flag to emit to stdout. Equivalent to `-o -` but
    # easier to remember.
    ap.add_argument("--stdout", action="store_true",
                    help="Write to stdout instead of a file.")
    # Suppresses the `# smola: ...` provenance comments and the auto
    # bindings table. Useful when generating .s for hand-editing or
    # when measuring exact output sizes.
    ap.add_argument("--no-provenance", action="store_true",
                    help=("Suppress # smola: ... comments and the "
                          "auto bindings table."))
    # Parse-only mode. The translator still runs (so syntax errors
    # surface), but no output is written. Used by IDE integrations
    # and pre-commit hooks.
    ap.add_argument("--check", action="store_true",
                    help="Parse only; do not write output.")
    # Verbose mode currently only enables a few status messages on
    # stderr. Kept minimal because SMOLA's job is supposed to be
    # quick and quiet on the success path.
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    # Read the input. stdin path is handled separately so we can give
    # the source a sensible filename for error messages.
    if args.input == "-":
        source = sys.stdin.read()
        # All SourceLoc entries from this run will say "<stdin>:<line>"
        # in error messages. Matches the convention used by other
        # Unix tools.
        filename = "<stdin>"
    else:
        src_path = Path(args.input)
        if not src_path.exists():
            # File-not-found is a user error, so exit 1.
            print(f"smola: error: input file not found: {args.input}",
                  file=sys.stderr)
            return 1
        # UTF-8 is the only encoding we accept. SMOLA source is text;
        # if the user has a file in some other encoding, they need to
        # convert it first. This is intentional — supporting "all
        # encodings" introduces bugs we don't want.
        source = src_path.read_text(encoding="utf-8")
        filename = str(src_path)

    # Build the translator with the chosen settings. The translator
    # is self-contained; we create one per run and discard it.
    translator = Translator(filename=filename,
                            emit_provenance=not args.no_provenance)

    # Run the translation. Two exception classes get different
    # treatment: SmolaError is the user-facing "you wrote something
    # we don't accept" case (exit 1). Anything else is a SMOLA bug
    # (exit 2). The verbose flag triggers a Python traceback for the
    # bug case so reports can include the stack.
    try:
        output = translator.translate(source)
    except SmolaError as e:
        # SmolaError.__str__ already formats the message with the
        # source location and hint; we just need to write it.
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        # Any other exception is a bug. Print enough to start
        # diagnosing, with the optional full traceback in verbose
        # mode.
        print(f"smola: internal error: {type(e).__name__}: {e}",
              file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 2

    # --check mode: stop here, success implied. Useful for "does this
    # file parse?" questions without filling the disk with .s files.
    if args.check:
        if args.verbose:
            print("smola: check passed", file=sys.stderr)
        return 0

    # Write the output. Three output paths:
    #   1. --stdout or -o -  : write to stdout
    #   2. -o <path>         : write to that path
    #   3. (default)         : derive path from input (.smola -> .s)
    if args.stdout or args.output == "-":
        # Direct stdout write — useful in pipelines, and matches
        # `cat foo.smola | smola - --stdout`.
        sys.stdout.write(output)
    else:
        if args.output is not None:
            out_path = Path(args.output)
        elif args.input == "-":
            # Reading stdin without an explicit -o gives us nowhere
            # to write. Caller error.
            print("smola: error: --output required when reading from stdin",
                  file=sys.stderr)
            return 1
        else:
            # Default: replace the extension. `Path.with_suffix` handles
            # the .smola -> .s rename atomically.
            out_path = Path(args.input).with_suffix(".s")
        # UTF-8 write to match the read. GAS itself doesn't care about
        # encoding for ASCII content, but if a comment ever contains
        # non-ASCII text (Roland's daughter's name, mathematical
        # symbols, etc.) this preserves it correctly.
        out_path.write_text(output, encoding="utf-8")
        if args.verbose:
            print(f"smola: wrote {out_path}", file=sys.stderr)
    return 0


# Standard "this module can be run directly" guard. When the bin/smola
# launcher imports us, this branch doesn't fire — main() is called
# explicitly. When someone runs `python -m smola.cli`, it does.
if __name__ == "__main__":
    sys.exit(main())
