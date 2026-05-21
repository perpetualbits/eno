# lib/gfx

Graphics helpers, GLSL plumbing, and wavelet-domain visual effects.

## Planned contents

- **GL context & window setup** (SDL2-based for the demo, possibly with a
  dedicated minimal Wayland/X11 path for size-coded productions).
- **Shader loading + minification glue** (works with `tools/glint`).
- **SDF primitives** for cave/monument geometry.
- **Wavelet-domain effects**: sand, smoke, terrain — same WaveletSquare
  data structures, repurposed for 2D fields.
- **Post-fx**: bloom, tone-mapping, film grain.
- **Cairo/Pango bridge**: provides a CPU-side ARGB surface for text that
  the demo uploads as a texture.

Depends on `lib/crest` (for 2D/3D wavelet bits) and `lib/core`.

Currently empty placeholder.
