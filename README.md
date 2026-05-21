# Epsilon Null Operation (ENO)

Demoscene crew building audiovisual productions for RISC-V Linux (SpaceMit K1/K3
and friends), starting with the **Desert Monument** 64k.

ENO is a hint to enumeration, and an anagram for ONE — unity among people.
Epsilon Null (ε₀) is the smallest ordinal beyond every finite ω-tower; it's
the answer to "I love you. I love you 2. I love you 3. I love you ∞. I love
you ∞². I love you ε₀."

## Crew

| Name    | Role                                                         |
|---------|--------------------------------------------------------------|
| Roland  | Code, math, direction                                        |
| Elise   | Flute, drums                                                 |
| Simon   | Cello, guitar, oud, DAW production                           |
| Segher  | Build tools, GCC, possibly SMOLR (Linux RISC-V exe packer)   |

## Layout

```
eno/
├── lib/              Shared libraries (the ENO toolkit)
│   ├── crest/          1D/2D/3D wavelets, chirplets, polar bases (CREST)
│   ├── siftr/          Softsynth: stamps, envelopes, oscillators (SIFTR)
│   ├── fx/             Audio effects: reverb, chorus, etc.
│   ├── gfx/            GLSL helpers, SDF primitives, post-fx
│   ├── core/           Arena, math utils, fixed-size containers
│   └── io/             WAV loading, OGG, raw resource bundling
├── tools/            Build/dev tools (run on host)
│   ├── smolr/          (planned) Linux RISC-V executable packer
│   ├── carve/          Wavelet/coefficient authoring tool (CARVE)
│   └── glint/          GLSL shader minifier/packer (GLINT)
├── prods/            Demoscene productions
│   └── desert-monument/  ENO #1, target: 64k Linux RISC-V
├── docs/             Design notes, post-mortems, theory
└── third_party/      Vendored dependencies (libsndfile snapshots, etc.)
```

## Building

Each subdirectory is independently buildable with `make`. The top-level
`Makefile` builds everything in dependency order.

```sh
make                  # build everything
make test             # run all test suites
make -C lib/crest     # build just the CREST wavelet library
make -C prods/desert-monument  # build the demo
```

## License

TBD — likely a permissive license for the libraries, with productions kept
proprietary until after their respective release parties.
