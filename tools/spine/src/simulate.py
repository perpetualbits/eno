#!/usr/bin/env python3
"""
src/simulate.py — SPINE v0.2 Prototype C streaming-patch simulator.

Reads a .spine file, resolves it as a patch graph via expand.py, then
ticks the graph at a fixed rate (default 100 Hz) for some number of
simulated seconds. Emits:

  - a CSV trace (one row per tick, one column per probe)
  - a readable trace (one line per tick per probe)
  - summary statistics (min/max/mean/RMS per probe, NaN/Inf detection)

This is design-validation tooling, NOT an audio synthesizer. Stub
functions stand in for real DSP: sine for oscillators, IIR averaging
for filters, simple shift register for delays, etc. The point is to
prove the graph resolves coherently and that feedback loops converge
rather than explode.

Architecture:
  - simulate.py imports expand.py to share the parser and resolver
  - one TickFn per type id maps (node, inputs, state, dt, t) -> outputs
  - simultaneous-update tick model: every node reads last tick's
    output values from its sources, computes its new state, writes its
    new output. Naturally handles feedback via the implicit one-tick
    delay on every edge.

Usage:
    python3 src/simulate.py path/to/file.spine
    python3 src/simulate.py path/to/file.spine --duration 5.0 --rate 100
    python3 src/simulate.py path/to/file.spine --csv trace.csv
    python3 src/simulate.py path/to/file.spine --probes lfo_a,scene_main
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import random
import sys
from dataclasses import dataclass, field
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import expand  # noqa: E402


# =====================================================================
# Tick functions per type. Each returns the node's new output(s) given
# its inputs (a dict of port_name -> last-tick value) and its mutable
# state dict. State is per-node and persists across ticks.
#
# Conventions:
#   - All outputs are floats in roughly [-1, 1] for signals, arbitrary
#     range for values, and bool (True/False) for events.
#   - Inputs missing from the inputs dict default to 0.0 (or False for
#     event ports).
#   - State dicts are initialized lazily; tick functions populate them
#     on first call.
# =====================================================================


def _input(inputs: dict[str, Any], port: str, default: float = 0.0) -> float:
    """Return the float value of `port` from inputs, or `default` if absent or None."""
    v = inputs.get(port, default)
    if v is None:
        return default
    return float(v)


def _event_input(inputs: dict[str, Any], port: str) -> bool:
    """Return True if the event port fired this tick, False otherwise."""
    return bool(inputs.get(port, False))


def tick_oscillator(params, inputs, state, dt, t):
    """Tick a band-limited oscillator (sine/square/sawtooth/triangle). Returns {"out": sample}."""
    freq = float(params.get("freq", 440.0))
    mod = _input(inputs, "freq_mod")  # additive in Hz
    phase = state.get("phase", 0.0)
    eff_freq = max(0.0, freq + mod)
    phase = (phase + eff_freq * dt) % 1.0
    state["phase"] = phase
    wf = str(params.get("waveform", "sine"))
    if wf == "sine":
        out = math.sin(2 * math.pi * phase)
    elif wf == "square":
        out = 1.0 if phase < 0.5 else -1.0
    elif wf == "sawtooth":
        out = 2.0 * phase - 1.0
    elif wf == "triangle":
        out = 4.0 * abs(phase - 0.5) - 1.0
    else:
        out = math.sin(2 * math.pi * phase)
    return {"out": out}


def tick_lfo(params, inputs, state, dt, t):
    """Tick a low-frequency oscillator with amplitude and offset scaling. Returns {"out": value}."""
    # LFO is structurally the same as oscillator but outputs a `value`
    # with amplitude+offset (so it can sweep a cutoff between e.g. 200
    # and 800 Hz without rescaling on the way).
    freq = float(params.get("freq", 1.0))
    mod = _input(inputs, "freq_mod")
    amplitude = float(params.get("amplitude", 1.0))
    offset = float(params.get("offset", 0.0))
    phase = state.get("phase", 0.0)
    eff_freq = max(0.0, freq + mod)
    phase = (phase + eff_freq * dt) % 1.0
    state["phase"] = phase
    wf = str(params.get("waveform", "sine"))
    if wf == "sine":
        raw = math.sin(2 * math.pi * phase)
    elif wf == "triangle":
        raw = 4.0 * abs(phase - 0.5) - 1.0
    elif wf == "sawtooth":
        raw = 2.0 * phase - 1.0
    else:
        raw = math.sin(2 * math.pi * phase)
    return {"out": offset + amplitude * raw}


def tick_noise(params, inputs, state, dt, t):
    """Tick a white-noise source. Returns a uniformly random sample in [-1, 1]."""
    return {"out": random.uniform(-1.0, 1.0)}


def tick_clock(params, inputs, state, dt, t):
    """Tick a clock node. Fires a trigger event once per 1/rate seconds."""
    rate = float(params.get("rate", 1.0))
    mod = _input(inputs, "rate_mod")
    eff_rate = max(0.01, rate + mod)
    phase = state.get("phase", 0.0)
    new_phase = phase + eff_rate * dt
    fired = new_phase >= 1.0
    if fired:
        new_phase -= 1.0
    state["phase"] = new_phase
    return {"trigger": fired}


def tick_dice(params, inputs, state, dt, t):
    """Tick a sample-and-hold randomizer. Picks a new value on each incoming trigger."""
    triggered = _event_input(inputs, "trigger")
    if triggered:
        unipolar = bool(params.get("unipolar", False))
        scale = float(params.get("scale", 1.0))
        offset = float(params.get("offset", 0.0))
        if unipolar:
            raw = random.random()
        else:
            raw = random.uniform(-1.0, 1.0)
        state["held"] = offset + scale * raw
    return {"out": state.get("held", 0.0)}


def tick_envelope(params, inputs, state, dt, t):
    """Tick an ADSR envelope. Autoreleases from sustain after the decay time."""
    triggered = _event_input(inputs, "trigger")
    attack = float(params.get("attack", 0.01))
    decay = float(params.get("decay", 0.1))
    sustain = float(params.get("sustain", 0.5))
    release = float(params.get("release", 0.2))
    if triggered:
        state["phase"] = "a"
        state["t_phase"] = 0.0
        state["value"] = state.get("value", 0.0)
    phase = state.get("phase", "idle")
    tp = state.get("t_phase", 0.0) + dt
    val = state.get("value", 0.0)
    if phase == "a":
        val = min(1.0, tp / max(attack, 1e-6))
        if tp >= attack:
            phase = "d"
            tp = 0.0
    elif phase == "d":
        val = 1.0 + (sustain - 1.0) * min(1.0, tp / max(decay, 1e-6))
        if tp >= decay:
            phase = "s"
    elif phase == "s":
        # In Prototype C we autorelease after sustain length = decay
        # (no note_off events yet). Triggers come from a clock so this
        # is the right shape for the soundscape.
        if tp >= decay:
            phase = "r"
            tp = 0.0
            state["release_from"] = val
    elif phase == "r":
        rf = state.get("release_from", val)
        val = rf * (1.0 - min(1.0, tp / max(release, 1e-6)))
        if tp >= release:
            phase = "idle"
            val = 0.0
    else:
        val = 0.0
    state["phase"] = phase
    state["t_phase"] = tp
    state["value"] = val
    return {"out": val}


def tick_lowpass(params, inputs, state, dt, t):
    """Tick a 1-pole IIR lowpass filter. Coefficient is derived from cutoff frequency."""
    # 1-pole IIR: y = a*x + (1-a)*y_prev, where a comes from cutoff.
    sig = _input(inputs, "in")
    cutoff = float(params.get("cutoff", 1000.0))
    mod = _input(inputs, "cutoff_mod")
    eff_cutoff = max(1.0, cutoff + mod)
    # Map cutoff to coefficient. At our tick rate, this is a wide
    # approximation, fine for design validation.
    a = 1.0 - math.exp(-2.0 * math.pi * eff_cutoff * dt)
    a = max(0.0, min(1.0, a))
    y_prev = state.get("y", 0.0)
    y = a * sig + (1.0 - a) * y_prev
    state["y"] = y
    return {"out": y}


def tick_highpass(params, inputs, state, dt, t):
    """Tick a 1st-order IIR highpass filter."""
    # Simple 1st-order highpass.
    sig = _input(inputs, "in")
    cutoff = float(params.get("cutoff", 100.0))
    mod = _input(inputs, "cutoff_mod")
    eff_cutoff = max(1.0, cutoff + mod)
    a = math.exp(-2.0 * math.pi * eff_cutoff * dt)
    a = max(0.0, min(1.0, a))
    x_prev = state.get("x_prev", 0.0)
    y_prev = state.get("y_prev", 0.0)
    y = a * (y_prev + sig - x_prev)
    state["x_prev"] = sig
    state["y_prev"] = y
    return {"out": y}


def tick_filter(params, inputs, state, dt, t):
    """Tick the generic Prototype-B filter (simulated as a lowpass for now)."""
    # The generic Prototype-B filter. Treat as lowpass for simulation.
    return tick_lowpass(params, inputs, state, dt, t)


def tick_delay(params, inputs, state, dt, t):
    """Tick a delay line with feedback. Buffer length tracks the modulated delay time."""
    sig = _input(inputs, "in")
    time = float(params.get("time", 0.1))
    feedback = float(params.get("feedback", 0.0))
    mod_t = _input(inputs, "time_mod")
    mod_fb = _input(inputs, "fb_mod")
    eff_time = max(dt, time + mod_t)
    eff_fb = max(-0.99, min(0.99, feedback + mod_fb))
    nsamples = max(1, int(round(eff_time / dt)))
    buf = state.setdefault("buf", [0.0] * nsamples)
    # Resize if mod changed delay length.
    if len(buf) != nsamples:
        # Pad or truncate, preserving recent samples.
        if nsamples > len(buf):
            buf = [0.0] * (nsamples - len(buf)) + buf
        else:
            buf = buf[-nsamples:]
    delayed = buf[0]
    out = delayed
    buf.pop(0)
    buf.append(sig + eff_fb * delayed)
    state["buf"] = buf
    return {"out": out}


def tick_allpass_delay(params, inputs, state, dt, t):
    """Tick a first-order allpass filter: y = -g*x + x_d + g*y_d."""
    # First-order allpass:  y = -g*x + x_d + g*y_d
    sig = _input(inputs, "in")
    time = float(params.get("time", 0.05))
    g = float(params.get("feedback", 0.5))
    mod_t = _input(inputs, "time_mod")
    mod_fb = _input(inputs, "fb_mod")
    eff_time = max(dt, time + mod_t)
    eff_g = max(-0.99, min(0.99, g + mod_fb))
    nsamples = max(1, int(round(eff_time / dt)))
    x_buf = state.setdefault("x_buf", [0.0] * nsamples)
    y_buf = state.setdefault("y_buf", [0.0] * nsamples)
    if len(x_buf) != nsamples:
        if nsamples > len(x_buf):
            x_buf = [0.0] * (nsamples - len(x_buf)) + x_buf
            y_buf = [0.0] * (nsamples - len(y_buf)) + y_buf
        else:
            x_buf = x_buf[-nsamples:]
            y_buf = y_buf[-nsamples:]
    x_d = x_buf[0]
    y_d = y_buf[0]
    y = -eff_g * sig + x_d + eff_g * y_d
    x_buf.pop(0); x_buf.append(sig)
    y_buf.pop(0); y_buf.append(y)
    state["x_buf"] = x_buf
    state["y_buf"] = y_buf
    return {"out": y}


def tick_gain(params, inputs, state, dt, t):
    """Tick a gain node: multiply the input signal by gain * gain_mod."""
    sig = _input(inputs, "in")
    g = float(params.get("gain", 1.0))
    mod = _input(inputs, "gain_mod", default=1.0)
    return {"out": sig * g * mod}


def tick_mixer(params, inputs, state, dt, t):
    """Tick a mixer: sum all connected inN inputs and divide by count for unity gain."""
    # Sum all connected `inN` inputs. Divide by count for unity gain.
    s = 0.0
    n = 0
    for k, v in inputs.items():
        if k.startswith("in") and v is not None:
            s += float(v)
            n += 1
    if n > 0:
        s /= n
    return {"out": s}


def tick_passthrough(params, inputs, state, dt, t):
    """Tick a terminal node (patch.output / patch.scene_out): pass through the input signal."""
    # patch.output and patch.scene_out — terminal nodes.
    return {"out": _input(inputs, "in")}


# Music dialect types are not ticked in the simulator. They appear in
# the graph as sources, but Prototype C does not simulate event-driven
# music expansion through the patch — that's Prototype D+ territory.
def tick_music_passthrough(params, inputs, state, dt, t):
    """Placeholder tick for music dialect nodes, which are not simulated in Prototype C."""
    return {}


TICK_FNS: dict[str, Any] = {
    "patch.oscillator": tick_oscillator,
    "patch.lfo": tick_lfo,
    "patch.noise": tick_noise,
    "patch.clock": tick_clock,
    "patch.dice": tick_dice,
    "patch.envelope": tick_envelope,
    "patch.lowpass": tick_lowpass,
    "patch.highpass": tick_highpass,
    "patch.filter": tick_filter,
    "patch.delay": tick_delay,
    "patch.allpass_delay": tick_allpass_delay,
    "patch.gain": tick_gain,
    "patch.mixer": tick_mixer,
    "patch.output": tick_passthrough,
    "patch.scene_out": tick_passthrough,
    # Music sources are non-ticking placeholders for now.
    "music.note": tick_music_passthrough,
    "music.rest": tick_music_passthrough,
    "music.phrase": tick_music_passthrough,
    "music.instrument": tick_music_passthrough,
}


# =====================================================================
# Simulation driver
# =====================================================================


@dataclass
class ProbeStats:
    name: str
    min_v: float = float("inf")
    max_v: float = float("-inf")
    sum_v: float = 0.0
    sum_sq: float = 0.0
    n: int = 0
    nan_count: int = 0
    inf_count: int = 0

    def observe(self, v: float) -> None:
        if isinstance(v, bool):
            v = 1.0 if v else 0.0
        try:
            fv = float(v)
        except (TypeError, ValueError):
            return
        if math.isnan(fv):
            self.nan_count += 1
            return
        if math.isinf(fv):
            self.inf_count += 1
            return
        self.min_v = min(self.min_v, fv)
        self.max_v = max(self.max_v, fv)
        self.sum_v += fv
        self.sum_sq += fv * fv
        self.n += 1

    def mean(self) -> float:
        return self.sum_v / self.n if self.n > 0 else 0.0

    def rms(self) -> float:
        if self.n == 0:
            return 0.0
        return math.sqrt(self.sum_sq / self.n)

    def as_line(self) -> str:
        if self.n == 0:
            return f"  {self.name:<20}  n=0 (never observed)"
        flags = []
        if self.nan_count:
            flags.append(f"NaN×{self.nan_count}")
        if self.inf_count:
            flags.append(f"Inf×{self.inf_count}")
        if abs(self.max_v - self.min_v) < 1e-9:
            flags.append("flat")
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        return (
            f"  {self.name:<20}  "
            f"min={self.min_v:+.4f}  max={self.max_v:+.4f}  "
            f"mean={self.mean():+.4f}  rms={self.rms():.4f}{flag_str}"
        )


@dataclass
class SimResult:
    rate_hz: float
    duration_s: float
    ticks: int
    probe_names: list[str]
    csv_rows: list[list[float]]   # [tick_index, *probes] per row
    stats: dict[str, ProbeStats]
    warnings: list[str]


def select_probes(
    graph: expand.PatchGraph,
    requested: list[str] | None,
) -> list[tuple[str, str]]:
    """Return the list of (node_id, port_name) tuples to record.

    If `requested` is None, default probes are:
      - the `in` port of every patch.scene_out (the final output)
      - the `out` port of every patch.lfo (modulation source visibility)
    """
    by_id = {n.id: n for n in graph.nodes}
    if requested:
        out: list[tuple[str, str]] = []
        for spec in requested:
            if "." in spec:
                node, port = spec.split(".", 1)
            else:
                node, port = spec, "out"
            if node in by_id:
                out.append((node, port))
        return out

    probes: list[tuple[str, str]] = []
    for n in graph.nodes:
        if n.type_id == "patch.scene_out":
            probes.append((n.id, "in"))
    for n in graph.nodes:
        if n.type_id == "patch.lfo":
            probes.append((n.id, "out"))
    return probes


def simulate(
    graph: expand.PatchGraph,
    duration_s: float = 5.0,
    rate_hz: float = 100.0,
    seed: int | None = 42,
    probes: list[tuple[str, str]] | None = None,
) -> SimResult:
    """Run the patch graph for `duration_s` simulated seconds.

    Uses a simultaneous-update model: each tick, every node computes
    its new output from the *previous* tick's input values. This
    naturally handles feedback via an implicit one-tick delay on every
    edge.
    """
    if seed is not None:
        random.seed(seed)

    dt = 1.0 / rate_hz
    n_ticks = int(round(duration_s * rate_hz))

    # Index edges by destination (node_id, port_name) -> list of sources.
    # Multiple edges can target the same port (e.g. a delay's `in` may
    # receive a regular signal plus a feedback path; both should sum).
    # The tick function receives the summed value via the inputs dict.
    incoming: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for e in graph.edges:
        incoming.setdefault((e.dst_node, e.dst_port), []).append(
            (e.src_node, e.src_port)
        )

    # Last-tick output buffer: (node_id, port_name) -> value.
    last: dict[tuple[str, str], Any] = {}
    # Per-node state dicts.
    states: dict[str, dict[str, Any]] = {n.id: {} for n in graph.nodes}

    # Probe list defaults: scene_out inputs and lfo outputs.
    if probes is None:
        probes = select_probes(graph, None)
    probe_names = [f"{n}.{p}" for n, p in probes]
    stats = {name: ProbeStats(name=name) for name in probe_names}
    csv_rows: list[list[float]] = []
    warnings: list[str] = []

    # Topological order, computed by the resolver. Within a tick, we
    # iterate in topo order so that non-feedback dependencies see this
    # tick's values; feedback dependencies see last tick's. This is a
    # mild simplification of the pure simultaneous-update model and
    # gives more sensible transient behavior at startup.
    order = list(graph.order)
    type_by_id = {n.id: n.type_id for n in graph.nodes}
    params_by_id = {n.id: n.params for n in graph.nodes}
    feedback_inputs: set[tuple[str, str]] = set()
    for e in graph.edges:
        if e.is_feedback:
            feedback_inputs.add((e.dst_node, e.dst_port))

    for tick in range(n_ticks):
        t = tick * dt
        # Each node ticks once, in topo order.
        for nid in order:
            type_id = type_by_id.get(nid)
            tick_fn = TICK_FNS.get(type_id)
            if tick_fn is None:
                warnings.append(
                    f"no tick function for {type_id!r}, node {nid}"
                )
                continue
            # Collect inputs. Multiple edges can target one port; sum
            # them for signal/value shapes, OR them for events.
            inputs: dict[str, Any] = {}
            cat = expand.ALL_PORTS.get(type_id, {})
            in_ports = cat.get("inputs", {})
            for port, shape in in_ports.items():
                srcs = incoming.get((nid, port))
                if not srcs:
                    continue
                if shape == "event":
                    fired = False
                    for src in srcs:
                        v = last.get(src, False)
                        fired = fired or bool(v)
                    inputs[port] = fired
                else:
                    # signal or value: sum
                    s = 0.0
                    for src in srcs:
                        v = last.get(src, 0.0)
                        if isinstance(v, bool):
                            v = 1.0 if v else 0.0
                        try:
                            s += float(v)
                        except (TypeError, ValueError):
                            pass
                    inputs[port] = s
            # Compute new outputs.
            try:
                new_out = tick_fn(
                    params_by_id.get(nid, {}),
                    inputs, states[nid], dt, t,
                )
            except Exception as ex:
                warnings.append(f"tick error on {nid}: {ex}")
                new_out = {}
            # Stash for next tick (and probes).
            for out_port, val in new_out.items():
                last[(nid, out_port)] = val

        # Record probes. A probe on a node's input reads the summed
        # value the node would have seen this tick. A probe on a
        # node's output reads the value this node just computed.
        row: list[float] = [t]
        for (nid, port) in probes:
            type_id = type_by_id.get(nid)
            cat = expand.ALL_PORTS.get(type_id, {})
            if port in cat.get("outputs", {}):
                v = last.get((nid, port), 0.0)
            else:
                srcs = incoming.get((nid, port), [])
                s = 0.0
                for src in srcs:
                    sv = last.get(src, 0.0)
                    if isinstance(sv, bool):
                        sv = 1.0 if sv else 0.0
                    try:
                        s += float(sv)
                    except (TypeError, ValueError):
                        pass
                v = s
            if isinstance(v, bool):
                vf = 1.0 if v else 0.0
            else:
                try:
                    vf = float(v)
                except (TypeError, ValueError):
                    vf = 0.0
            stats[f"{nid}.{port}"].observe(vf)
            row.append(vf)
        csv_rows.append(row)

    return SimResult(
        rate_hz=rate_hz, duration_s=duration_s, ticks=n_ticks,
        probe_names=probe_names, csv_rows=csv_rows,
        stats=stats, warnings=warnings,
    )


# =====================================================================
# Output rendering
# =====================================================================


def render_summary(result: SimResult) -> str:
    """Format per-probe statistics and warnings as a human-readable summary string."""
    lines = []
    lines.append(
        f"# simulation: {result.ticks} ticks at {result.rate_hz} Hz "
        f"= {result.duration_s:.2f} s"
    )
    lines.append(f"# probes: {len(result.probe_names)}")
    if result.warnings:
        lines.append(f"# warnings: {len(result.warnings)}")
        for w in result.warnings[:8]:
            lines.append(f"# WARN  {w}")
        if len(result.warnings) > 8:
            lines.append(f"# ... ({len(result.warnings) - 8} more)")
    lines.append("")
    lines.append("per-probe statistics:")
    for name in result.probe_names:
        lines.append(result.stats[name].as_line())
    return "\n".join(lines) + "\n"


def render_trace(
    result: SimResult,
    max_lines: int | None = None,
) -> str:
    """Human-readable trace. One line per probe per tick.

    For long simulations, decimate or truncate via max_lines.
    """
    lines = []
    decimate = 1
    if max_lines is not None:
        total = result.ticks * len(result.probe_names)
        if total > max_lines:
            decimate = max(1, total // max_lines)
    counter = 0
    for row in result.csv_rows:
        t = row[0]
        for i, name in enumerate(result.probe_names):
            counter += 1
            if (counter - 1) % decimate != 0:
                continue
            v = row[i + 1]
            lines.append(f"t={t:>7.3f}  {name:<22}  {v:+.4f}")
    return "\n".join(lines) + "\n"


def render_csv(result: SimResult) -> str:
    """Render the full simulation trace as a CSV string (one row per tick)."""
    import io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["t_s"] + result.probe_names)
    for row in result.csv_rows:
        w.writerow([f"{row[0]:.6f}"] + [f"{v:.6f}" for v in row[1:]])
    return buf.getvalue()


# =====================================================================
# CLI
# =====================================================================


def main() -> int:
    """CLI entry point: parse arguments, run the simulation, and emit results."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("file", help="path to .spine file")
    ap.add_argument("--root", default="demo_root",
                    help="root GRP id (default: demo_root)")
    ap.add_argument("--duration", type=float, default=5.0,
                    help="simulation duration in seconds (default: 5.0)")
    ap.add_argument("--rate", type=float, default=100.0,
                    help="tick rate in Hz (default: 100)")
    ap.add_argument("--seed", type=int, default=42,
                    help="RNG seed for reproducible dice/noise (default: 42)")
    ap.add_argument("--probes", default=None,
                    help="comma-separated list of node[.port] probes "
                         "(default: auto-select scene_out inputs + LFO outs)")
    ap.add_argument("--csv", default=None,
                    help="write CSV trace to this file")
    ap.add_argument("--trace", default=None,
                    help="write human-readable trace to this file")
    ap.add_argument("--summary-only", action="store_true",
                    help="emit only the summary (no trace lines)")
    args = ap.parse_args()

    with open(args.file) as f:
        stmts = expand.parse(f.read())
    graph = expand.expand_patch(stmts, root=args.root)

    requested_probes = None
    if args.probes:
        requested_probes = [s.strip() for s in args.probes.split(",")]
    probe_tuples = select_probes(graph, requested_probes)

    result = simulate(
        graph,
        duration_s=args.duration, rate_hz=args.rate,
        seed=args.seed, probes=probe_tuples,
    )

    sys.stdout.write(render_summary(result))

    if args.csv:
        with open(args.csv, "w") as f:
            f.write(render_csv(result))
        sys.stderr.write(f"wrote CSV: {args.csv}\n")

    if args.trace:
        with open(args.trace, "w") as f:
            f.write(render_trace(result, max_lines=10000))
        sys.stderr.write(f"wrote trace: {args.trace}\n")

    if not args.summary_only and not args.trace:
        # Print decimated trace to stdout for quick inspection.
        sys.stdout.write("\n")
        sys.stdout.write(render_trace(result, max_lines=200))

    return 0


if __name__ == "__main__":
    sys.exit(main())
