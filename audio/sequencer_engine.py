"""Renders a Pattern's step sequence to a looping stereo audio buffer and
plays it back live, so the Steps tab's Play button gives an audible preview
of the pattern. Per-part Level/Pan/Pitch/EG Time/Start Point/Filter are all
taken into account, using the pattern's BPM (and Beat resolution) to time
the steps.

There's no official DSP spec for the ESX's own synthesis engine, so the
filter, envelope and pitch-shift math below are deliberately simple,
musically-reasonable approximations (log-scaled cutoff, resample-based
pitch shift, exponential decay envelope) rather than a bit-exact
reproduction of the hardware.
"""

import threading

import numpy as np

from esx import audio_dsp
from esx.constants import AmpEg, Beat, FilterType, StretchStep

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

ENGINE_SAMPLE_RATE = 44100

# Total addressable steps per part (16 bytes x 8 bits = 128, matching
# NUM_SEQUENCE_DATA_GATE/NOTE) - a bar/step combination that implies more
# steps than this simply has its excess steps carry no data, same as the
# Steps tab's own grid (ui/tab_patterns.py's STEP_DATA_CAPACITY).
STEP_DATA_CAPACITY = 128

# ~5ms at the engine rate - long enough to avoid an audible click when a
# Stretch retrigger truncates the still-sounding previous voice, short
# enough not to blur into the next trigger's own onset.
RETRIGGER_FADE_SAMPLES = int(0.005 * ENGINE_SAMPLE_RATE)

# How many sequencer steps make up one quarter-note beat, per the pattern's
# "Beat" resolution setting - not documented in any official ESX spec, so
# this follows the conventional drum-machine meaning of each option's name
# (a 16th-note step grid has 4 steps/beat, a 16th-note *triplet* grid fits
# 6 in the same beat, etc).
BEAT_STEPS_PER_BEAT = {
    Beat.BEAT_16TH: 4,
    Beat.BEAT_32ND: 8,
    Beat.BEAT_8TRI: 3,
    Beat.BEAT_16TRI: 6,
}


def _iter_playable_parts(pattern):
    """Yields (part, bit, kind) for every part that has a sample to trigger.
    kind is "bits" (1 bit/step in sequence_data, drum parts), "gate" (1
    byte/step in sequence_data_gate + a note number in sequence_data_note,
    keyboard parts) or "stretch" (1 bit/step in sequence_data, drum-style
    retrigger per active step, but each trigger plays the sample's own
    Fit-To-Tempo-stretched render instead of render_voice's plain pitch
    shift - see render_stretch_voice). Bit order mirrors
    pattern.mute_status's layout, i.e. ui/tab_patterns.py's
    TabPatterns._build_step_rows. Accent and Audio In have no sample_pointer
    of their own, so they're not playable voices."""
    bit = 0
    for part in pattern.drum_parts:
        yield part, bit, "bits"
        bit += 1
    bit += 1  # Accent
    for part in pattern.keyboard_parts:
        yield part, bit, "gate"
        bit += 1
    for part in pattern.stretch_slice_parts:
        yield part, bit, "stretch"
        bit += 1


def _get_step_state(part, kind, step):
    if kind == "gate":
        gate_data = part.sequence_data_gate.data
        if step >= len(gate_data) or gate_data[step] == 0:
            return False
        # The gate byte alone doesn't distinguish an active step from one
        # that's been switched off - real ESX files leave it at whatever
        # non-zero value it had the first time the step was touched, and
        # instead flag "off" via the note byte's bit 7 (e.g. a C4/60 step
        # that's off is stored as note 60|0x80=188), so the hardware still
        # remembers the pitch if the step is switched back on. See
        # ui/tab_patterns.py's TabPatterns._get_step_state (same encoding).
        note_data = part.sequence_data_note.data
        return step >= len(note_data) or note_data[step] < 0x80
    # "bits" (drum) and "stretch" both use the same 1-bit/step encoding.
    data = part.sequence_data.data
    byte_i, bit_i = divmod(step, 8)
    return byte_i < len(data) and bool(data[byte_i] & (1 << bit_i))


def _get_step_note(part, step):
    data = part.sequence_data_note.data
    # Bit 7 is the gate-kind steps' own off flag (see _get_step_state) -
    # mask it off so a step that's off-but-remembers-its-pitch still
    # yields a playable 0-127 MIDI note rather than an out-of-range byte.
    return (data[step] & 0x7F) if step < len(data) else 60


def _cutoff_to_hz(cutoff: int) -> float:
    """cutoff is a signed byte (-128..127); mapped log-scale across the
    audible range since the hardware's own filter response curve isn't
    documented."""
    norm = (cutoff + 128) / 255.0
    norm = min(max(norm, 0.0), 1.0)
    return 20.0 * (20000.0 / 20.0) ** norm


def _resonance_to_q(resonance: int) -> float:
    norm = min(max(resonance, 0), 127) / 127.0
    return 0.5 + norm * 9.5


# Pitch is stored as an unsigned byte (0-127) centered at 64 - confirmed by
# a blank/default pattern carrying pitch=64 (and pan=64, see _pan_gains) on
# every part, i.e. dead center, never the 0 a signed -64..63 reading would
# imply. The raw range mapped 1:1 to semitones would be +/-64 semitones
# (5+ octaves) at the extremes, clearly implausible for a sample pitch
# knob, so it's scaled down to a musically sane +/-2 octaves instead.
PITCH_SEMITONE_RANGE = 24.0


def _pitch_to_semitones(raw_pitch: int) -> float:
    centered = max(0, min(127, raw_pitch)) - 64
    return centered * (PITCH_SEMITONE_RANGE / 64.0)


def _apply_filter(mono: np.ndarray, part, sample_rate: int) -> np.ndarray:
    filter_type = int(part.filter_type)
    if filter_type == int(FilterType.LPF):
        band_type = "low_pass"
        gain_db = 0.0
    elif filter_type == int(FilterType.HPF):
        band_type = "high_pass"
        gain_db = 0.0
    else:
        band_type = "peak"  # BPF / BPF_PLUS approximated as a resonant peak
        gain_db = 9.0
    band = audio_dsp.EQBand(type=band_type, freq=_cutoff_to_hz(part.cutoff),
                             gain_db=gain_db, q=_resonance_to_q(part.resonance))
    processed, = audio_dsp.apply_eq([mono], sample_rate, [band])
    return processed


def _resample(mono: np.ndarray, ratio: float) -> np.ndarray:
    """ratio = output_len / input_len."""
    if len(mono) < 2 or abs(ratio - 1.0) < 1e-6:
        return mono
    out_len = max(1, int(round(len(mono) * ratio)))
    src_idx = np.linspace(0, len(mono) - 1, out_len)
    return np.interp(src_idx, np.arange(len(mono)), mono)


def _apply_envelope(mono: np.ndarray, part, sample_rate: int) -> np.ndarray:
    """AmpEg.GATE plays the sample at full level for its own natural length;
    AmpEg.EG applies an exponential decay whose length follows eg_time -
    eg_time has no published time-curve, so this uses a 30ms-2s range that
    reads as musically usable short-to-long."""
    if len(mono) == 0 or int(getattr(part, "amp_eg", AmpEg.GATE)) != int(AmpEg.EG):
        return mono
    decay_seconds = 0.03 + (max(0, min(127, part.eg_time)) / 127.0) * 2.0
    decay_samples = max(1, int(decay_seconds * sample_rate))
    cutoff_len = min(len(mono), decay_samples * 6)
    mono = mono[:cutoff_len]
    envelope = np.exp(-np.arange(cutoff_len, dtype=np.float64) / decay_samples)
    return mono * envelope


def _pan_gains(pan: int):
    """pan is stored the same way as pitch - an unsigned byte (0-127)
    centered at 64, not the signed -64..63 range some other fields use."""
    norm = (max(0, min(127, pan)) - 64) / 64.0
    theta = (norm + 1.0) * (np.pi / 4.0)
    return float(np.cos(theta)), float(np.sin(theta))


def _sample_source_mono(sample) -> np.ndarray:
    ch1 = audio_dsp.be16_to_float(sample.audio_data_ch1)
    ch2 = audio_dsp.be16_to_float(sample.audio_data_ch2) if sample.audio_data_ch2 else ch1
    n = min(len(ch1), len(ch2)) if len(ch2) else len(ch1)
    if n == 0:
        return np.zeros(0, dtype=np.float64)
    if len(ch2) == len(ch1) and len(ch2) == n:
        return (ch1[:n] + ch2[:n]) / 2.0
    return ch1[:n]


def render_voice(sample, part, sample_rate: int, note=None) -> np.ndarray:
    """Renders one part's sample for a single step trigger: start point
    trim, pitch shift, filter, envelope, level and pan. Returns an (n, 2)
    float64 stereo array at `sample_rate`."""
    mono = _sample_source_mono(sample)
    if len(mono) == 0:
        return np.zeros((0, 2), dtype=np.float64)

    start_frac = max(0, min(127, getattr(part, "start_point", 0))) / 127.0
    start_idx = int(start_frac * len(mono))
    mono = mono[start_idx:]
    if len(mono) == 0:
        return np.zeros((0, 2), dtype=np.float64)

    src_rate = sample.sample_rate if sample.sample_rate > 0 else sample_rate
    semitones = (note - 60) if note is not None else _pitch_to_semitones(getattr(part, "pitch", 64))
    speed_ratio = (2.0 ** (-semitones / 12.0)) * (sample_rate / src_rate)
    mono = _resample(mono, speed_ratio)

    if hasattr(part, "cutoff"):
        mono = _apply_filter(mono, part, sample_rate)
    mono = _apply_envelope(mono, part, sample_rate)

    level = getattr(part, "level", 127) / 127.0
    left_gain, right_gain = _pan_gains(getattr(part, "pan", 64))
    return np.stack([mono * level * left_gain, mono * level * right_gain], axis=1)


def _time_stretch(mono: np.ndarray, out_len: int) -> np.ndarray:
    """Pitch-preserving time-stretch/compress to an exact output length via
    WSOLA (Waveform-Similarity Overlap-Add): analysis frames are copied
    into the output verbatim (so their own internal frequency content -
    the perceived pitch - is unchanged) and simply *resequenced* in time by
    reading them at a different rate than they're written out. Each frame's
    read position is nudged, within a small search window, to whichever
    offset best matches the tail of the previous frame's overlap region -
    without that alignment step (plain fixed-hop OLA), unrelated frames get
    overlapped and destructively cancel various frequencies against each
    other, which sounds like a (undesired) filter smeared over the result.
    Naively resampling instead of stretching (changing playback speed)
    would change duration and pitch together, which is exactly what a
    genuine Stretch part must avoid."""
    in_len = len(mono)
    if out_len <= 0:
        return np.zeros(0, dtype=np.float64)
    if in_len < 2:
        return np.zeros(out_len, dtype=np.float64)

    alpha = out_len / in_len
    # Never larger than the input itself - a frame_len forced above in_len
    # would zero-pad every frame past the real content, collapsing the
    # whole stretch down to one short, heavily-windowed (and so falsely
    # low-sounding) burst followed by silence.
    frame_len = max(8, min(4096, in_len))
    synthesis_hop = max(1, frame_len // 4)
    analysis_hop = synthesis_hop / alpha
    overlap_len = max(1, frame_len - synthesis_hop)
    # How far from the "ideal" (fixed-ratio) read position WSOLA is allowed
    # to search for a better-matching frame - wide enough to actually find
    # a good match, narrow enough to stay close to the intended timing.
    tolerance = max(1, min(synthesis_hop // 2, in_len // 2, 512))
    window = np.hanning(frame_len)

    out = np.zeros(out_len + frame_len, dtype=np.float64)
    norm = np.zeros(out_len + frame_len, dtype=np.float64)
    max_start = max(0, in_len - frame_len)

    def read_frame(pos):
        end = pos + frame_len
        if pos >= in_len:
            return np.zeros(frame_len, dtype=np.float64)
        if end > in_len:
            frame = np.zeros(frame_len, dtype=np.float64)
            frame[:in_len - pos] = mono[pos:in_len]
            return frame
        return mono[pos:end]

    ideal_read_pos = 0.0
    write_pos = 0
    prev_tail = None
    while write_pos < out_len:
        target = int(round(ideal_read_pos))
        read_pos = min(max(target, 0), max_start)
        if prev_tail is not None and tolerance > 0:
            lo = min(max(target - tolerance, 0), max_start)
            hi = min(max(target + tolerance, 0), max_start)
            if hi > lo:
                ov = min(overlap_len, len(prev_tail), in_len - lo)
                if ov > 0:
                    candidates = mono[lo:hi + ov]
                    if len(candidates) >= ov:
                        windows = np.lib.stride_tricks.sliding_window_view(candidates, ov)
                        scores = windows @ prev_tail[:ov]
                        read_pos = lo + int(np.argmax(scores))

        frame = read_frame(read_pos)
        out[write_pos:write_pos + frame_len] += frame * window
        norm[write_pos:write_pos + frame_len] += window
        prev_tail = frame[synthesis_hop:synthesis_hop + overlap_len]
        ideal_read_pos += analysis_hop
        write_pos += synthesis_hop

    norm[norm < 1e-8] = 1.0
    return (out / norm)[:out_len]


def render_stretch_voice(sample, part, sample_rate: int, samples_per_step: int):
    """Renders one trigger of a Stretch part: "Fit To Tempo" (per the
    sample's own Sample.stretch_step tag - how many steps its content is
    meant to span), then start point trim, filter, envelope, level and pan,
    same as render_voice. Unlike a normal Sample part, changing tempo here
    changes the sample's *duration* while keeping its pitch roughly where
    it started - Fit To Tempo stretches/compresses the sample so that many
    steps take exactly as long at the pattern's current tempo as they did
    at the sample's own native tempo. A sample with stretch_step OFF (no
    tag) has nothing to fit to, so it just plays back at its native length
    like a normal one-shot. Each active step re-triggers this same render
    independently (see render_pattern's step loop), so it retriggers
    exactly like a drum hit rather than only sounding once per pattern.
    Returns an (n, 2) float64 stereo array, or None if the sample/part has
    nothing to render."""
    mono = _sample_source_mono(sample)
    if len(mono) == 0:
        return None

    start_frac = max(0, min(127, getattr(part, "start_point", 0))) / 127.0
    start_idx = int(start_frac * len(mono))
    mono = mono[start_idx:]
    if len(mono) == 0:
        return None

    # Normalize the sample's own recorded rate to the engine's playback
    # rate *before* stretching - skipping this left the stretch operating
    # on a waveform whose cycles were already the wrong length, which for
    # a sample recorded well below the engine rate (e.g. 22050 Hz content
    # played as if it were 44100 Hz) came out roughly an octave too low.
    src_rate = sample.sample_rate if sample.sample_rate > 0 else sample_rate
    if src_rate != sample_rate and len(mono) > 1:
        mono = _resample(mono, sample_rate / src_rate)

    stretch_step = getattr(sample, "stretch_step", StretchStep.OFF)
    target_len = None
    if int(stretch_step) >= 0 and len(mono) > 1:
        native_steps = int(stretch_step) + 1
        target_len = native_steps * samples_per_step
        mono = _time_stretch(mono, target_len)

    # The Pitch knob still works as a musical pitch control, applied as a
    # resample (which shifts pitch and duration together) immediately
    # undone by a second time-stretch back to target_len - the classic
    # resample-then-restretch trick for shifting pitch independently of
    # duration. Without a stretch_step tag there's no fixed length to
    # restretch back to, so the pitch shift is left as a plain resample.
    semitones = _pitch_to_semitones(getattr(part, "pitch", 64))
    if abs(semitones) > 1e-6 and len(mono) > 1:
        pitch_ratio = 2.0 ** (-semitones / 12.0)
        mono = _resample(mono, pitch_ratio)
        if target_len is not None:
            mono = _time_stretch(mono, target_len)

    if hasattr(part, "cutoff"):
        mono = _apply_filter(mono, part, sample_rate)

    mono = _apply_envelope(mono, part, sample_rate)

    level = getattr(part, "level", 127) / 127.0
    left_gain, right_gain = _pan_gains(getattr(part, "pan", 64))
    return np.stack([mono * level * left_gain, mono * level * right_gain], axis=1)


def _render_monophonic(voice, steps, samples_per_step, loop_len):
    """A Stretch part plays one voice at a time, so a retrigger cuts off
    whatever's still sounding from the previous one instead of layering
    underneath it - each trigger's tail is truncated at the next trigger's
    offset (or the loop end for the last one), with a short fade to avoid a
    click at the cut."""
    buf = np.zeros((loop_len, 2), dtype=np.float64)
    for i, step in enumerate(steps):
        offset = step * samples_per_step
        next_offset = steps[i + 1] * samples_per_step if i + 1 < len(steps) else loop_len
        natural_end = offset + len(voice)
        end = min(loop_len, next_offset, natural_end)
        if end <= offset:
            continue
        segment = voice[:end - offset].copy()
        if end < natural_end:
            fade_len = min(RETRIGGER_FADE_SAMPLES, len(segment))
            if fade_len > 0:
                segment[-fade_len:] *= np.linspace(1.0, 0.0, fade_len)[:, None]
        buf[offset:end] = segment
    return buf


def _render_additive(part, kind, sample, sample_rate, steps, samples_per_step, loop_len):
    buf = np.zeros((loop_len, 2), dtype=np.float64)
    for step in steps:
        note = _get_step_note(part, step) if kind == "gate" else None
        voice = render_voice(sample, part, sample_rate, note=note)
        if len(voice) == 0:
            continue
        offset = step * samples_per_step
        end = min(loop_len, offset + len(voice))
        if end > offset:
            buf[offset:end] += voice[:end - offset]
    return buf


def _stretch_voice_cache_key(part, sample, samples_per_step):
    """Every field render_stretch_voice's output actually depends on -
    mute/solo and step (on/off) edits touch none of these, so keying a
    cache on this tuple lets update_buffer_async skip WSOLA entirely for
    Stretch parts that weren't the thing being edited."""
    return (
        id(sample), id(part), samples_per_step,
        int(getattr(sample, "stretch_step", -1)),
        int(getattr(part, "start_point", 0)),
        int(getattr(part, "pitch", 64)),
        int(getattr(part, "cutoff", 0)),
        int(getattr(part, "resonance", 0)),
        int(getattr(part, "filter_type", 0)),
        int(getattr(part, "amp_eg", 0)),
        int(getattr(part, "eg_time", 0)),
        int(getattr(part, "level", 127)),
        int(getattr(part, "pan", 64)),
    )


def _render_parts(pattern, samples, sample_rate: int = ENGINE_SAMPLE_RATE, voice_cache=None):
    """Computes the full (ungated) pattern mix once, along with enough
    per-part state to cheaply re-apply an unmute gate afterwards (see
    apply_mute_gate) without redoing the expensive part: a Stretch part's
    WSOLA render (render_stretch_voice) can take the better part of a
    second, and it's identical regardless of which steps end up gated, so
    it's computed here exactly once and the resulting `voice` array is
    handed back for re-use.

    voice_cache is an optional {cache_key: voice} dict, mutated in place,
    that SequencerPlaybackEngine keeps alive across update_buffer_async
    calls for the lifetime of a Play session: a mute/step edit never
    changes what a Stretch part itself sounds like, only which steps
    trigger it, so re-running that part's WSOLA on every single edit -
    the whole pattern's worth, every time - was making every mute/step
    toggle audibly laggy whenever the pattern had a Stretch part at all,
    independent of the fix to how stale the gate position was. Omit (or
    pass a fresh dict) for a one-shot render with no reuse across calls.
    Returns (mix, seconds_per_step, total_steps, samples_per_step,
    loop_len, part_specs)."""
    if voice_cache is None:
        voice_cache = {}
    num_bars = int(pattern.pattern_length) + 1
    steps_per_bar = int(pattern.last_step) + 1
    total_steps = num_bars * steps_per_bar

    steps_per_beat = BEAT_STEPS_PER_BEAT.get(pattern.beat, 4)
    bpm = max(1.0, pattern.tempo.value)
    seconds_per_step = 60.0 / bpm / steps_per_beat
    samples_per_step = max(1, int(round(seconds_per_step * sample_rate)))
    loop_len = total_steps * samples_per_step

    mix = np.zeros((loop_len, 2), dtype=np.float64)
    part_specs = []

    for part, bit, kind in _iter_playable_parts(pattern):
        if pattern.mute_status & (1 << bit):
            continue
        sample_pointer = getattr(part, "sample_pointer", -1)
        if sample_pointer is None or not (0 <= sample_pointer < len(samples)):
            continue
        sample = samples[sample_pointer]
        if sample.is_empty():
            continue

        active_steps = [
            s for s in range(min(total_steps, STEP_DATA_CAPACITY))
            if _get_step_state(part, kind, s)
        ]
        if not active_steps:
            continue

        if kind == "stretch":
            # A Stretch part's Fit-To-Tempo render is identical on every
            # trigger (it doesn't depend on which step it lands on, unlike
            # a keyboard part's per-step note), so it's rendered once and
            # reused for every active step instead of redoing the same
            # stretch again per trigger - and cached across calls (see
            # voice_cache above) since it's also identical across mute/step
            # edits that don't touch this part at all.
            cache_key = _stretch_voice_cache_key(part, sample, samples_per_step)
            if cache_key in voice_cache:
                voice = voice_cache[cache_key]
            else:
                voice = render_stretch_voice(sample, part, sample_rate, samples_per_step)
                voice_cache[cache_key] = voice
            if voice is None or len(voice) == 0:
                continue
            part_buf = _render_monophonic(voice, active_steps, samples_per_step, loop_len)
        else:
            voice = None
            part_buf = _render_additive(part, kind, sample, sample_rate, active_steps, samples_per_step, loop_len)

        mix += part_buf
        part_specs.append({
            "bit": bit, "kind": kind, "part": part, "sample": sample,
            "voice": voice, "active_steps": active_steps,
        })

    return mix, seconds_per_step, total_steps, samples_per_step, loop_len, part_specs


def apply_mute_gate(mix, part_specs, sample_rate, samples_per_step, loop_len, mute_gate):
    """Cheaply rebuilds just the [gate_from:] tail of each gated part's
    contribution to `mix`, using only its steps at/after gate_from, so a
    trigger that's already "in the past" relative to gate_from can't bleed
    its still-sounding tail into the still-upcoming part of this one pass
    (which would sound like an already-in-progress note suddenly
    resuming). The region before gate_from is left untouched (still the
    full, all-triggers render), so those same steps sound normally again
    as soon as the loop wraps back around to them.

    Deliberately kept separate from the (potentially slow, WSOLA-heavy)
    _render_parts: gate_from is a live playback position that keeps moving
    while _render_parts runs, so it must be sampled as close as possible to
    when the result actually gets swapped into the playing buffer - not
    before a render that can itself take the better part of a second,
    which would make gate_from stale by the time it's applied and cause
    the gated part to miss whatever trigger fell in that gap (only
    catching its next one instead, e.g. at the start of the next bar).
    Recomputing each gated part's contribution here is cheap: for a
    Stretch part it reuses the `voice` array _render_parts already paid
    the WSOLA cost for, and render_voice for drum/keyboard parts was never
    expensive to begin with."""
    if not mute_gate:
        return mix
    result = mix.copy()
    for spec in part_specs:
        gate_from = mute_gate.get(spec["bit"])
        if gate_from is None or gate_from >= loop_len:
            continue
        active_steps = spec["active_steps"]
        future_steps = [s for s in active_steps if s * samples_per_step >= gate_from]
        if spec["kind"] == "stretch":
            full_buf = _render_monophonic(spec["voice"], active_steps, samples_per_step, loop_len)
            future_buf = _render_monophonic(spec["voice"], future_steps, samples_per_step, loop_len)
        else:
            full_buf = _render_additive(
                spec["part"], spec["kind"], spec["sample"], sample_rate, active_steps, samples_per_step, loop_len
            )
            future_buf = _render_additive(
                spec["part"], spec["kind"], spec["sample"], sample_rate, future_steps, samples_per_step, loop_len
            )
        result[gate_from:] += future_buf[gate_from:] - full_buf[gate_from:]
    return result


def render_pattern(pattern, samples, sample_rate: int = ENGINE_SAMPLE_RATE, mute_gate=None):
    """Mixes every active step of every unmuted part into one loop-length
    stereo float32 buffer. Voice tails that run past the loop boundary are
    truncated rather than wrapped - acceptable for the short, mostly
    percussive one-shots the ESX plays.

    mute_gate is an optional {bit: min_offset} map - see apply_mute_gate.
    For a one-shot render (no live playback position to go stale), this
    convenience wrapper is fine; SequencerPlaybackEngine.update_buffer_async
    calls _render_parts/apply_mute_gate directly instead, so it can sample
    gate_from right before the swap rather than before the render. Returns
    (buffer, seconds_per_step, total_steps)."""
    mix, seconds_per_step, total_steps, samples_per_step, loop_len, part_specs = _render_parts(
        pattern, samples, sample_rate
    )
    if mute_gate:
        mix = apply_mute_gate(mix, part_specs, sample_rate, samples_per_step, loop_len, mute_gate)

    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak > 1.0:
        mix = mix / peak

    return mix.astype(np.float32), seconds_per_step, total_steps


class SequencerPlaybackEngine:
    """Loops a precomputed pattern buffer through a persistent sounddevice
    output stream - a singleton (like audio.audio_player.AudioPlayer) so
    starting the sequencer implicitly stops any other playback in the app
    from fighting over the output device."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._stream = None
        self._buffer = np.zeros((0, 2), dtype=np.float32)
        self._pos = 0
        self._playing = False
        self._paused = False
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._buffer_lock = threading.Lock()
        self._samples_per_step = 0
        self._total_steps = 0
        self._last_mute_status = None
        # Guards update_buffer_async: renders (WSOLA in particular can take
        # a second or more) run on a background thread so mute/step edits
        # don't freeze the UI, and this generation counter lets a slower,
        # now-stale render notice a newer one already landed and discard
        # its own result instead of clobbering it.
        self._render_lock = threading.Lock()
        self._render_generation = 0
        # Caches each Stretch part's rendered (WSOLA-stretched) voice audio
        # across update_buffer_async calls for the lifetime of a Play
        # session - a mute/step edit never changes what a Stretch part
        # itself sounds like, only which steps trigger it, so without this
        # every single edit would re-run WSOLA for the whole pattern from
        # scratch. Reset whenever playback (re)starts, since the pattern or
        # samples backing it may have changed entirely.
        self._voice_cache = {}

    def play(self, pattern, samples, sample_rate: int = ENGINE_SAMPLE_RATE) -> bool:
        if not SOUNDDEVICE_AVAILABLE:
            return False
        self._voice_cache = {}
        mix, seconds_per_step, total_steps, _samples_per_step, _loop_len, _part_specs = _render_parts(
            pattern, samples, sample_rate, voice_cache=self._voice_cache
        )
        peak = float(np.max(np.abs(mix))) if mix.size else 0.0
        if peak > 1.0:
            mix = mix / peak
        buffer = mix.astype(np.float32)
        self.stop()
        if len(buffer) == 0:
            return False

        with self._buffer_lock:
            self._buffer = buffer
            self._pos = 0
            self._samples_per_step = max(1, int(round(seconds_per_step * sample_rate)))
            self._total_steps = total_steps
        self._last_mute_status = pattern.mute_status
        self._paused = False
        self._pause_event.set()

        def callback(outdata, frames, time_info, status):
            if not self._pause_event.is_set():
                outdata[:] = 0
                return
            with self._buffer_lock:
                buf = self._buffer
                n = len(buf)
                if n == 0:
                    outdata[:] = 0
                    return
                pos = self._pos
                remaining = frames
                out_idx = 0
                while remaining > 0:
                    chunk = min(remaining, n - pos)
                    outdata[out_idx:out_idx + chunk] = buf[pos:pos + chunk]
                    pos = (pos + chunk) % n
                    out_idx += chunk
                    remaining -= chunk
                self._pos = pos

        try:
            self._stream = sd.OutputStream(samplerate=sample_rate, channels=2, callback=callback)
            self._stream.start()
        except Exception:
            self._stream = None
            return False

        self._playing = True
        return True

    def update_buffer_async(self, pattern, samples, sample_rate: int = ENGINE_SAMPLE_RATE) -> bool:
        """Re-renders and hot-swaps the loop buffer without stopping the
        stream, so mute/solo/step edits are heard immediately while the
        sequencer keeps running instead of only on the next Play press. The
        (potentially slow, WSOLA-heavy) render itself happens on a
        background thread instead of blocking the caller - meant for UI
        code that calls this on every mute/solo/step edit, where a
        synchronous render would freeze the UI thread for its duration.

        The unmute gate's reference position is deliberately sampled AFTER
        the render finishes, not before it starts: playback keeps advancing
        the whole time the render runs, so a position captured up front
        would be stale by the time the buffer is swapped in, making a
        just-unmuted part miss whatever trigger fell in that gap and only
        catch its next one (e.g. the start of the next bar) instead of the
        very next one. apply_mute_gate is cheap (it reuses the voice audio
        _render_parts already computed) so re-sampling the position and
        applying the gate right before the swap costs only milliseconds."""
        if not self._playing:
            return False
        new_mute_status = pattern.mute_status
        # Captured now, not re-read inside the worker: play() replaces
        # self._voice_cache with a fresh dict on every (re)start, and a
        # worker dispatched by a since-superseded session must keep using
        # the cache it started with rather than picking up whatever
        # self._voice_cache happens to point to by the time it finishes.
        voice_cache = self._voice_cache

        with self._render_lock:
            self._render_generation += 1
            generation = self._render_generation

        def worker():
            mix, seconds_per_step, total_steps, samples_per_step, loop_len, part_specs = _render_parts(
                pattern, samples, sample_rate, voice_cache=voice_cache
            )
            with self._render_lock:
                if generation != self._render_generation or not self._playing:
                    return
                with self._buffer_lock:
                    pos = self._pos % loop_len if loop_len else 0

                mute_gate = None
                if self._last_mute_status is not None:
                    newly_unmuted = self._last_mute_status & ~new_mute_status
                    if newly_unmuted:
                        mute_gate = {bit: pos for bit in range(16) if newly_unmuted & (1 << bit)}
                if mute_gate:
                    mix = apply_mute_gate(mix, part_specs, sample_rate, samples_per_step, loop_len, mute_gate)

                peak = float(np.max(np.abs(mix))) if mix.size else 0.0
                if peak > 1.0:
                    mix = mix / peak
                buffer = mix.astype(np.float32)

                with self._buffer_lock:
                    self._buffer = buffer
                    self._pos = pos if len(buffer) else 0
                    self._samples_per_step = samples_per_step
                    self._total_steps = total_steps
                self._last_mute_status = new_mute_status

        threading.Thread(target=worker, daemon=True).start()
        return True

    def pause(self):
        if self._playing:
            self._paused = True
            self._pause_event.clear()

    def stop(self):
        self._playing = False
        self._paused = False
        self._pause_event.set()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def is_playing(self) -> bool:
        return self._playing and not self._paused

    def is_paused(self) -> bool:
        return self._playing and self._paused

    def get_playback_step(self):
        """Returns the current 0-based step index within the loop (for
        driving a UI playhead animation), or None if nothing is loaded.
        Still returns a (frozen) position while paused, so the playhead
        stays put instead of disappearing."""
        with self._buffer_lock:
            if not self._playing or self._samples_per_step <= 0 or self._total_steps <= 0:
                return None
            return (self._pos // self._samples_per_step) % self._total_steps
