"""Optional Demucs-based stem separation, kept isolated from the rest of the
app behind is_available() the same way audio/audio_player.py guards
sounddevice - the heavy torch/demucs dependency is not required to run the
editor, only to use the Stem Splitter feature.

Unlike a normal optional dependency, torch/demucs aren't just "maybe not
installed" - they're deliberately never bundled into the frozen .exe at all
(see main.spec) and are instead installed on demand into an AppData folder
by audio/stem_deps.py. So the import here is intentionally lazy/retryable
rather than a one-shot module-level try/except: is_available() can go from
False to True mid-process, right after stem_deps.run_install() finishes and
extends sys.path, without needing an app restart."""

import wave
import io
from pathlib import Path

import numpy as np

_demucs_api = None

STEM_NAMES = ["vocals", "drums", "bass", "other"]
MODEL_NAME = "htdemucs"


def _try_import() -> bool:
    global _demucs_api
    if _demucs_api is not None:
        return True
    from audio import stem_deps
    stem_deps.ensure_on_syspath()
    try:
        import demucs.api as demucs_api
    except ImportError:
        return False
    _demucs_api = demucs_api
    return True


def is_available() -> bool:
    return _try_import()


def load_separator(callback=None, callback_arg: dict = None):
    """Builds a demucs.api.Separator, which triggers the pretrained-model
    download on first use (no official progress hook for that download - the
    caller shows an indeterminate busy indicator around this call)."""
    if not _try_import():
        raise RuntimeError("demucs is not installed")
    return _demucs_api.Separator(
        model=MODEL_NAME, progress=False, callback=callback, callback_arg=callback_arg
    )


def separate_file(separator, path: str):
    """Returns (stems, sample_rate) where stems is {name: float32 ndarray
    shaped (2, n)} for each of STEM_NAMES."""
    _origin, separated = separator.separate_audio_file(Path(path))
    stems = {}
    for name in STEM_NAMES:
        tensor = separated.get(name)
        if tensor is None:
            continue
        stems[name] = tensor.cpu().numpy().astype(np.float32)
    return stems, int(separator.samplerate)


def _to_stereo(arr: np.ndarray) -> np.ndarray:
    """Normalizes a (2, n) or (n, 2) or (n,) array to shape (2, n)."""
    if arr.ndim == 1:
        return np.stack([arr, arr])
    if arr.shape[0] == 2:
        return arr
    if arr.shape[1] == 2:
        return arr.T
    raise ValueError(f"Unexpected stem array shape: {arr.shape}")


def mix_stems(stems: dict, selected: list) -> np.ndarray:
    """Sums the selected stems (a Demucs stem set decomposes the original
    mix, so summation reconstructs it) and safety-clips to [-1, 1]. Returns
    a (2, n) float32 array, or an all-zero (2, 0) array if nothing selected
    or the stems are empty."""
    chosen = [_to_stereo(stems[name]) for name in selected if name in stems]
    if not chosen:
        return np.zeros((2, 0), dtype=np.float32)
    n = min(a.shape[1] for a in chosen)
    mixed = np.zeros((2, n), dtype=np.float32)
    for a in chosen:
        mixed += a[:, :n]
    return np.clip(mixed, -1.0, 1.0)


def stereo_float_to_wav_bytes(stereo: np.ndarray, sample_rate: int, mono: bool = False) -> bytes:
    """Converts a (2, n) float32 [-1, 1] array to a standard little-endian
    16-bit PCM WAV, mono-downmixed if requested. Used both for in-memory
    preview playback and for the temp file handed to Sample.from_wav_file."""
    if stereo.size == 0:
        return bytes()
    clipped = np.clip(stereo, -1.0, 1.0)
    if mono:
        mono_arr = clipped.mean(axis=0)
        ints = np.round(mono_arr * 32767.0).astype('<i2')
        channels = 1
        interleaved = ints
    else:
        ints = np.round(clipped * 32767.0).astype('<i2')
        channels = 2
        interleaved = np.empty(ints.shape[1] * 2, dtype='<i2')
        interleaved[0::2] = ints[0]
        interleaved[1::2] = ints[1]

    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(sample_rate if sample_rate > 0 else 44100)
        w.writeframes(interleaved.tobytes())
    return buf.getvalue()


def write_wav_file(path: str, stereo: np.ndarray, sample_rate: int, mono: bool = False):
    with open(path, 'wb') as f:
        f.write(stereo_float_to_wav_bytes(stereo, sample_rate, mono))


def mono_preview_be16(arr: np.ndarray) -> bytes:
    """Downmixes a stem array to mono big-endian int16 PCM, the exact format
    WaveformWidget.set_audio() expects for a preview."""
    if arr.size == 0:
        return bytes()
    mono = _to_stereo(arr).mean(axis=0)
    clipped = np.clip(mono, -1.0, 1.0)
    ints = np.round(clipped * 32767.0).astype('>i2')
    return ints.tobytes()
