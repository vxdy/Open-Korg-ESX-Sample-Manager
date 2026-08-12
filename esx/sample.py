import os
import struct
import wave
import io
from .constants import (
    CHUNKSIZE_SAMPLE_HEADER_MONO, CHUNKSIZE_SAMPLE_HEADER_STEREO,
    CHUNKSIZE_SLICE_DATA, DEFAULT_SAMPLING_RATE, PlayLevel, StretchStep
)
from .utils import decode_name, encode_name, safe_enum


class SampleTune:
    BASE_SAMPLE_RATE = 44100.0

    def __init__(self, value=0.0):
        self.value = value  # float semitone offset

    @classmethod
    def from_short(cls, short_val: int) -> 'SampleTune':
        t = cls()
        t.value = short_val / 100.0
        return t

    def to_short(self) -> int:
        return int(self.value * 100)

    def calculate_sample_rate(self) -> int:
        import math
        rate = self.BASE_SAMPLE_RATE * (2 ** (self.value / 12.0))
        return int(rate)


class Sample:
    def __init__(self):
        self.name = ''
        self.offset_ch1_start = 0
        self.offset_ch1_end = 0
        self.offset_ch2_start = 0
        self.offset_ch2_end = 0
        self.start = 0
        self.end = 0
        self.loop_start = 0
        self.sample_rate = DEFAULT_SAMPLING_RATE
        self.sample_tune = SampleTune()
        self.play_level = PlayLevel.DB_0
        self.stretch_step = StretchStep.OFF
        self.unknown_byte1 = 0
        self.unknown_byte2 = 0
        self.unknown_byte3 = 0
        self.unknown_byte4 = 0
        self.audio_data_ch1 = bytes()
        self.audio_data_ch2 = bytes()
        self.slice_array = bytes(CHUNKSIZE_SLICE_DATA)
        self.num_frames = 0
        self.is_stereo_original = False
        self.sample_number = -1
        self._loop = False
        self._loop_type = 0

    @classmethod
    def from_wav_file(cls, filepath: str, sample_number: int = -1, as_mono: bool = True) -> 'Sample':
        with wave.open(filepath, 'rb') as wav_file:
            if wav_file.getcomptype() != 'NONE':
                raise ValueError("Only uncompressed PCM WAV files are supported")
            channels = wav_file.getnchannels()
            sampwidth = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            num_frames = wav_file.getnframes()
            raw_data = wav_file.readframes(num_frames)

        if channels < 1:
            raise ValueError("WAV file has no audio channels")
        if sampwidth not in (1, 2, 3, 4):
            raise ValueError(f"Unsupported WAV sample width: {sampwidth * 8} bit")

        sample = cls()
        sample.sample_number = sample_number
        sample.name = cls._name_from_path(filepath)
        sample.sample_rate = sample_rate if sample_rate > 0 else DEFAULT_SAMPLING_RATE
        sample.sample_tune = SampleTune()
        sample.play_level = PlayLevel.DB_0
        sample.stretch_step = StretchStep.OFF
        sample.start = 0

        if as_mono or channels == 1:
            audio = cls._wav_raw_to_mono_be(raw_data, channels, sampwidth)
            sample.audio_data_ch1 = audio
            sample.audio_data_ch2 = audio
            sample.is_stereo_original = False
        else:
            ch1, ch2 = cls._wav_raw_to_stereo_be(raw_data, channels, sampwidth)
            sample.audio_data_ch1 = ch1
            sample.audio_data_ch2 = ch2
            sample.is_stereo_original = True

        sample.num_frames = len(sample.audio_data_ch1) // 2
        sample.end = max(0, sample.num_frames - 1)
        sample.loop_start = sample.end
        return sample

    @staticmethod
    def _name_from_path(filepath: str) -> str:
        stem = os.path.splitext(os.path.basename(filepath))[0]
        clean = ''.join(ch if 32 <= ord(ch) < 127 else '_' for ch in stem)
        return clean.strip()[:8]

    @classmethod
    def _wav_raw_to_mono_be(cls, raw_data: bytes, channels: int, sampwidth: int) -> bytes:
        frame_size = channels * sampwidth
        num_frames = len(raw_data) // frame_size
        result = bytearray(num_frames * 2)
        for frame in range(num_frames):
            base = frame * frame_size
            total = 0
            for channel in range(channels):
                total += cls._read_wav_sample(raw_data, base + channel * sampwidth, sampwidth)
            mixed = cls._clamp_sample(total // channels)
            struct.pack_into('>h', result, frame * 2, mixed)
        return bytes(result)

    @classmethod
    def _wav_raw_to_stereo_be(cls, raw_data: bytes, channels: int, sampwidth: int) -> tuple[bytes, bytes]:
        frame_size = channels * sampwidth
        num_frames = len(raw_data) // frame_size
        ch1 = bytearray(num_frames * 2)
        ch2 = bytearray(num_frames * 2)
        for frame in range(num_frames):
            base = frame * frame_size
            left = cls._read_wav_sample(raw_data, base, sampwidth)
            if channels > 1:
                right = cls._read_wav_sample(raw_data, base + sampwidth, sampwidth)
            else:
                right = left
            struct.pack_into('>h', ch1, frame * 2, cls._clamp_sample(left))
            struct.pack_into('>h', ch2, frame * 2, cls._clamp_sample(right))
        return bytes(ch1), bytes(ch2)

    @staticmethod
    def _read_wav_sample(raw_data: bytes, offset: int, sampwidth: int) -> int:
        if sampwidth == 1:
            return (raw_data[offset] - 128) << 8
        if sampwidth == 2:
            return struct.unpack_from('<h', raw_data, offset)[0]
        if sampwidth == 3:
            return int.from_bytes(raw_data[offset:offset + 3], 'little', signed=True) >> 8
        return struct.unpack_from('<i', raw_data, offset)[0] >> 16

    @staticmethod
    def _clamp_sample(value: int) -> int:
        return max(-32768, min(32767, int(value)))

    @classmethod
    def from_mono_header(cls, data: bytes, sample_number: int = -1) -> 'Sample':
        s = cls()
        s.sample_number = sample_number
        s.is_stereo_original = False
        offset = 0
        s.name = decode_name(data[0:8])
        offset = 8
        s.offset_ch1_start = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.offset_ch1_end = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.start = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.end = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.loop_start = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.sample_rate = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.sample_tune = SampleTune.from_short(struct.unpack_from('>h', data, offset)[0]); offset += 2
        s.play_level = safe_enum(PlayLevel, data[offset]); offset += 1
        s.unknown_byte1 = data[offset]; offset += 1
        s.stretch_step = safe_enum(StretchStep, data[offset]); offset += 1
        s.unknown_byte2 = data[offset]; offset += 1
        s.unknown_byte3 = data[offset]; offset += 1
        s.unknown_byte4 = data[offset]; offset += 1
        return s

    @classmethod
    def from_stereo_header(cls, data: bytes, sample_number: int = -1) -> 'Sample':
        s = cls()
        s.sample_number = sample_number
        s.is_stereo_original = True
        offset = 0
        s.name = decode_name(data[0:8])
        offset = 8
        s.offset_ch1_start = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.offset_ch1_end = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.offset_ch2_start = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.offset_ch2_end = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.start = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.end = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.sample_rate = struct.unpack_from('>i', data, offset)[0]; offset += 4
        s.sample_tune = SampleTune.from_short(struct.unpack_from('>h', data, offset)[0]); offset += 2
        s.play_level = safe_enum(PlayLevel, data[offset]); offset += 1
        s.unknown_byte1 = data[offset]; offset += 1
        s.stretch_step = safe_enum(StretchStep, data[offset]); offset += 1
        s.unknown_byte2 = data[offset]; offset += 1
        s.unknown_byte3 = data[offset]; offset += 1
        s.unknown_byte4 = data[offset]; offset += 1
        return s

    def init_audio_channel(self, data: bytes, channel_type: str):
        # ESX offsets include only the 16-byte offset header plus PCM data.
        # Loop/padding bytes live after the offset end and are skipped here.
        num_frames = (len(data) - 16) // 2
        if num_frames <= 0:
            return
        self.num_frames = num_frames
        # skip 16 header bytes
        pcm = data[16:16 + num_frames * 2]
        if channel_type == 'MONO':
            self.audio_data_ch1 = pcm
            self.audio_data_ch2 = pcm
        elif channel_type == 'STEREO_1':
            self.audio_data_ch1 = pcm
        elif channel_type == 'STEREO_2':
            self.audio_data_ch2 = pcm

    def init_slice_array(self, data: bytes):
        self.slice_array = data[:CHUNKSIZE_SLICE_DATA]

    def is_empty(self) -> bool:
        return not (
            self.audio_data_ch1
            and self.audio_data_ch2
            and len(self.audio_data_ch1) == len(self.audio_data_ch2)
        )

    def clear(self):
        sample_number = self.sample_number
        self.__init__()
        self.sample_number = sample_number

    def invalidate_offsets(self):
        self.offset_ch1_start = -1
        self.offset_ch1_end = -1
        self.offset_ch2_start = -1
        self.offset_ch2_end = -1

    def get_audio_data_loop_start(self) -> bytes:
        if self.loop_start < self.end and self.loop_start >= 0:
            audio = self.get_audio_channel_both()
            offset = self.loop_start * 2
            if offset + 1 < len(audio):
                return audio[offset:offset + 2]
        return b'\x00\x00'

    def get_audio_channel_both(self) -> bytes:
        if self.is_empty():
            return bytes()
        if not self.audio_data_ch1 or not self.audio_data_ch2:
            return self.audio_data_ch1 or self.audio_data_ch2 or bytes()
        ch1 = self.audio_data_ch1
        ch2 = self.audio_data_ch2
        num_frames = min(len(ch1), len(ch2)) // 2
        result = bytearray(num_frames * 2)
        for i in range(num_frames):
            s1 = struct.unpack_from('>h', ch1, i * 2)[0]
            s2 = struct.unpack_from('>h', ch2, i * 2)[0]
            mixed = (s1 + s2) // 2
            struct.pack_into('>h', result, i * 2, mixed)
        return bytes(result)

    def get_audio_channel_both_length(self) -> int:
        """Byte length get_audio_channel_both() would return, without doing
        the per-frame downmix - use this when only the size is needed."""
        if self.is_empty():
            return 0
        if not self.audio_data_ch1 or not self.audio_data_ch2:
            return len(self.audio_data_ch1 or self.audio_data_ch2 or b'')
        num_frames = min(len(self.audio_data_ch1), len(self.audio_data_ch2)) // 2
        return num_frames * 2

    def to_wav_bytes(self) -> bytes:
        audio = self.get_audio_channel_both()
        if not audio:
            return bytes()
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate if self.sample_rate > 0 else DEFAULT_SAMPLING_RATE)
            # Convert big-endian PCM to little-endian for WAV
            num_frames = len(audio) // 2
            le_data = bytearray(len(audio))
            for i in range(num_frames):
                val = struct.unpack_from('>h', audio, i * 2)[0]
                struct.pack_into('<h', le_data, i * 2, val)
            w.writeframes(bytes(le_data))
        return buf.getvalue()

    def to_export_wav_bytes(self) -> bytes:
        """Export the sample as a WAV file, preserving true stereo if the
        sample was originally imported as stereo (unlike to_wav_bytes(),
        which always mixes down to mono for the live preview player)."""
        if self.is_empty():
            return bytes()

        if self.is_stereo_original and self.audio_data_ch1 and self.audio_data_ch2:
            channels = 2
            num_frames = min(len(self.audio_data_ch1), len(self.audio_data_ch2)) // 2
            le_data = bytearray(num_frames * 4)
            for i in range(num_frames):
                left = struct.unpack_from('>h', self.audio_data_ch1, i * 2)[0]
                right = struct.unpack_from('>h', self.audio_data_ch2, i * 2)[0]
                struct.pack_into('<h', le_data, i * 4, left)
                struct.pack_into('<h', le_data, i * 4 + 2, right)
        else:
            channels = 1
            audio = self.audio_data_ch1 or self.audio_data_ch2
            num_frames = len(audio) // 2
            le_data = bytearray(len(audio))
            for i in range(num_frames):
                val = struct.unpack_from('>h', audio, i * 2)[0]
                struct.pack_into('<h', le_data, i * 2, val)

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(channels)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate if self.sample_rate > 0 else DEFAULT_SAMPLING_RATE)
            w.writeframes(bytes(le_data))
        return buf.getvalue()

    def to_mono_header_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_SAMPLE_HEADER_MONO)
        name_b = encode_name(self.name, 8)
        buf[0:8] = name_b
        offset = 8
        struct.pack_into('>i', buf, offset, self.offset_ch1_start); offset += 4
        struct.pack_into('>i', buf, offset, self.offset_ch1_end); offset += 4
        struct.pack_into('>i', buf, offset, self.start); offset += 4
        struct.pack_into('>i', buf, offset, self.end); offset += 4
        struct.pack_into('>i', buf, offset, self.loop_start); offset += 4
        struct.pack_into('>i', buf, offset, self.sample_rate); offset += 4
        struct.pack_into('>h', buf, offset, self.sample_tune.to_short()); offset += 2
        buf[offset] = int(self.play_level) & 0xFF; offset += 1
        buf[offset] = self.unknown_byte1; offset += 1
        buf[offset] = int(self.stretch_step) & 0xFF; offset += 1
        buf[offset] = self.unknown_byte2; offset += 1
        buf[offset] = self.unknown_byte3; offset += 1
        buf[offset] = self.unknown_byte4; offset += 1
        return bytes(buf)

    def to_stereo_header_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_SAMPLE_HEADER_STEREO)
        name_b = encode_name(self.name, 8)
        buf[0:8] = name_b
        offset = 8
        struct.pack_into('>i', buf, offset, self.offset_ch1_start); offset += 4
        struct.pack_into('>i', buf, offset, self.offset_ch1_end); offset += 4
        struct.pack_into('>i', buf, offset, self.offset_ch2_start); offset += 4
        struct.pack_into('>i', buf, offset, self.offset_ch2_end); offset += 4
        struct.pack_into('>i', buf, offset, self.start); offset += 4
        struct.pack_into('>i', buf, offset, self.end); offset += 4
        struct.pack_into('>i', buf, offset, self.sample_rate); offset += 4
        struct.pack_into('>h', buf, offset, self.sample_tune.to_short()); offset += 2
        buf[offset] = int(self.play_level) & 0xFF; offset += 1
        buf[offset] = self.unknown_byte1; offset += 1
        buf[offset] = int(self.stretch_step) & 0xFF; offset += 1
        buf[offset] = self.unknown_byte2; offset += 1
        buf[offset] = self.unknown_byte3; offset += 1
        buf[offset] = self.unknown_byte4; offset += 1
        return bytes(buf)

    def to_offset_channel_bytes(self, channel_type: str) -> bytes:
        if channel_type == 'STEREO_1':
            audio = self.audio_data_ch1
            start = self.offset_ch1_start
            end = self.offset_ch1_end
            marker = 1
        elif channel_type == 'STEREO_2':
            audio = self.audio_data_ch2
            start = self.offset_ch2_start
            end = self.offset_ch2_end
            marker = 2
        else:
            audio = self.get_audio_channel_both()
            start = self.offset_ch1_start
            end = self.offset_ch1_end
            marker = 0

        buf = bytearray()
        buf.extend(struct.pack('>IiiBBH', 0x80007FFF, start, end, self.sample_number & 0xFF, marker, 0xFFFF))
        buf.extend(audio)
        if channel_type == 'MONO':
            buf.extend(self.get_audio_data_loop_start())
        else:
            buf.extend(b'\x00\x00')
        return bytes(buf)

    def duration_seconds(self) -> float:
        if self.sample_rate and self.sample_rate > 0:
            return self.num_frames / self.sample_rate
        return 0.0

    def label(self) -> str:
        stereo = 'Stereo' if self.is_stereo_original else 'Mono'
        return f"{self.sample_number} - {self.name} [{stereo}]"
