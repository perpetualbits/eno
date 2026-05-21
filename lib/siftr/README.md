# lib/siftr — SIFTR softsynth

Softsynth built on the CREST wavelet stamping primitive. Operates in
coefficient space throughout.

## Planned contents

- **Voice**: an active sound source with envelope, pitch, gain.
- **Voice bank**: pool of voices, allocation strategy (oldest-out, etc).
- **Envelopes**: ADSR, multi-segment exponential, splines.
- **Oscillators / atoms**: sine, chirp, noise, plucked, wavetable —
  all expressed as pre-baked wavelet squares ready to be stamped.
- **Note triggers**: high-level "play this atom at time t with pitch p
  and gain g" API.

Depends on `lib/crest` and `lib/core`.

Currently empty placeholder.
