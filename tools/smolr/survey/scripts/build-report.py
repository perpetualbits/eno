#!/usr/bin/env python3
"""survey/scripts/build-report.py

Read the per-artifact inspection files produced by inspect-all.sh and
synthesise docs/riscv-relocation-survey.md.

The report is the Phase 1 deliverable. It must answer:

  1. Which R_RISCV_* relocations does each test produce, under each ISA tier
     and each relax/PLT combination?
  2. Which combinations are stable (same relocation set) and which diverge?
  3. Which combinations link cleanly and which don't?
  4. Are there any surprises that SMOLR will need to handle before Phase 3?

Driven by env vars (same as the other scripts):
  TESTS, TIERS, FLAGCOMBOS, BUILD
"""

import os
import re
import sys
from pathlib import Path
from collections import defaultdict, Counter


def env_list(name):
    v = os.environ.get(name, "")
    if not v:
        sys.exit(f"build-report.py: ${name} not set")
    return v.split()


TESTS      = env_list("TESTS")
TIERS      = env_list("TIERS")
FLAGCOMBOS = env_list("FLAGCOMBOS")
BUILD      = Path(os.environ.get("BUILD", "build/survey"))

RELOC_LINE = re.compile(
    r"^\s*[0-9a-f]+\s+[0-9a-f]+\s+(R_RISCV_\S+)", re.IGNORECASE
)


def parse_relocs(path):
    """Return a Counter of R_RISCV_* relocation names found in a readelf -rW file."""
    c = Counter()
    if not path.exists():
        return c
    for line in path.read_text(errors="replace").splitlines():
        m = RELOC_LINE.match(line)
        if m:
            c[m.group(1)] += 1
    return c


def parse_dynamic(path):
    """Return DT_NEEDED entries from a readelf -d output, in order."""
    needed = []
    if not path.exists():
        return needed
    for line in path.read_text(errors="replace").splitlines():
        if "(NEEDED)" in line:
            # Format: " 0x... (NEEDED)   Shared library: [libc.so.6]"
            m = re.search(r"\[(.+?)\]", line)
            if m:
                needed.append(m.group(1))
    return needed


def linked(stem):
    return (stem.parent / f"{stem.name}.elf").exists()


def header():
    return f"""# RISC-V Relocation Survey (SMOLR Phase 1)

Auto-generated from the survey corpus under `tools/smolr/build/survey/`.
Regenerate with `make report` after rebuilding the corpus.

This document answers:

1. Which `R_RISCV_*` relocations does each test produce, under each ISA
   tier and each relax / PLT combination?
2. Which combinations link cleanly, and which don't?
3. What is the minimal relocation set SMOLR must handle for Phase 3?

## Methodology

For each test source in `survey/tests/`, we build the cartesian product of:

- **ISA tier**: {", ".join(f"`{t}`" for t in TIERS)}
- **Flag combo**: {", ".join(f"`{c}`" for c in FLAGCOMBOS)}

We record `readelf -rW` on the resulting `.o` and `readelf -d` on the
linked `.elf` when linking succeeds.

The ISA tier `rva23u64` may be transparently replaced by an expanded
ISA string (see `build-survey.sh`) on toolchains that don't accept the
profile name directly. The tier label in this report still says `rva23u64`
in that case — check `build/toolchain-probe.txt` to confirm which strings
the local toolchain actually accepted.

"""


def emit_test_section(test):
    out = [f"## Test: `{test}`\n"]

    src = Path(f"survey/tests/{test}.c")
    if src.exists():
        out.append("Source:\n\n```c\n" + src.read_text() + "```\n")
    else:
        out.append(f"(source `{src}` not found)\n")

    # Per-test relocation matrix.
    out.append("### Relocation matrix\n")
    out.append("Each cell shows `RELOC_NAME × count`. Empty cells mean no "
               "object was produced for that combination.\n")

    # Build a wide table: rows = (tier, combo), columns = relocation types.
    rows = {}
    all_relocs = set()
    link_status = {}
    needed_libs = {}
    missing = []
    for tier in TIERS:
        for combo in FLAGCOMBOS:
            stem = BUILD / f"{test}-{tier}-{combo}"
            reloc_file = stem.parent / f"{stem.name}.reloc"
            relocs = parse_relocs(reloc_file)
            if not reloc_file.exists():
                missing.append((tier, combo))
                continue
            rows[(tier, combo)] = relocs
            all_relocs.update(relocs.keys())
            link_status[(tier, combo)] = linked(stem)
            dyn_file = stem.parent / f"{stem.name}.dynamic"
            needed_libs[(tier, combo)] = parse_dynamic(dyn_file)

    if not rows:
        out.append("\n(no artifacts found for this test — corpus not built?)\n")
        return "\n".join(out)

    sorted_relocs = sorted(all_relocs)
    headers = ["tier / flags", "linked?", "DT_NEEDED"] + sorted_relocs
    out.append("| " + " | ".join(headers) + " |")
    out.append("|" + "|".join("---" for _ in headers) + "|")
    for tier in TIERS:
        for combo in FLAGCOMBOS:
            key = (tier, combo)
            if key not in rows:
                continue
            label = f"`{tier}` / `{combo}`"
            linked_cell = "yes" if link_status[key] else "no"
            needed = needed_libs.get(key, [])
            needed_cell = ", ".join(needed) if needed else "—"
            cells = [label, linked_cell, needed_cell]
            for r in sorted_relocs:
                n = rows[key].get(r, 0)
                cells.append(str(n) if n else "")
            out.append("| " + " | ".join(cells) + " |")

    if missing:
        out.append("\nMissing artifacts:")
        for t, c in missing:
            out.append(f"- `{t}` / `{c}`")

    # Stability summary across flag combos within a tier.
    out.append("\n### Stability across flag combos\n")
    for tier in TIERS:
        sets_in_tier = []
        for combo in FLAGCOMBOS:
            if (tier, combo) in rows:
                sets_in_tier.append((combo, frozenset(rows[(tier, combo)].keys())))
        if not sets_in_tier:
            continue
        unique_sets = set(s for _, s in sets_in_tier)
        if len(unique_sets) == 1:
            sample = next(iter(unique_sets))
            out.append(f"- `{tier}`: identical reloc *set* across all combos "
                       f"({len(sample)} types)")
        else:
            out.append(f"- `{tier}`: relocation set varies across combos:")
            for combo, s in sets_in_tier:
                out.append(f"  - `{combo}`: {sorted(s)}")

    out.append("")
    return "\n".join(out)


def emit_global_summary():
    """Collect the union of all relocations seen, grouped by which test triggered them."""
    out = ["## Global summary\n"]
    by_reloc = defaultdict(list)
    for test in TESTS:
        for tier in TIERS:
            for combo in FLAGCOMBOS:
                stem = BUILD / f"{test}-{tier}-{combo}"
                reloc_file = stem.parent / f"{stem.name}.reloc"
                for r in parse_relocs(reloc_file):
                    by_reloc[r].append((test, tier, combo))

    if not by_reloc:
        out.append("(no relocations observed — corpus not built?)\n")
        return "\n".join(out)

    out.append("Every relocation observed in the corpus, with one example "
               "triple per type:\n")
    out.append("| Relocation | First triggered by | Total artifacts |")
    out.append("|---|---|---|")
    for r in sorted(by_reloc):
        first = by_reloc[r][0]
        out.append(
            f"| `{r}` | `{first[0]}` / `{first[1]}` / `{first[2]}` | "
            f"{len(by_reloc[r])} |"
        )

    out.append("\n### Recommended minimal supported set for Phase 3\n")
    out.append("Phase 3 needs only what test `01-call-puts` produces with the "
               "default tier and flag combo. Everything beyond that is "
               "Phase 4+ territory.\n")
    phase3_relocs = set()
    for tier in TIERS:
        for combo in FLAGCOMBOS:
            stem = BUILD / f"01-call-puts-{tier}-{combo}"
            phase3_relocs.update(parse_relocs(stem.parent / f"{stem.name}.reloc").keys())
    if phase3_relocs:
        for r in sorted(phase3_relocs):
            out.append(f"- `{r}`")
    else:
        out.append("(no data — 01-call-puts not built)")

    out.append("")
    return "\n".join(out)


def main():
    print(header())
    print(emit_global_summary())
    for test in TESTS:
        print(emit_test_section(test))
        print()


if __name__ == "__main__":
    main()
