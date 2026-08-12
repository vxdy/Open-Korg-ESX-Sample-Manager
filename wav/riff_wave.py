import wave
import struct
import os


class RiffWave:
    def __init__(self):
        self.filepath = ''
        self.num_channels = 1
        self.sample_width = 2
        self.frame_rate = 44100
        self.num_frames = 0
        self.pcm_data = bytes()
        self.loop_start = -1
        self.loop_end = -1

    @classmethod
    def from_file(cls, path: str) -> 'RiffWave':
        rw = cls()
        rw.filepath = path

        with wave.open(path, 'rb') as w:
            rw.num_channels = w.getnchannels()
            rw.sample_width = w.getsampwidth()
            rw.frame_rate = w.getframerate()
            rw.num_frames = w.getnframes()
            rw.pcm_data = w.readframes(rw.num_frames)

        # Try to read smpl chunk for loop info
        try:
            rw._read_smpl_chunk(path)
        except Exception:
            pass

        return rw

    def _read_smpl_chunk(self, path: str):
        with open(path, 'rb') as f:
            data = f.read()

        # Search for 'smpl' chunk in RIFF
        offset = 12  # skip RIFF header
        while offset + 8 <= len(data):
            chunk_id = data[offset:offset + 4]
            chunk_size = struct.unpack_from('<I', data, offset + 4)[0]
            if chunk_id == b'smpl':
                # smpl chunk: manufacturer(4), product(4), sample_period(4), midi_note(4),
                # midi_pitch_frac(4), smpte_format(4), smpte_offset(4), num_loops(4), sampler_data(4)
                # then loops: cue_point_id(4), type(4), start(4), end(4), fraction(4), play_count(4)
                smpl_offset = offset + 8
                num_loops = struct.unpack_from('<I', data, smpl_offset + 28)[0]
                if num_loops > 0:
                    loop_start_offset = smpl_offset + 36
                    self.loop_start = struct.unpack_from('<I', data, loop_start_offset + 8)[0]
                    self.loop_end = struct.unpack_from('<I', data, loop_start_offset + 12)[0]
                break
            offset += 8 + chunk_size
            if chunk_size % 2 != 0:
                offset += 1  # word align

    def get_pcm_data(self) -> bytes:
        return self.pcm_data

    def duration_seconds(self) -> float:
        if self.frame_rate > 0:
            return self.num_frames / self.frame_rate
        return 0.0
