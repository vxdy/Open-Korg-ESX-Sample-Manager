import struct
from typing import List, Optional
from .constants import (
    ADDR_VALID_ESX_CHECK_1, ADDR_GLOBAL_PARAMETERS, ADDR_PATTERN_DATA,
    ADDR_SONG_DATA, ADDR_SONG_EVENT_DATA, ADDR_VALID_ESX_CHECK_2,
    ADDR_NUM_MONO_SAMPLES, ADDR_NUM_STEREO_SAMPLES, ADDR_CURRENT_OFFSET,
    ADDR_SAMPLE_HEADER_MONO, ADDR_SAMPLE_HEADER_STEREO,
    ADDR_SLICE_DATA, ADDR_SAMPLE_DATA,
    CHUNKSIZE_GLOBAL_PARAMETERS, CHUNKSIZE_PATTERN, CHUNKSIZE_SONG,
    CHUNKSIZE_SONG_EVENT, CHUNKSIZE_SAMPLE_HEADER_MONO, CHUNKSIZE_SAMPLE_HEADER_STEREO,
    CHUNKSIZE_SLICE_DATA,
    NUM_PATTERNS, NUM_SONGS, NUM_SAMPLES_MONO, NUM_SAMPLES_STEREO, NUM_SAMPLES,
    NUM_SLICE_DATA, SIZE_FILE_MIN, SIZE_FILE_MAX, MAX_SAMPLE_MEM_IN_BYTES
)
from .global_parameters import GlobalParameters
from .pattern import Pattern
from .sample import Sample
from .song import Song


ESX_MAGIC_1 = bytes([0x4B, 0x4F, 0x52, 0x47, 0x00, 0x00, 0x00, 0x71, 0x45, 0x53, 0x58, 0x00])
ESX_MAGIC_2 = bytes([0x4B, 0x4F, 0x52, 0x47, 0x00, 0x00, 0x00, 0x71])


class EsxFile:
    def __init__(self):
        self.global_parameters: Optional[GlobalParameters] = None
        self.patterns: List[Pattern] = []
        self.samples: List[Sample] = []
        self.songs: List[Song] = []
        self._raw_data: Optional[bytes] = None
        self._original_non_audio_data: Optional[bytes] = None

    @classmethod
    def load(cls, filepath: str) -> 'EsxFile':
        with open(filepath, 'rb') as f:
            data = f.read()

        if len(data) < SIZE_FILE_MIN:
            raise ValueError(f"File too small: {len(data)} bytes, expected at least {SIZE_FILE_MIN}")
        if len(data) > SIZE_FILE_MAX:
            raise ValueError(f"File too large: {len(data)} bytes, max {SIZE_FILE_MAX}")

        # Validate magic bytes
        check1 = data[ADDR_VALID_ESX_CHECK_1:ADDR_VALID_ESX_CHECK_1 + 12]
        if check1 != ESX_MAGIC_1:
            raise ValueError(f"Invalid ESX file: bad magic bytes at offset 0x00")

        check2 = data[ADDR_VALID_ESX_CHECK_2:ADDR_VALID_ESX_CHECK_2 + 8]
        if check2 != ESX_MAGIC_2:
            raise ValueError(f"Invalid ESX file: bad magic bytes at offset 0x1B0000")

        esx = cls()
        esx._raw_data = data
        esx._original_non_audio_data = data[:ADDR_SAMPLE_DATA]

        # Global Parameters
        gp_data = data[ADDR_GLOBAL_PARAMETERS:ADDR_GLOBAL_PARAMETERS + CHUNKSIZE_GLOBAL_PARAMETERS]
        esx.global_parameters = GlobalParameters.from_bytes(gp_data)

        # Patterns
        offset = ADDR_PATTERN_DATA
        for i in range(NUM_PATTERNS):
            chunk = data[offset:offset + CHUNKSIZE_PATTERN]
            p = Pattern.from_bytes(chunk, i)
            esx.patterns.append(p)
            offset += CHUNKSIZE_PATTERN

        # Songs
        offset = ADDR_SONG_DATA
        for i in range(NUM_SONGS):
            chunk = data[offset:offset + CHUNKSIZE_SONG]
            s = Song.from_bytes(chunk, i)
            esx.songs.append(s)
            offset += CHUNKSIZE_SONG

        # Song events
        offset = ADDR_SONG_EVENT_DATA
        for i in range(NUM_SONGS):
            song = esx.songs[i]
            num_events = max(0, song.num_song_events_original)
            if num_events > 0:
                event_bytes = data[offset:offset + num_events * CHUNKSIZE_SONG_EVENT]
                song.init_song_events(event_bytes)
                offset += num_events * CHUNKSIZE_SONG_EVENT

        # Mono sample headers
        offset = ADDR_SAMPLE_HEADER_MONO
        for i in range(NUM_SAMPLES_MONO):
            chunk = data[offset:offset + CHUNKSIZE_SAMPLE_HEADER_MONO]
            s = Sample.from_mono_header(chunk, i)
            esx.samples.append(s)
            offset += CHUNKSIZE_SAMPLE_HEADER_MONO

        # Stereo sample headers
        offset = ADDR_SAMPLE_HEADER_STEREO
        for i in range(NUM_SAMPLES_MONO, NUM_SAMPLES):
            chunk = data[offset:offset + CHUNKSIZE_SAMPLE_HEADER_STEREO]
            s = Sample.from_stereo_header(chunk, i)
            esx.samples.append(s)
            offset += CHUNKSIZE_SAMPLE_HEADER_STEREO

        # Slice data
        offset = ADDR_SLICE_DATA
        for i in range(min(NUM_SAMPLES_MONO, NUM_SLICE_DATA)):
            chunk = data[offset:offset + CHUNKSIZE_SLICE_DATA]
            esx.samples[i].init_slice_array(chunk)
            offset += CHUNKSIZE_SLICE_DATA

        # Audio data
        for i in range(NUM_SAMPLES):
            sample = esx.samples[i]
            if i < NUM_SAMPLES_MONO:
                # Mono
                ch1_start = sample.offset_ch1_start
                ch1_end = sample.offset_ch1_end
                ch1_size = ch1_end - ch1_start
                INVALID = -1
                if (ch1_size > 0
                        and ch1_start != INVALID
                        and ch1_end != INVALID):
                    abs_start = ADDR_SAMPLE_DATA + ch1_start
                    chunk = data[abs_start:abs_start + ch1_size]
                    sample.init_audio_channel(chunk, 'MONO')
            else:
                # Stereo
                ch1_start = sample.offset_ch1_start
                ch1_end = sample.offset_ch1_end
                ch2_start = sample.offset_ch2_start
                ch2_end = sample.offset_ch2_end
                ch1_size = ch1_end - ch1_start
                ch2_size = ch2_end - ch2_start
                INVALID = -1
                if (ch1_size == ch2_size and ch1_size > 0
                        and ch1_start != INVALID and ch1_end != INVALID
                        and ch2_start != INVALID and ch2_end != INVALID):
                    abs1 = ADDR_SAMPLE_DATA + ch1_start
                    chunk1 = data[abs1:abs1 + ch1_size]
                    sample.init_audio_channel(chunk1, 'STEREO_1')
                    abs2 = ADDR_SAMPLE_DATA + ch2_start
                    chunk2 = data[abs2:abs2 + ch2_size]
                    sample.init_audio_channel(chunk2, 'STEREO_2')

        return esx

    def save(self, filepath: str):
        if self._original_non_audio_data is None:
            raise ValueError("No original data to save - file was not loaded")

        buf = bytearray(self._original_non_audio_data)
        if len(buf) < ADDR_SAMPLE_DATA:
            buf.extend(bytes(ADDR_SAMPLE_DATA - len(buf)))

        # Write global parameters
        gp_bytes = self.global_parameters.to_bytes()
        buf[ADDR_GLOBAL_PARAMETERS:ADDR_GLOBAL_PARAMETERS + CHUNKSIZE_GLOBAL_PARAMETERS] = gp_bytes

        # Write patterns
        offset = ADDR_PATTERN_DATA
        for p in self.patterns:
            pb = p.to_bytes()
            buf[offset:offset + CHUNKSIZE_PATTERN] = pb
            offset += CHUNKSIZE_PATTERN

        # Write songs
        offset = ADDR_SONG_DATA
        for s in self.songs:
            sb = s.to_song_bytes()
            buf[offset:offset + CHUNKSIZE_SONG] = sb
            offset += CHUNKSIZE_SONG

        # Write song events
        offset = ADDR_SONG_EVENT_DATA
        for s in self.songs:
            eb = s.to_song_events_bytes()
            buf[offset:offset + len(eb)] = eb
            offset += len(eb)

        audio_data = self._build_sample_audio_data_and_update_offsets()

        # Write mono sample headers
        offset = ADDR_SAMPLE_HEADER_MONO
        for i in range(NUM_SAMPLES_MONO):
            hb = self.samples[i].to_mono_header_bytes()
            buf[offset:offset + CHUNKSIZE_SAMPLE_HEADER_MONO] = hb
            offset += CHUNKSIZE_SAMPLE_HEADER_MONO

        # Write stereo sample headers
        offset = ADDR_SAMPLE_HEADER_STEREO
        for i in range(NUM_SAMPLES_MONO, NUM_SAMPLES):
            hb = self.samples[i].to_stereo_header_bytes()
            buf[offset:offset + CHUNKSIZE_SAMPLE_HEADER_STEREO] = hb
            offset += CHUNKSIZE_SAMPLE_HEADER_STEREO

        # Write slice data
        offset = ADDR_SLICE_DATA
        for i in range(min(NUM_SAMPLES_MONO, NUM_SLICE_DATA)):
            slice_data = self.samples[i].slice_array[:CHUNKSIZE_SLICE_DATA]
            buf[offset:offset + CHUNKSIZE_SLICE_DATA] = slice_data.ljust(CHUNKSIZE_SLICE_DATA, b'\x00')
            offset += CHUNKSIZE_SLICE_DATA

        struct.pack_into('>i', buf, ADDR_NUM_MONO_SAMPLES, self.get_used_mono_sample_count())
        struct.pack_into('>i', buf, ADDR_NUM_STEREO_SAMPLES, self.get_used_stereo_sample_count())
        struct.pack_into('>i', buf, ADDR_CURRENT_OFFSET, len(audio_data))

        eof_data = struct.pack('>IiII', 0x80007FFF, len(audio_data), 0x017FFFFE, 0x00FFFFFF)
        final_data = bytes(buf[:ADDR_SAMPLE_DATA]) + audio_data + eof_data

        if len(final_data) > SIZE_FILE_MAX:
            raise ValueError(f"File too large: {len(final_data)} bytes, max {SIZE_FILE_MAX}")

        with open(filepath, 'wb') as f:
            f.write(final_data)
        self._raw_data = final_data
        self._original_non_audio_data = final_data[:ADDR_SAMPLE_DATA]

    def _build_sample_audio_data_and_update_offsets(self) -> bytes:
        audio_data = bytearray()
        for i, sample in enumerate(self.samples):
            sample.sample_number = i
            if sample.is_empty():
                sample.invalidate_offsets()
                sample.num_frames = 0
                continue

            if i < NUM_SAMPLES_MONO:
                audio = sample.get_audio_channel_both()
                sample.audio_data_ch1 = audio
                sample.audio_data_ch2 = audio
                sample.is_stereo_original = False
                self._append_sample_channel(audio_data, sample, 'MONO')
            else:
                sample.is_stereo_original = True
                if not sample.audio_data_ch2:
                    sample.audio_data_ch2 = sample.audio_data_ch1
                frames = min(len(sample.audio_data_ch1), len(sample.audio_data_ch2)) // 2
                sample.audio_data_ch1 = sample.audio_data_ch1[:frames * 2]
                sample.audio_data_ch2 = sample.audio_data_ch2[:frames * 2]
                sample.num_frames = frames
                self._append_sample_channel(audio_data, sample, 'STEREO_1')
                self._append_sample_channel(audio_data, sample, 'STEREO_2')

            if len(audio_data) > MAX_SAMPLE_MEM_IN_BYTES:
                raise ValueError(
                    f"Sample memory exceeded: {len(audio_data)} bytes, max {MAX_SAMPLE_MEM_IN_BYTES}"
                )
        return bytes(audio_data)

    def _append_sample_channel(self, audio_data: bytearray, sample: Sample, channel_type: str):
        if channel_type == 'MONO':
            channel_audio = sample.get_audio_channel_both()
        elif channel_type == 'STEREO_2':
            channel_audio = sample.audio_data_ch2
        else:
            channel_audio = sample.audio_data_ch1

        frames = len(channel_audio) // 2
        sample.num_frames = frames
        start = len(audio_data)
        end = start + (frames * 2) + 16

        if channel_type == 'STEREO_2':
            sample.offset_ch2_start = start
            sample.offset_ch2_end = end
        else:
            sample.offset_ch1_start = start
            sample.offset_ch1_end = end

        audio_data.extend(sample.to_offset_channel_bytes(channel_type))
        if frames % 2 == 0:
            audio_data.extend(b'\x00\x00')

    def get_used_pattern_count(self) -> int:
        return sum(1 for p in self.patterns if not p.is_empty())

    def get_used_sample_count(self) -> int:
        return sum(1 for s in self.samples if not s.is_empty())

    def get_used_mono_sample_count(self) -> int:
        return sum(1 for s in self.samples[:NUM_SAMPLES_MONO] if not s.is_empty())

    def get_used_stereo_sample_count(self) -> int:
        return sum(1 for s in self.samples[NUM_SAMPLES_MONO:] if not s.is_empty())

    def get_used_song_count(self) -> int:
        return sum(1 for s in self.songs if s.name.strip('\x00').strip())

    def get_sample_memory_used_bytes(self) -> int:
        total = 0
        for i, s in enumerate(self.samples):
            if not s.is_empty():
                if i < NUM_SAMPLES_MONO:
                    total += s.get_audio_channel_both_length()
                else:
                    total += len(s.audio_data_ch1) + len(s.audio_data_ch2)
        return total
