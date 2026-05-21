# tools/carve — CARVE

The offline authoring tool for instrument trajectory templates and 3D scene
definitions. ML fitting, node-graph UI, IR baking for polar wavelet reverb.

See `docs/carve_design.md` for the full design.

## Scope

CARVE produces SPINE-dialect entities (audio trajectory templates, 3D scenes,
impulse responses) that NERVE consumes at runtime. It is not a DAW, not a
runtime, and not a renderer.

## Planned features

- **Node-graph editor**: author `audio.trajectory_template` entities by
  connecting segment, envelope, and modulator nodes.
- **ML fitting** (Tier 2, Python/GPU): fit recorded instrument samples to
  wavelet bases. Results feed back into the node graph.
- **IR baker**: compute polar wavelet reverb impulse responses from 3D scenes.
- **In-CARVE playback**: audition trajectory templates via a small ALSA path
  while NERVE is not yet available.
- **SPINE text emission**: export the authored entities as SPINE source.

## Implementation tiers

- Tier 1 (portable C): node-graph editor, IR baker, project I/O, SPINE emission.
  Must be small enough to eventually run on RISC-V.
- Tier 2 (Python): ML fitting on GPU dev servers. File-based JSON handoff
  with Tier 1.

Currently empty placeholder.
