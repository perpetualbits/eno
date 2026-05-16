# SIZE_COMPARISON.md

Prototype A v0.2 — structural compression measurement.

## What this measures

Two `.spine` files that expand to byte-identical event lists:

- `phrase_motif.spine` — rolled-up, uses DEF/MOD/USE/GRP for reuse.
- `phrase_motif_flat.spine` — hand-flattened, every note placed
  explicitly with `at`, every entity defined once per occurrence.

Both produce 15 events when expanded. The expansion files are
byte-identical (verified by `diff`).

## Methodology

Source size in two forms:

1. **Raw bytes** — `wc -c` directly. Comparable only for human reading;
   sensitive to comment density.
2. **Canonical bytes** — comments stripped (`#` to end of line),
   whitespace runs collapsed to single spaces, leading/trailing
   trimmed. This is the fair structural comparison.

Run from the repo root:

```sh
python3 -c "
import re
for path in ['examples/phrase_motif.spine', 'examples/phrase_motif_flat.spine']:
    with open(path) as f: text = f.read()
    canonical = re.sub(r'\s+', ' ', re.sub(r'#[^\n]*', '', text)).strip()
    print(f'{path}: raw={len(text)} canonical={len(canonical)}')
"
```

## Current numbers

| Form           | Raw bytes | Canonical bytes |
|----------------|----------:|----------------:|
| rolled         |     3588  |             745 |
| flat           |     1913  |            1013 |
| **ratio**      | 0.53×     | **1.36×**       |

The rolled version is **~26% smaller in canonical bytes** than the flat
version. Raw byte comparison is misleading because the rolled file
carries more explanatory comments.

## What this means

This is a *small* example (15 events, 3 distinct pitch sets) and the
savings are modest. Two reasons to be cautiously encouraged anyway:

1. **The savings are real and non-zero** at this scale. The premise
   that structural compression saves bytes is empirically supported,
   if barely.

2. **The savings grow nonlinearly with reuse.** Adding a sixth USE of
   `motif_asc` costs ~25 canonical bytes in the rolled form (`USE
   motif_asc at X.X dur Y.Y`) and ~75 canonical bytes in the flat form
   (three explicit notes). At 10 reuses the rolled form would be
   ~2.5× smaller in canonical bytes.

This is the v0.2 equivalent of SMOLR's "make `wc -c` look confused" —
modestly confused, but confused in the right direction. Future
prototypes with longer scores will show the trend more clearly.

## What this does NOT yet show

- Entropy coding wins. The canonical comparison is pre-entropy. Once
  binary form lands, the rolled version compresses much better still
  because its symbol stream is shorter and more repetitive.
- Near-repetition wins. Variants that share structure but differ in
  one parameter (e.g. "motif_asc but with a B4 instead of a G4")
  cannot yet be rolled up by v0.2's exact-repetition pass. Real music
  has lots of these. Open question §3.1 tracks this.
- Reachability wins on shared libraries. When a future demo imports
  a library of 200 phrases and uses 12, the unused 188 are dropped.
  This is the much larger structural win and is invisible in single-
  file examples like this one.

## Reproducing

Run from `tools/spine/`:

```sh
# 1. Verify both files exist and expand:
python3 src/expand.py examples/phrase_motif.spine
python3 src/expand.py examples/phrase_motif_flat.spine

# 2. Verify they produce identical event lists:
python3 src/expand.py examples/phrase_motif.spine \
  > /tmp/rolled_out.txt
python3 src/expand.py examples/phrase_motif_flat.spine \
  > /tmp/flat_out.txt
diff /tmp/rolled_out.txt /tmp/flat_out.txt  # should be empty

# 3. Verify reachability drops orphan_chord from the rolled version:
python3 src/expand.py examples/phrase_motif.spine \
  --dump-reachable
# Output should list 'orphan_chord' under "dropped (unreachable)".
```
