import threading
import struct
from enum import Enum

try:
    import sounddevice as sd
    import numpy as np
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False


class PlayerState(Enum):
    STOPPED = 0
    PLAYING = 1
    PAUSED = 2


class AudioPlayer:
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
        self.state = PlayerState.STOPPED
        self._thread = None
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()
        self._current_data = None
        self._current_rate = 44100
        self._loop = False
        self._stream = None

    def play(self, wav_bytes: bytes, sample_rate: int = 44100, loop: bool = False):
        if not SOUNDDEVICE_AVAILABLE:
            print("sounddevice not available - cannot play audio")
            return

        self.stop()
        self._stop_event.clear()
        self._pause_event.set()

        try:
            import wave
            import io
            with wave.open(io.BytesIO(wav_bytes), 'rb') as w:
                nchannels = w.getnchannels()
                sampwidth = w.getsampwidth()
                framerate = w.getframerate()
                nframes = w.getnframes()
                raw = w.readframes(nframes)

            dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
            dtype = dtype_map.get(sampwidth, np.int16)
            audio = np.frombuffer(raw, dtype=dtype)
            if nchannels > 1:
                audio = audio.reshape(-1, nchannels)

            self._current_data = audio.astype(np.float32) / np.iinfo(dtype).max
            self._current_rate = framerate
            self._loop = loop

            self.state = PlayerState.PLAYING
            self._thread = threading.Thread(target=self._play_thread, daemon=True)
            self._thread.start()
        except Exception as e:
            print(f"Audio play error: {e}")

    def _play_thread(self):
        try:
            data = self._current_data
            rate = self._current_rate
            pos = 0

            def callback(outdata, frames, time, status):
                nonlocal pos
                self._pause_event.wait()
                if self._stop_event.is_set():
                    raise sd.CallbackStop()
                remaining = len(data) - pos
                if remaining <= 0:
                    if self._loop:
                        pos = 0
                        remaining = len(data)
                    else:
                        raise sd.CallbackStop()
                chunk = min(frames, remaining)
                outdata[:chunk] = data[pos:pos + chunk].reshape(-1, 1) if data.ndim == 1 else data[pos:pos + chunk]
                if chunk < frames:
                    outdata[chunk:] = 0
                pos += chunk

            channels = 1 if data.ndim == 1 else data.shape[1]
            with sd.OutputStream(
                samplerate=rate,
                channels=channels,
                callback=callback,
                finished_callback=self._on_finished
            ):
                self._stop_event.wait()
        except Exception as e:
            pass
        finally:
            self.state = PlayerState.STOPPED

    def _on_finished(self):
        self.state = PlayerState.STOPPED

    def pause(self):
        if self.state == PlayerState.PLAYING:
            self._pause_event.clear()
            self.state = PlayerState.PAUSED

    def resume(self):
        if self.state == PlayerState.PAUSED:
            self._pause_event.set()
            self.state = PlayerState.PLAYING

    def stop(self):
        self._stop_event.set()
        self._pause_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.state = PlayerState.STOPPED

    def is_playing(self) -> bool:
        return self.state == PlayerState.PLAYING

    def is_paused(self) -> bool:
        return self.state == PlayerState.PAUSED

    def is_stopped(self) -> bool:
        return self.state == PlayerState.STOPPED
