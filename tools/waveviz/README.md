# tools/waveviz

The audio/wavelet inspector & timeline GUI.

A development tool, not part of any demo binary. Used to design, audition,
and debug audio content before baking it into a production.

## Planned features

- Timeline with overlaid waveform (amplitude/time) and wavelet square grid
- Per-square coefficient heatmap, I and Q channels visible side-by-side
- Stamp browser: see every stamp contributing to a given square
- Live audition: scrub the timeline, hear it in real time
- Edit: drag stamps, tweak gain, change delays, see the result instantly
- Import: WAV files via `lib/io`, decompose into wavelet squares
- Export: save stamp lists as C arrays for inclusion in production code

## Likely tech

SDL2 + ImGui (or Dear ImGui in C via cimgui) for the UI. We discussed
unifying on SDL2 for both prototyping and the demo, so this is consistent.

Currently empty placeholder.
