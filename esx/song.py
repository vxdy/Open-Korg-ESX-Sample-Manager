import struct
from .constants import (
    CHUNKSIZE_SONG, CHUNKSIZE_SONG_EVENT, NUM_SONG_PATTERNS
)
from .utils import decode_name, encode_name, safe_enum
from .pattern import Tempo


class TempoLock:
    OFF = 0
    ON = 1


class SongLength:
    def __init__(self, value=0):
        self.value = value


class MuteHold:
    OFF = 0
    ON = 1


class SongPattern:
    def __init__(self):
        self.note_offset = 0


class SongEvent:
    def __init__(self):
        self.raw_data = bytes(8)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'SongEvent':
        e = cls()
        e.raw_data = data[:8]
        return e

    def to_bytes(self) -> bytes:
        return self.raw_data


class Song:
    def __init__(self):
        self.name = ''
        self.tempo = Tempo()
        self.tempo_lock = 0
        self.song_length = 0
        self.mute_hold = 0
        self.next_song_number = 0
        self.num_song_events_original = 0
        self.reserved_bytes = bytes(8)
        self.song_patterns = [SongPattern() for _ in range(NUM_SONG_PATTERNS)]
        self.song_events = []
        self.song_number = -1

    @classmethod
    def from_bytes(cls, data: bytes, song_number: int = -1) -> 'Song':
        s = cls()
        s.song_number = song_number
        offset = 0

        # bytes 0~7: name
        s.name = decode_name(data[0:8])
        offset = 8

        # bytes 8~9: tempo
        s.tempo = Tempo.from_short(struct.unpack_from('>h', data, offset)[0])
        offset += 2

        # byte 10: tempo lock
        s.tempo_lock = data[offset]; offset += 1
        # byte 11: song length
        s.song_length = data[offset]; offset += 1
        # byte 12: mute hold
        s.mute_hold = data[offset]; offset += 1
        # byte 13: next song number
        s.next_song_number = data[offset]; offset += 1
        # bytes 14~15: number of song events
        s.num_song_events_original = struct.unpack_from('>h', data, offset)[0]; offset += 2
        # bytes 16~23: reserved
        s.reserved_bytes = data[offset:offset + 8]; offset += 8

        # bytes 24~279: song patterns (256 x 1 byte)
        for i in range(NUM_SONG_PATTERNS):
            sp = SongPattern()
            if offset < len(data):
                sp.note_offset = struct.unpack_from('b', data, offset)[0]
                offset += 1
            s.song_patterns[i] = sp

        return s

    def init_song_events(self, data: bytes):
        self.song_events = []
        offset = 0
        while offset + CHUNKSIZE_SONG_EVENT <= len(data):
            e = SongEvent.from_bytes(data[offset:offset + CHUNKSIZE_SONG_EVENT])
            self.song_events.append(e)
            offset += CHUNKSIZE_SONG_EVENT

    def to_song_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_SONG)
        offset = 0

        name_b = encode_name(self.name, 8, 0x00)
        buf[0:8] = name_b
        offset = 8

        struct.pack_into('>h', buf, offset, self.tempo.to_short()); offset += 2
        buf[offset] = self.tempo_lock; offset += 1
        buf[offset] = self.song_length; offset += 1
        buf[offset] = self.mute_hold; offset += 1
        buf[offset] = self.next_song_number; offset += 1
        num_events = len(self.song_events)
        struct.pack_into('>h', buf, offset, num_events); offset += 2
        buf[offset:offset + 8] = self.reserved_bytes[:8]; offset += 8

        for i, sp in enumerate(self.song_patterns):
            if offset < CHUNKSIZE_SONG:
                struct.pack_into('b', buf, offset, sp.note_offset)
                offset += 1

        return bytes(buf)

    def to_song_events_bytes(self) -> bytes:
        result = bytearray()
        for e in self.song_events:
            result.extend(e.to_bytes())
        return bytes(result)

    def label(self) -> str:
        return f"{self.song_number} - {self.name}"
