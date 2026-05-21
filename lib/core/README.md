# lib/core

Foundational utilities shared across all ENO libraries and productions.

## Planned contents

- **Arena allocator**: single-block bump allocator with save/restore.
  Currently lives in `lib/crest` and will move here once a second
  library needs it.
- **Fixed containers**: small-vector, ring buffer, fixed hash map — all
  with caller-provided storage, no malloc.
- **Math primitives**: fast sin/cos tables, vector ops, fixed-point helpers
  if any code path still needs them.
- **Logging/assert**: dev-build verbose logging that compiles out in
  release builds.

Nothing here yet — currently empty placeholder.
