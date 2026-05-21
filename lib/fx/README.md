# lib/fx

Audio effects, all expressed as stamp clusters in wavelet space.

## Planned contents

- **Reverb**: reflector-bank model. Each reflector is a (delay, gain,
  per-band damping) triple; reverb is N stamps from source into mix.
  Polar wavelets parametrise the reflector positions.
- **Chorus / flanger**: small clusters of modulated stamps.
- **Filters**: per-band gain shaping (already supported in stamp's
  use_per_band_gain path).
- **Distortion / saturation**: applied in coefficient space.

Depends on `lib/crest` and `lib/core`.

Currently empty placeholder.
