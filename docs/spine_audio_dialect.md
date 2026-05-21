# SPINE `audio` Dialect

**Status:** v0.1 sketch.
**Project:** Epsilon Null Operation (ε₀)
**Companion to:** `spine_core_v0_3_design.md`, `spine_dialect_template.md`,
`nerve_runtime_model.md`, `carve_design.md` (forthcoming).

---

## 0. What this document is

The `audio` dialect is where SPINE's symbolic notation meets actual
sound. The score (in dialects like `music` and `cello`) refers to
instruments and effects by name. The `audio` dialect defines those
instruments and effects as SPINE entities, in enough detail that:

- CARVE (the offline authoring tool) knows what to produce.
- NERVE (the runtime) knows how to render them.
- The binary form knows how to encode each parameter.

The dialect contract is filled out per `spine_dialect_template.md` §1.
This document is the first dialect that crosses into runtime DSP, so
it is also the first dialect to require a parameter quantization
table.

---

## 1. Domain

- **Domain name:** `audio`
- **Purpose:** define the entities that produce, transform, and route
  audio in a SPINE-driven demo. Instruments (built as trajectory
  templates over segments of wavelet bases), spaces (3D scenes for
  spatial audio), and effects (polar wavelet reverb being the
  first non-trivial one). Bridges symbolic notation in the score-side
  dialects to coefficient-space synthesis in NERVE.
- **Status:** draft v0.1, sketch sufficient for the first cello and the
  first reverb. Many gaps; this is a starting point, not a contract.

---

## 2. Concepts

Before the type catalog, three concepts the rest of the document
relies on.

### 2.1 Segment

A **segment** is a time-bounded portion of an instrument sound,
characterized by one wavelet basis family and a sparse set of fitted
coefficients in that basis. Examples:

- The scratchy onset of a bowed cello note (basis: Morlet or Gabor,
  short, broadband)
- The sustained chirplet body of the same note (basis: chirplet,
  long, narrow band, possibly time-varying center frequency)
- The decay/release after bow lift (basis: damped exponential)
- A vowel in vocal synthesis (basis: stacked formant sinusoids)
- A consonant (basis depends on type: fricative noise, plosive
  impulse, etc.)

Segments are the load-bearing primitive of the audio dialect. They are
the unit at which CARVE fits, the unit at which NERVE switches DSP
code paths, and the unit at which reachability prunes unused bases.

### 2.2 Trajectory template

A **trajectory template** is the full description of a gesture's
sonic content: an ordered sequence of segments, the stitch parameters
between them, and the expressive parameter ranges the gesture exposes
(bow position, vibrato depth, formant frequencies, etc.).

A cello dialect gesture like `cello.gesture.martelé` references one
trajectory template. CARVE produces trajectory templates by fitting
recorded samples. NERVE consumes them at playback.

Trajectory templates are the unit of cross-chat hand-off: CARVE writes
them, the audio dialect (this document) defines their schema, NERVE
reads them.

### 2.3 Coefficient quantization

The audio dialect specifies, per parameter, how that parameter is
quantized in the binary form. This is what makes the binary form small.
The text form keeps full floats; the binary form pays only the bits
the dialect prescribes.

Quantization specifications use these shorthand notations:

```
u8, u12, u16          unsigned linear, given bit width
i8, i12, i16          signed linear (two's complement)
q.N.M                 fixed-point: N integer bits + M fractional bits
log.N(min, max)       N-bit log-quantized in [min, max]
ulog.N(max)           N-bit unsigned log in [eps, max]
phase.N               N-bit phase in [0, 2π)
enum.N                N-bit symbol selector from a dialect-defined table
varint                variable-length integer (1–5 bytes typical)
ref.N                 N-bit reference to another entity, dictionary-coded
```

Per-type quantization tables appear with each type definition below.

---

## 3. Type catalog

The dialect's types are grouped: bases (§3.1), segments (§3.2),
trajectory templates (§3.3), instruments (§3.4), spatial scene (§3.5),
listeners and microphones (§3.6), effects (§3.7), and routing (§3.8).

### 3.1 Bases

Bases are precomputed and stateless. They define the *shape family*
that a segment's coefficients live in. The actual coefficients are
stored in the segment, not in the basis.

```text
Type id:        audio.basis.morlet
Required:       (none — basis is named, parameters live per-segment)
Optional:       (none in v0.1)
Lifetime:       precomputed
Notes:          Complex-valued Gabor-like wavelet. Good for onset
                transients and short-time analysis.

Type id:        audio.basis.chirplet
Required:       (none)
Optional:       (none in v0.1)
Lifetime:       precomputed
Notes:          Linear-chirp Gaussian. Center frequency varies linearly
                over the segment duration. Right basis for sustained
                bowed/blown tones with slight pitch drift.

Type id:        audio.basis.gabor
Required:       (none)
Optional:       (none in v0.1)
Lifetime:       precomputed
Notes:          Gaussian-windowed sinusoid, real-valued. Cheap; less
                expressive than Morlet for transients.

Type id:        audio.basis.damped_exp
Required:       (none)
Optional:       (none in v0.1)
Lifetime:       precomputed
Notes:          Exponentially-damped sinusoid. Natural fit for release
                segments and resonator tails.

Type id:        audio.basis.formant_stack
Required:       num_formants : int  (typically 3 or 4)
Optional:       (none in v0.1)
Lifetime:       precomputed
Notes:          Stack of Gaussian-windowed sinusoids modeling vowel
                formants. The formant frequencies are segment-level
                coefficients, not basis-level.

Type id:        audio.basis.noise_fricative
Required:       (none)
Optional:       (none in v0.1)
Lifetime:       precomputed
Notes:          Bandpass-filtered noise. Models /s/, /f/, /sh/ in
                vocals and bow-noise transients.

Type id:        audio.basis.impulse
Required:       (none)
Optional:       (none in v0.1)
Lifetime:       precomputed
Notes:          Short broadband impulse. Models /k/, /t/, /p/ in
                vocals; finger-on-string clicks; plucked-string starts.
```

**Reachability note:** a demo links in only the basis decoders it
references. A demo with only cello and ocarina probably needs
`chirplet`, `morlet`, `damped_exp`, and `noise_fricative` — about 4–6
basis decoders, each a few hundred bytes of RVV code at most.

### 3.2 Segments

A segment binds a basis to a duration and a set of fitted
coefficients.

```text
Type id:        audio.segment
Required:       basis             : ref(audio.basis.*)
                duration          : float    (local-time units)
                coefficients      : vector   (basis-specific shape)
Optional:       role              : symbol = "body"
                                    one of: "onset", "body", "release",
                                            "transition", "ornament"
                stitch_in         : float = 0.0   (crossfade-in duration)
                stitch_out        : float = 0.0   (crossfade-out duration)
Lifetime:       precomputed
Notes:          The coefficients vector's interpretation depends on
                the basis. For chirplet, it's a list of (scale,
                translate, amplitude, phase, chirp_rate) tuples. For
                formant_stack, it's a list of (formant_freq, bandwidth,
                amplitude) tuples. The basis decoder knows the shape.

                A segment's role tag is a hint to NERVE for scheduling
                and to CARVE for fitting strategy. Not strictly
                enforced by the dialect.

Quantization (binary form):
                basis            ref.6     (per-stream pruned)
                duration         q.4.12    (16 bits: 0–16 seconds at ~244µs precision)
                coefficients     varint count, then per-element per basis:
                                   amplitude  : ulog.10(max=8.0)
                                   phase      : phase.8
                                   freq/scale : log.12(min=20, max=20000)
                                   chirp_rate : i12 (Hz/sec, log-quantized)
                role             enum.3
                stitch_in/out    q.0.8     (8 bits: 0–1 in 1/256 steps)
```

A typical cello-note segment fits in roughly 8–40 wavelets. At
~5 bytes/wavelet quantized, that is 40–200 bytes per segment.

### 3.3 Trajectory templates

A trajectory template is a sequence of segments plus the parameters
the gesture exposes to the score.

```text
Type id:        audio.trajectory_template
Required:       segments          : vector of ref(audio.segment)
Optional:       expressive_params : vector of ref(audio.param_spec)
                pitch_reference   : float = 0.0  (Hz; the "natural" pitch
                                                  the template was fitted
                                                  at, used as the base
                                                  for pitch-shift)
                duration_reference: float = 1.0  (the "natural" length,
                                                  used as the base for
                                                  time-stretch)
Lifetime:       precomputed
Notes:          A trajectory template is the unit a gesture
                references. The cello dialect's gesture entities
                (cello.gesture.*) each LNK to one trajectory template
                via the gesture's "template" port. The score never
                sees this; the template id is internal to the
                instrument-side library.

                Pitch-shift and time-stretch are runtime operations
                that NERVE applies based on the score's requested
                pitch and duration relative to the template's
                references.

Quantization (binary form):
                segments         varint count, then ref.10 per segment
                expressive_params varint count, then ref.8 per param
                pitch_reference  log.10(min=20, max=20000)
                duration_reference q.4.8 (16 bits: 0–16 seconds)
```

### 3.4 Parameter specs (expressive parameter declarations)

An instrument exposes parameters that the score can vary at USE time
or that gesture-modifier MOD operators can tune. The parameter spec
declares the parameter's name, range, default, and how variations
affect the segment coefficients.

```text
Type id:        audio.param_spec
Required:       name      : symbol      (dialect-defined or instrument-defined)
                kind      : symbol      ("continuous" | "discrete")
                default   : float
Optional:       min       : float = 0.0
                max       : float = 1.0
                affects   : vector of (ref(audio.segment), ref(audio.coefficient_modulator))
                            (which segments this parameter modulates,
                             and how — see §3.4.1)
Lifetime:       precomputed
Notes:          The instrument designer (using CARVE) declares which
                expressive parameters the trajectory template exposes
                and which segments they affect. Default values are
                what the score gets if no MOD or USE override touches
                the parameter.

Quantization:   name      enum.6  (per-stream pruned)
                kind      enum.1
                default   q.4.12
                min, max  q.4.12
                affects   varint count of (ref.10, ref.8) pairs
```

#### 3.4.1 Coefficient modulators

A coefficient modulator is a small rule for how an expressive
parameter perturbs a segment's coefficients. Common forms:

- Linear scaling of a coefficient axis (e.g., `vibrato_depth` scales
  the amplitude of an LFO-like inner modulation).
- Linear shift of a frequency axis (e.g., `vibrato_rate` adds to a
  base frequency).
- Crossfade between two pre-fit segment variants (e.g., `bow_pressure`
  crossfades between "light" and "heavy" segment variants).

The full set of modulator types is dialect-level enum.4 in the binary
form. v0.1 sketch defines three:

```text
audio.coefficient_modulator.linear_scale
audio.coefficient_modulator.linear_shift
audio.coefficient_modulator.crossfade_pair
```

This is rough and will need refinement after CARVE's first real
instrument fits run. Worth deferring details until then.

### 3.5 Spatial scene

The 3D scene that the polar wavelet reverb uses, and that graphics
will eventually share.

```text
Type id:        audio.space.point_cloud
Required:       points     : vector of (x, y, z, reflectivity)
Optional:       bounds     : vector (min_xyz, max_xyz)
                background_absorption : float = 0.05
Lifetime:       precomputed
Notes:          The simplest spatial scene: a list of reflective
                points in 3D space. Each point contributes to the
                room IR proportional to its reflectivity. Suitable
                for 4k demos. Larger demos can extend to mesh-based
                or SDF-based scene types (future).

Quantization:   points     varint count, then per-point:
                             x, y, z      : q.8.8 each (meters)
                             reflectivity : ulog.6(max=1.0)
                bounds     6 × q.8.8  (optional, often elided)
                bg_absorb  ulog.6(max=1.0)
```

A 64-point cloud quantizes to roughly 1 KiB before any further
compression. A 16-point cloud (enough for a simple room shape with a
listener) costs about 64 bytes.

### 3.6 Listeners and microphones

A listener is the auditory equivalent of a camera. It has a position,
an orientation, and a microphone cluster — one virtual microphone per
output channel.

```text
Type id:        audio.listener
Required:       position : ref(curve or vector)
Optional:       orientation : ref(curve or quaternion) = identity
                microphone_cluster : ref(audio.microphone_cluster)
                                     = audio.microphone_cluster.stereo_default
Lifetime:       streaming
Notes:          The position parameter is curve-valued for moving
                listeners; a static listener uses a constant vector.
                The listener entity is what the polar wavelet reverb
                effect reads from at each audio fragment.

                Cross-domain note: the same listener entity should
                also drive the graphics camera. One curve, two
                consumers. See spine_core_v0_3_design.md §3.5.

Quantization:   position    ref.8 (to a curve or vector entity)
                orientation ref.8
                mic_cluster ref.6
```

```text
Type id:        audio.microphone_cluster
Required:       microphones : vector of (offset_xyz, channel_id)
Optional:       layout_name : symbol = "custom"
                              one of: "mono", "stereo", "quad",
                              "5_1", "7_1", "custom"
Lifetime:       precomputed
Notes:          The microphone offsets are in the listener's local
                coordinate frame. A standard stereo cluster has two
                microphones at (-0.0875, 0, 0) and (0.0875, 0, 0)
                meters from the listener position (approximate
                interaural distance).

                The cluster's microphone count is what NERVE uses at
                startup to match the actual output device. If the
                device has fewer channels, NERVE downmixes; if more,
                NERVE either replicates or routes intelligently.

Quantization:   microphones varint count, then per-mic:
                              offset_xyz : q.4.8 each (cm precision)
                              channel_id : u4
                layout_name   enum.3
```

```text
Type id:        audio.microphone_cluster.stereo_default
                (a pre-defined instance, no need to repeat in every demo)
Type id:        audio.microphone_cluster.mono_default
Type id:        audio.microphone_cluster.quad_default
                (etc., for common configurations)
```

The default clusters are dialect-provided and don't have to be defined
per-demo. Cost: zero bytes in the binary form, just a built-in
reference.

### 3.7 Effects

The first non-trivial effect. Many will follow; this one is the
prototype for the dialect's effect shape.

```text
Type id:        audio.effect.polar_wavelet_reverb
Required:       space    : ref(audio.space.*)
                listener : ref(audio.listener)
Optional:       wet      : float = 0.3
                dry      : float = 0.7
                predelay : float = 0.0       (seconds before reverb starts)
                damping  : float = 0.5       (high-frequency rolloff)
                density  : float = 0.7       (late-tail packing)
                early_late_balance : float = 0.5
                                              (0 = early reflections only,
                                               1 = late tail only)
                listener_grid : ref(audio.listener_grid) = (auto)
                                              (precomputed grid of IRs
                                               at listener positions;
                                               CARVE-generated)
Lifetime:       streaming
Notes:          Approach 3 per the polar wavelet reverb design
                decision: the direct path from each sound source to
                each microphone is computed at runtime from source
                position; the room's diffuse response (the reverb IR)
                is precomputed offline per-microphone per-listener-
                position, and is source-independent in the diffuse-
                field approximation.

                Pre-echoes: NERVE introduces a fixed global audio
                latency L (typically 100–300 ms). The reverb IR may
                contain taps at negative offsets within that latency
                window. Causality preserved in absolute time.

                IR interpolation: when the listener moves between
                precomputed grid positions, NERVE interpolates between
                the nearest grid IRs using trilinear or barycentric
                weights. The wavelet transform's linearity makes this
                valid.

                Per-channel cost at runtime: one sparse FIR
                convolution. A typical IR has 30–100 nonzero taps.
                Cheap on RVV; see CARVE design for the kernel sketch.

Quantization:   space         ref.8
                listener      ref.8
                wet, dry      q.0.10 each
                predelay      ulog.8(max=0.5)
                damping       q.0.8
                density       q.0.8
                early_late    q.0.8
                listener_grid ref.10 (large; usually the dominant cost)
```

```text
Type id:        audio.listener_grid
Required:       positions : vector of xyz   (the grid points where IRs are baked)
                irs       : vector of ref(audio.impulse_response)
                            (one IR per (position, microphone) pair)
Lifetime:       precomputed
Notes:          Generated by CARVE from the space and microphone
                cluster definitions. Grid resolution and shape are
                CARVE-side decisions; the dialect just records the
                results.

Quantization:   positions  varint count, then 3×q.8.8 per point
                irs        varint count, then ref.10 per IR
```

```text
Type id:        audio.impulse_response
Required:       taps : vector of (time_offset, amplitude)
Optional:       basis : ref(audio.basis.*) = audio.basis.impulse
                        (the per-tap shape; default is a unit impulse,
                         meaning the IR is a simple sparse FIR. Other
                         bases allow wavelet-shaped reflections.)
Lifetime:       precomputed
Notes:          Time offsets can be negative (pre-echoes within the
                global latency window).

Quantization:   taps  varint count, then per-tap:
                        time_offset : i14 (signed, fragment-sample units)
                        amplitude   : ulog.10(max=4.0)
                basis ref.6
```

Other effects (`audio.effect.lowpass_filter`, `audio.effect.distortion`,
`audio.effect.chorus`, `audio.effect.delay`) will follow the same
pattern but are not specified in this v0.1 sketch.

### 3.8 Routing and master bus

```text
Type id:        audio.bus
Required:       channels : int
Optional:       gain     : float = 1.0
Lifetime:       streaming
Notes:          A bus is a routing node with N input ports and N
                output ports. Multiple instruments LNK their outputs
                into the bus's inputs; effects LNK their inputs from
                the bus's outputs; the master bus terminates at the
                audio output device.

Quantization:   channels u4
                gain     q.0.10
```

```text
Type id:        audio.master_out
Required:       (none)
Optional:       (none in v0.1)
Lifetime:       sink
Notes:          The terminal node. One per demo. NERVE wires this to
                the actual audio output device at startup. Channel
                count is determined by the device, not the dialect.
```

---

## 4. Ports

The audio dialect's ports carry three shapes, per SPINE v0.3 §3.5:

- **signal:** continuous audio (one sample per audio fragment slot)
- **value:** scalar control parameter (one update per audio fragment
  or slower)
- **event:** discrete trigger (note_on, etc.)

```text
audio.basis.*:                   no ports (referenced by segments)

audio.segment:                   no ports (referenced by templates)

audio.trajectory_template:       in:  event note_on
                                      value pitch
                                      value duration
                                      value expressive_param (varies)
                                 out: signal audio

audio.space.*:                   no ports (referenced by reverb)

audio.listener:                  in:  value position (curve-fed)
                                      value orientation
                                 out: (none — the listener is read by
                                       effects, not LNKed to)

audio.effect.polar_wavelet_reverb:
                                 in:  signal audio_in[N_channels]
                                 out: signal audio_out[N_channels]

audio.bus:                       in:  signal audio_in[N_channels]
                                 out: signal audio_out[N_channels]

audio.master_out:                in:  signal audio_in[N_channels]
                                 out: (sink)
```

Multi-source inputs combine per SPINE v0.3 (signal sources sum;
event sources OR).

---

## 5. Operators

The audio dialect's MOD operators are sparse in v0.1. Most expressive
variation flows through expressive parameters on trajectory templates
(§3.4), not through MOD on the audio entities themselves. Score-side
dialects (music, cello) carry most of the MOD vocabulary.

```text
Operator:  pitch_shift
Args:      float (semitones)
Applies:   audio.trajectory_template
Effect:    Shifts the template's pitch_reference for instances created
           via the MOD. Equivalent to using a different fundamental
           pitch when rendering. Resampling done by NERVE.
Composes:  with time_stretch independently.

Operator:  time_stretch
Args:      float (factor, default 1.0)
Applies:   audio.trajectory_template
Effect:    Scales the template's duration_reference. NERVE rescales
           segment durations and coefficient time-axes accordingly.
Composes:  with pitch_shift; in v0.1 the two are independent
           (no formant correction during pitch_shift).

Operator:  brighten / darken
Args:      float (amount, ~0.0-1.0)
Applies:   audio.trajectory_template
Effect:    Tilts the segment coefficients' amplitude vs. frequency:
           brighten emphasizes high frequencies, darken emphasizes
           low. A pre-baked frequency-tilt filter applied at
           render time.
Composes:  with everything.
```

The cello dialect's operators (with_pressure, decelerando, humanize,
etc.) ultimately translate to coefficient modulators on the
underlying trajectory template — but the score writer never sees this
translation. It happens inside the cello-dialect interpreter at
expansion time.

---

## 6. Override keys

USE override keys (not specified above as MOD operators) for
instances of audio entities:

```text
Override:  gain
Args:      float (0–4, log-quantized)
Applies:   any audio entity
Effect:    Multiplies output amplitude. Instance-only.

Override:  pan
Args:      float (-1.0 = full left, +1.0 = full right)
Applies:   any audio output
Effect:    Stereo positioning override. Bypasses the spatial system
           for "just put it on this side" usage.

Override:  send
Args:      vector of (ref(audio.bus), float gain)
Applies:   any audio output
Effect:    Routes a copy of the instance's output to one or more
           additional buses. Used for parallel processing (e.g.,
           dry signal to master + send to reverb bus).
```

---

## 7. Lifetime classification summary

For NERVE scheduling, the audio dialect's types fall into:

| Type                              | Lifetime       |
|-----------------------------------|----------------|
| `audio.basis.*`                   | precomputed    |
| `audio.segment`                   | precomputed    |
| `audio.trajectory_template`       | precomputed    |
| `audio.param_spec`                | precomputed    |
| `audio.coefficient_modulator.*`   | precomputed    |
| `audio.space.*`                   | precomputed    |
| `audio.listener_grid`             | precomputed    |
| `audio.impulse_response`          | precomputed    |
| `audio.microphone_cluster.*`      | precomputed    |
| `audio.listener`                  | streaming      |
| `audio.effect.*`                  | streaming      |
| `audio.bus`                       | streaming      |
| `audio.master_out`                | sink           |
| (instance of a trajectory template at runtime) | event-driven |

Note that the trajectory template entity itself is precomputed (the
template's coefficients are loaded once), but each note event the
score triggers creates an event-driven *instance* of the template.
This instance has per-note state (current phase, current bow position,
current expressive-param values, vibrato LFO phase). It is born on
note_on, lives for the note's duration, and is torn down on note_off
or natural decay.

---

## 8. Transition table

The audio dialect itself does not have transitions. Gesture
transitions are score-side concerns (cello dialect §3.8). When a
cello dialect transition resolves to "continue the bow," the audio
dialect just receives the second trajectory template's note_on event
with a `transition_from=<previous instance id>` parameter; the
instrument decides what to do with the previous instance's tail.

---

## 9. Time interpretation

- **Time-positioned types:** trajectory template instances (each
  note placed in score time by music/cello dialects).
- **Non-time-positioned types:** everything else. Bases, segments,
  spaces, listeners, effects, buses are definitions or persistent
  routing; they don't have a "place" in time.
- **Stretching behavior:** when a USE's `dur` differs from the
  template's `duration_reference`, segment durations and coefficient
  time-axes scale proportionally. Pitch is unaffected (separate axis).

---

## 10. Lifetime and execution — runtime detail

Implementation hand-off to NERVE. See `nerve_runtime_model.md` for
broader runtime architecture.

- **Audio output latency L:** NERVE introduces a fixed global latency
  (target 100–300 ms; final value chosen at startup based on device
  capabilities). The reverb IR's negative time offsets live within
  this window. Implementation: ring buffer of size at least
  `L + max_IR_length`.
- **Audio fragment size:** NERVE picks at startup (target 64–256
  samples at 48 kHz). All dialect parameter updates are at fragment
  rate, not sample rate, unless explicitly noted.
- **Per-fragment work:** for each active trajectory template
  instance, NERVE walks the current segment, accumulates the segment
  basis's contribution into the instance's output buffer, applies
  expressive parameter modulations, mixes into the destination bus.
  For each active reverb, NERVE selects/interpolates the
  listener-position-appropriate IR and runs sparse FIR convolution
  per channel.
- **Source-to-microphone direct path:** computed per-fragment per
  active note. Delay = `|source - mic| / c`; amplitude =
  `1 / max(|source - mic|, near_field_radius)^2`. Bypasses the
  reverb IR; routed directly to the master bus per channel.
- **Speaker discovery:** at startup, NERVE queries ALSA / the audio
  backend for output channel count. Selects the matching default
  microphone cluster, or uses a custom cluster if the demo specifies
  one and channel counts match.

---

## 11. Interpreter notes

- **Implementation:** Python expander for now (in `tools/spine/`,
  alongside the music and cello dialect interpreters). C
  implementation arrives with the first audio-producing prototype.
- **CARVE produces:** `audio.trajectory_template`,
  `audio.segment`, `audio.impulse_response`, `audio.listener_grid`,
  `audio.space.point_cloud` entities. CARVE writes these in the
  text form; the SPINE build pipeline produces the binary form.
- **NERVE consumes:** the binary form. Per-fragment audio rendering
  per §10.
- **Dependencies:** SPINE core v0.3 or later. No dependencies on
  other dialects (music and cello reference the audio dialect, not
  the other way around).
- **Known limitations:**
  - v0.1 is a sketch. Most types are coarsely specified and will
    refine as CARVE produces real instruments.
  - Quantization tables are first-cut estimates. Real values
    follow from measured fits.
  - Coefficient modulator types are placeholders. Real shapes follow
    CARVE's first fitting runs.
  - No formant-correction for pitch_shift. Future work.
  - No convolution-reverb path beyond the polar wavelet design.
    Simpler reverbs (Schroeder, FDN) may be added as separate
    `audio.effect.*` types for demos that prune the spatial path.

---

## 12. Open questions

Listed here rather than in `spine_open_questions.md` because they are
audio-dialect-specific.

1. **Segment role enum size.** v0.1 has 5 roles (`onset`, `body`,
   `release`, `transition`, `ornament`); enum.3 fits 8. Will more
   roles be needed once vocal and noise instruments arrive?
2. **Coefficient modulator vocabulary.** Three placeholders in §3.4.1
   are almost certainly insufficient. Will need expansion based on
   real instrument fits.
3. **Listener grid resolution.** How dense should the precomputed
   listener-position grid be? Trade-off: dense grid → smooth
   interpolation but more storage; sparse grid → small storage but
   audible interpolation artifacts on rapid motion. CARVE-side
   decision; this dialect just records the grid as authored.
4. **Source-position routing.** The direct path is per (source,
   microphone) pair. Is the source position a USE override on the
   instrument USE, or a separate entity (`audio.source_position`)
   that LNKs into the instrument? Leaning toward USE override (`loc=`
   in SPINE core §3.2 already exists), but a moving source needs a
   curve-valued loc, which works in v0.3 of SPINE core.
5. **Microphone cluster compatibility.** What happens when the demo
   specifies a 5.1 cluster but the device is stereo? Auto-downmix
   (probably) or refuse (probably not). Decided at startup by NERVE;
   the dialect should declare a fallback policy per cluster.
6. **Pre-echo expressivity.** Negative-R taps were the user's
   creative ask. In v0.1 they are just IR taps with negative time
   offsets. Will this be expressive enough for "freaky pre-echo"
   artistic intent, or do we need a separate `audio.effect.pre_echo`
   type? Defer until CARVE has done one.
7. **Binary form encoding of curve-valued parameters.** A listener's
   position is a curve; the binary form needs to encode either an
   inline curve (sparse keyframes?) or a reference to a curve entity
   defined elsewhere. SPINE core v0.3 §4.4 already specifies curves
   as a value type, so the encoding lives there, but the
   audio-dialect spec should make explicit which audio parameters
   accept curves.
8. **Multi-source reverb integration.** Approach 3 says the direct
   path is computed per (source, mic) at runtime. When many sources
   are active simultaneously (a chord, a chorus), does the direct
   path computation become a bottleneck? Probably no for ε₀-scale
   demos (≤ 16 simultaneous voices), but worth a benchmark before
   committing.

---

## 13. Worked example: a cello note with reverb

Sketch of how a cello note resolves through this dialect, glossing
the binary form for readability:

```text
# Instrument-side library (built once by CARVE, shipped with demo):
DEF basis_chirplet : audio.basis.chirplet { }
DEF basis_morlet   : audio.basis.morlet   { }
DEF basis_damped   : audio.basis.damped_exp { }

DEF seg_cello_d4_onset : audio.segment {
  basis = basis_morlet
  duration = 0.04
  role = "onset"
  coefficients = [...]            # fitted by CARVE
  stitch_out = 0.01
}

DEF seg_cello_d4_body : audio.segment {
  basis = basis_chirplet
  duration = 0.85
  role = "body"
  coefficients = [...]
  stitch_in = 0.01
  stitch_out = 0.02
}

DEF seg_cello_d4_release : audio.segment {
  basis = basis_damped
  duration = 0.1
  role = "release"
  coefficients = [...]
  stitch_in = 0.02
}

DEF traj_cello_d4_legato : audio.trajectory_template {
  segments = [seg_cello_d4_onset, seg_cello_d4_body, seg_cello_d4_release]
  pitch_reference = 293.66        # D4 in Hz
  duration_reference = 0.99
  expressive_params = [param_bow_pressure, param_vibrato_depth, ...]
}

# Spatial setup:
DEF room_simple : audio.space.point_cloud {
  points = [(−2.0, 0, 0, 0.5), (2.0, 0, 0, 0.5),
            (0, −1.5, 0, 0.3), (0, 1.5, 0, 0.3),
            (0, 0, 2.5, 0.7), (0, 0, −2.5, 0.7)]    # a small box
}

DEF listener_static : audio.listener {
  position = (0, 0, 0)
  microphone_cluster = audio.microphone_cluster.stereo_default
}

DEF reverb_room : audio.effect.polar_wavelet_reverb {
  space = room_simple
  listener = listener_static
  wet = 0.25
  dry = 0.75
}

DEF master : audio.bus { channels = 2 }
DEF out    : audio.master_out { }

LNK reverb_room.audio_out -> master.audio_in
LNK master.audio_out -> out.audio_in

# Score side (cello dialect, in a separate file):
# A cello note USE references the trajectory template indirectly
# via cello.gesture.legato.
# At expansion time, cello.gesture.legato resolves to traj_cello_d4_legato
# (the right pitch variant chosen by NERVE at runtime via pitch_shift).
# The cello instrument LNKs to reverb_room.audio_in.
```

This is one cello note in one stereo room. Binary form estimate:

- 3 bases: ~6 bytes (references; bases themselves are dialect-defined)
- 3 segments: ~120 bytes (40 bytes each, 20–40 wavelets)
- 1 trajectory template: ~30 bytes (refs + small floats)
- 1 point cloud (6 points): ~30 bytes
- 1 listener: ~6 bytes
- 1 reverb effect: ~10 bytes + IR grid storage
- IR grid (1 listener position × 2 mics × 50 taps): ~600 bytes
- 1 bus, 1 master out: ~4 bytes

Total: roughly 800 bytes for one fully-spatialized cello note. The IR
is the dominant cost. A 64k demo can afford many such configurations;
a 4k demo would share the IR across the whole piece (one room, used
for every instrument) and use 8–16 trajectory templates total. Plausible.

---

## 14. One-page reminder

```
What the audio dialect adds to SPINE:

bases        precomputed wavelet shape families (morlet, chirplet, …)
segments     time-bounded chunks of coefficients in one basis
templates    sequences of segments forming gesture trajectories
params       expressive parameters that modulate template coefficients
spaces       3D point clouds defining reverb scenes
listeners    moving audio cameras with microphone clusters
effects      polar wavelet reverb (and future effects)
buses        multi-channel routing

The score never sees coefficients. It names gestures.
The dialect (this doc) defines what gestures resolve to.
CARVE produces the coefficient data offline.
NERVE renders it per audio fragment at runtime.
Parameter quantization is dialect-side, locked per type.
The binary form is dictionary-coded per-stream per dialect.
```

That is the audio dialect.
