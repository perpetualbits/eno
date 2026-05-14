# Desert Monument

ENO production #1. Target: 64k Linux/RISC-V intro.

## Concept

Two survivors pilgrimage through a desert storm to reach a projected video
monument that commemorates a war 500 years prior. Coefficient-space
synthesis treats audio, reverb, visual fields, terrain, smoke, and sand as
related coefficient fields manipulated by a small set of verbs: stamp,
shift, scale, rotate, warp, diffuse, filter, render.

## Status

In planning / prototyping. The wavelet core (`lib/wavelet`) is the first
deliverable. The audio engine, visual engine, and timeline build on it.

## Layout

```
src/          Production-specific C/asm code (main loop, timeline)
assets/       Source assets: audio takes, textures, fonts, glyphs
docs/         Storyboard, music sketches, design notes
Makefile      Builds the final demo binary
```

## Build (eventually)

```sh
make            # development build with logging
make release    # release build, packed with smolr
make run        # run the development build
```

Currently empty placeholder.
