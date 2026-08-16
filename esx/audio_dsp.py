"""Sample-editing DSP: peak/loudness normalization, trim/cut, and a
parametric EQ. Operates on float64 arrays in the [-1, 1] range; callers
convert to/from the big-endian int16 PCM bytes used by Sample.audio_data_ch1/ch2.
"""

import io
import math
import struct
import wave
from dataclasses import dataclass

import numpy as np
from scipy.signal import lfilter, freqz

EQ_BAND_TYPES = ("peak", "low_shelf", "high_shelf", "low_pass", "high_pass")


def be16_to_float(data: bytes) -> np.ndarray:
    if not data:
        return np.zeros(0, dtype=np.float64)
    return np.frombuffer(data, dtype='>i2').astype(np.float64) / 32768.0


def float_to_be16(arr: np.ndarray) -> bytes:
    clipped = np.clip(arr, -1.0, 1.0)
    ints = np.round(clipped * 32767.0).astype('>i2')
    return ints.tobytes()


def pcm_be16_to_wav_bytes(pcm: bytes, sample_rate: int) -> bytes:
    """Wrap raw big-endian mono int16 PCM in a little-endian mono WAV
    container, for feeding transient (non-committed) previews to AudioPlayer."""
    if not pcm:
        return bytes()
    num_frames = len(pcm) // 2
    le_data = bytearray(len(pcm))
    for i in range(num_frames):
        val = struct.unpack_from('>h', pcm, i * 2)[0]
        struct.pack_into('<h', le_data, i * 2, val)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate if sample_rate > 0 else 44100)
        w.writeframes(bytes(le_data))
    return buf.getvalue()


# --------------------------------------------------------------------------
# Peak normalization
# --------------------------------------------------------------------------

def peak_amplitude(channels: list[np.ndarray]) -> float:
    peak = 0.0
    for ch in channels:
        if len(ch):
            peak = max(peak, float(np.max(np.abs(ch))))
    return peak


def normalize_peak(channels: list[np.ndarray], target_db: float = -0.1):
    """Scale all channels by a common gain so the loudest sample hits
    target_db dBFS. Returns (new_channels, applied_gain_db, had_signal)."""
    peak = peak_amplitude(channels)
    if peak <= 1e-9:
        return channels, 0.0, False
    target_amp = 10.0 ** (target_db / 20.0)
    gain = target_amp / peak
    gain_db = 20.0 * math.log10(gain) if gain > 0 else 0.0
    return [ch * gain for ch in channels], gain_db, True


# --------------------------------------------------------------------------
# Integrated loudness (ITU-R BS.1770 K-weighting), approximate.
#
# This implements the two-stage K-weighting filter and the -0.691 LUFS
# offset from BS.1770, but measures mean square over the whole signal
# rather than the standard's 400ms/75%-overlap blocks with absolute
# (-70 LUFS) and relative (-10 LU) gating. That block-gating scheme exists
# to stop long silences in broadcast program material from skewing the
# result; for short one-shot samples (drums, stabs, loops) it makes very
# little practical difference, so it's skipped to keep this fast and simple.
# --------------------------------------------------------------------------

def _high_shelf_k_coeffs(sample_rate: float):
    f0 = 1681.9744509555319
    g = 3.99984385397
    q = 0.7071752369554193
    k = math.tan(math.pi * f0 / sample_rate)
    vh = 10.0 ** (g / 20.0)
    vb = vh ** 0.4996667741545416
    a0 = 1.0 + k / q + k * k
    b0 = (vh + vb * k / q + k * k) / a0
    b1 = 2.0 * (k * k - vh) / a0
    b2 = (vh - vb * k / q + k * k) / a0
    a1 = 2.0 * (k * k - 1.0) / a0
    a2 = (1.0 - k / q + k * k) / a0
    return np.array([b0, b1, b2]), np.array([1.0, a1, a2])


def _high_pass_rlb_coeffs(sample_rate: float):
    f0 = 38.13547087613982
    q = 0.5003270373238773
    k = math.tan(math.pi * f0 / sample_rate)
    a0 = 1.0 + k / q + k * k
    a1 = 2.0 * (k * k - 1.0) / a0
    a2 = (1.0 - k / q + k * k) / a0
    return np.array([1.0, -2.0, 1.0]), np.array([1.0, a1, a2])


def _k_weight(arr: np.ndarray, sample_rate: float) -> np.ndarray:
    b1, a1 = _high_shelf_k_coeffs(sample_rate)
    b2, a2 = _high_pass_rlb_coeffs(sample_rate)
    return lfilter(b2, a2, lfilter(b1, a1, arr))


def measure_lufs(channels: list[np.ndarray], sample_rate: int) -> float:
    """Approximate integrated loudness in LUFS. Returns -inf for silence."""
    channels = [ch for ch in channels if len(ch)]
    if not channels or sample_rate <= 0:
        return float('-inf')

    total_mean_square = 0.0
    for ch in channels:
        weighted = _k_weight(ch, float(sample_rate))
        total_mean_square += float(np.mean(weighted ** 2))

    if total_mean_square <= 1e-12:
        return float('-inf')
    return -0.691 + 10.0 * math.log10(total_mean_square)


def normalize_loudness(channels: list[np.ndarray], sample_rate: int, target_lufs: float = -14.0):
    """Returns (new_channels, measured_before_lufs, applied_gain_db, clipped)."""
    measured = measure_lufs(channels, sample_rate)
    if measured == float('-inf'):
        return channels, measured, 0.0, False

    gain_db = target_lufs - measured
    gain = 10.0 ** (gain_db / 20.0)
    new_channels = [ch * gain for ch in channels]

    peak = peak_amplitude(new_channels)
    clipped = peak > 1.0
    if clipped:
        scale_down = 1.0 / peak
        new_channels = [ch * scale_down for ch in new_channels]
        gain_db += 20.0 * math.log10(scale_down)

    return new_channels, measured, gain_db, clipped


# --------------------------------------------------------------------------
# Trim / Cut
# --------------------------------------------------------------------------

def trim(arr: np.ndarray, start: int, end: int) -> np.ndarray:
    """Keep only the inclusive [start, end] frame range."""
    n = len(arr)
    start = max(0, min(start, n))
    end = max(start, min(end + 1, n))
    return arr[start:end].copy()


def cut_range(arr: np.ndarray, start: int, end: int) -> np.ndarray:
    """Remove the inclusive [start, end] frame range, splicing the rest together."""
    n = len(arr)
    start = max(0, min(start, n))
    end = max(start, min(end + 1, n))
    return np.concatenate([arr[:start], arr[end:]])


# --------------------------------------------------------------------------
# Parametric EQ (RBJ biquad cookbook)
# --------------------------------------------------------------------------

@dataclass
class EQBand:
    type: str = "peak"
    freq: float = 1000.0
    gain_db: float = 0.0
    q: float = 0.707
    enabled: bool = True


def design_band(band: EQBand, sample_rate: float):
    fs = float(sample_rate)
    f0 = min(max(float(band.freq), 1.0), fs / 2.0 - 1.0)
    q = max(float(band.q), 0.05)
    a = 10.0 ** (band.gain_db / 40.0)
    w0 = 2.0 * math.pi * f0 / fs
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    alpha = sin_w0 / (2.0 * q)

    if band.type == "low_shelf":
        sqrt_a = math.sqrt(a)
        b0 = a * ((a + 1) - (a - 1) * cos_w0 + 2 * sqrt_a * alpha)
        b1 = 2 * a * ((a - 1) - (a + 1) * cos_w0)
        b2 = a * ((a + 1) - (a - 1) * cos_w0 - 2 * sqrt_a * alpha)
        a0 = (a + 1) + (a - 1) * cos_w0 + 2 * sqrt_a * alpha
        a1 = -2 * ((a - 1) + (a + 1) * cos_w0)
        a2 = (a + 1) + (a - 1) * cos_w0 - 2 * sqrt_a * alpha
    elif band.type == "high_shelf":
        sqrt_a = math.sqrt(a)
        b0 = a * ((a + 1) + (a - 1) * cos_w0 + 2 * sqrt_a * alpha)
        b1 = -2 * a * ((a - 1) + (a + 1) * cos_w0)
        b2 = a * ((a + 1) + (a - 1) * cos_w0 - 2 * sqrt_a * alpha)
        a0 = (a + 1) - (a - 1) * cos_w0 + 2 * sqrt_a * alpha
        a1 = 2 * ((a - 1) - (a + 1) * cos_w0)
        a2 = (a + 1) - (a - 1) * cos_w0 - 2 * sqrt_a * alpha
    elif band.type == "low_pass":
        b0 = (1 - cos_w0) / 2
        b1 = 1 - cos_w0
        b2 = (1 - cos_w0) / 2
        a0 = 1 + alpha
        a1 = -2 * cos_w0
        a2 = 1 - alpha
    elif band.type == "high_pass":
        b0 = (1 + cos_w0) / 2
        b1 = -(1 + cos_w0)
        b2 = (1 + cos_w0) / 2
        a0 = 1 + alpha
        a1 = -2 * cos_w0
        a2 = 1 - alpha
    else:  # peak
        b0 = 1 + alpha * a
        b1 = -2 * cos_w0
        b2 = 1 - alpha * a
        a0 = 1 + alpha / a
        a1 = -2 * cos_w0
        a2 = 1 - alpha / a

    return np.array([b0, b1, b2]) / a0, np.array([a0, a1, a2]) / a0


def _band_is_active(band: EQBand) -> bool:
    if not band.enabled:
        return False
    if band.type in ("low_pass", "high_pass"):
        return True
    return abs(band.gain_db) > 1e-6


def any_band_active(bands: list[EQBand]) -> bool:
    return any(_band_is_active(b) for b in bands)


def apply_eq(channels: list[np.ndarray], sample_rate: int, bands: list[EQBand]) -> list[np.ndarray]:
    active = [b for b in bands if _band_is_active(b)]
    if not active:
        return [ch.copy() for ch in channels]

    result = []
    for ch in channels:
        out = ch
        for band in active:
            b, a = design_band(band, sample_rate)
            out = lfilter(b, a, out)
        result.append(out)
    return result


def eq_frequency_response(bands: list[EQBand], sample_rate: int, num_points: int = 300):
    """Returns (freqs_hz, magnitude_db) for the cascaded response of all
    enabled bands, log-spaced from 20 Hz to just under Nyquist."""
    nyquist = max(sample_rate / 2.0, 100.0)
    f_max = min(20000.0, nyquist * 0.99)
    freqs = np.logspace(math.log10(20.0), math.log10(max(f_max, 21.0)), num_points)

    total_h = np.ones(num_points, dtype=complex)
    for band in bands:
        if not band.enabled:
            continue
        b, a = design_band(band, sample_rate)
        _, h = freqz(b, a, worN=freqs, fs=sample_rate)
        total_h *= h

    mag_db = 20.0 * np.log10(np.maximum(np.abs(total_h), 1e-9))
    return freqs, mag_db
