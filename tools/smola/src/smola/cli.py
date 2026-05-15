"""SMOLA command-line interface.

Usage: smola input.smola [-o output.s] [options]
"""

import argparse
import sys
from pathlib import Path

from .errors import SmolaError
from .translator import Translator


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="smola",
        description="Preprocess SMOLA source into GAS-compatible RISC-V assembly.",
    )
    ap.add_argument("input", help="Input .smola file (use '-' for stdin)")
    ap.add_argument("-o", "--output",
                    help="Output .s file. Default: replace .smola extension with .s.")
    ap.add_argument("--stdout", action="store_true",
                    help="Write to stdout instead of a file.")
    ap.add_argument("--no-provenance", action="store_true",
                    help="Suppress # smola: ... comments.")
    ap.add_argument("--check", action="store_true",
                    help="Parse only; do not write output.")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    if args.input == "-":
        source = sys.stdin.read()
        filename = "<stdin>"
    else:
        src_path = Path(args.input)
        if not src_path.exists():
            print(f"smola: error: input file not found: {args.input}", file=sys.stderr)
            return 1
        source = src_path.read_text(encoding="utf-8")
        filename = str(src_path)

    translator = Translator(
        filename=filename,
        emit_provenance=not args.no_provenance,
    )

    try:
        output = translator.translate(source)
    except SmolaError as e:
        print(str(e), file=sys.stderr)
        return 1
    except Exception as e:
        print(f"smola: internal error: {type(e).__name__}: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 2

    if args.check:
        if args.verbose:
            print("smola: check passed", file=sys.stderr)
        return 0

    if args.stdout or args.output == "-":
        sys.stdout.write(output)
    else:
        if args.output is not None:
            out_path = Path(args.output)
        elif args.input == "-":
            print("smola: error: --output required when reading from stdin",
                  file=sys.stderr)
            return 1
        else:
            out_path = Path(args.input).with_suffix(".s")
        out_path.write_text(output, encoding="utf-8")
        if args.verbose:
            print(f"smola: wrote {out_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
