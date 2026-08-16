import struct
from .constants import (
    CHUNKSIZE_PATTERN, CHUNKSIZE_PARTS_DRUM, CHUNKSIZE_PARTS_KEYBOARD,
    CHUNKSIZE_PARTS_STRETCHSLICE, CHUNKSIZE_PARTS_AUDIOIN, CHUNKSIZE_PARTS_ACCENT,
    CHUNKSIZE_PARAMETERS_FX, CHUNKSIZE_PARAMETERS_MOTION,
    NUM_PARTS_DRUM, NUM_PARTS_KEYBOARD, NUM_PARTS_STRETCHSLICE,
    NUM_PARTS_AUDIOIN, NUM_PARTS_ACCENT, NUM_PARAMETERS_FX, NUM_PARAMETERS_MOTION,
    NUM_SEQUENCE_DATA, NUM_SEQUENCE_DATA_GATE, NUM_SEQUENCE_DATA_NOTE, NUM_MOTION_OPERATIONS,
    AmpEg, BpmSync, Beat, FxChain, FxSelect, FxSend, FxType, FilterType,
    LastStep, ModDest, ModType, MotionSequenceStatus, PatternLength,
    Reverse, Roll, RollType, Swing, ArpeggiatorScale
)
from .utils import unpack_int, pack_int, decode_name, encode_name, safe_enum


class SequenceData:
    # Stored as a bytearray (not bytes) so the pattern step editor can flip
    # individual step bits in place instead of rebuilding the object.
    def __init__(self, raw_bytes=None):
        self.data = bytearray(raw_bytes) if raw_bytes else bytearray(NUM_SEQUENCE_DATA)

    def to_bytes(self):
        return self.data


class SequenceDataGate:
    def __init__(self, raw_bytes=None):
        self.data = bytearray(raw_bytes) if raw_bytes else bytearray(NUM_SEQUENCE_DATA_GATE)

    def to_bytes(self):
        return self.data


class SequenceDataNote:
    def __init__(self, raw_bytes=None):
        self.data = bytearray(raw_bytes) if raw_bytes else bytearray(NUM_SEQUENCE_DATA_NOTE)

    def to_bytes(self):
        return self.data


class PartDrum:
    def __init__(self):
        self.sample_pointer = -1
        self.slice_number = 0
        self.reserved_byte = 0
        self.filter_type = FilterType.LPF
        self.cutoff = 0
        self.resonance = 0
        self.eg_intensity = 0
        self.pitch = 0
        self.level = 0
        self.pan = 0
        self.eg_time = 0
        self.start_point = 0
        self.fx_select = FxSelect.FX1
        self.fx_send = FxSend.OFF
        self.roll = Roll.OFF
        self.amp_eg = AmpEg.GATE
        self.reverse = Reverse.OFF
        self.reserved_bits_after_reverse = 0
        self.mod_dest = ModDest.PITCH
        self.reserved_bit_after_mod_depth = 0
        self.mod_type = ModType.SAWTOOTH
        self.bpm_sync = BpmSync.OFF
        self.mod_speed = 0
        self.mod_depth = 0
        self.motion_sequence_status = 0
        self.sequence_data = SequenceData()

    @classmethod
    def from_bytes(cls, data: bytes) -> 'PartDrum':
        p = cls()
        offset = 0
        p.sample_pointer = struct.unpack_from('>h', data, offset)[0]; offset += 2
        p.slice_number = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.reserved_byte = data[offset]; offset += 1
        p.filter_type = safe_enum(FilterType, data[offset]); offset += 1
        p.cutoff = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.resonance = data[offset]; offset += 1
        p.eg_intensity = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.pitch = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.level = data[offset]; offset += 1
        p.pan = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.eg_time = data[offset]; offset += 1
        p.start_point = data[offset]; offset += 1
        packed13 = data[offset]; offset += 1
        p.fx_select = safe_enum(FxSelect, unpack_int(packed13, 2, 0))
        p.fx_send = safe_enum(FxSend, unpack_int(packed13, 1, 2))
        p.roll = safe_enum(Roll, unpack_int(packed13, 1, 3))
        p.amp_eg = safe_enum(AmpEg, unpack_int(packed13, 1, 4))
        p.reverse = safe_enum(Reverse, unpack_int(packed13, 1, 5))
        p.reserved_bits_after_reverse = unpack_int(packed13, 2, 6)
        packed14 = data[offset]; offset += 1
        p.mod_dest = safe_enum(ModDest, unpack_int(packed14, 3, 0))
        p.reserved_bit_after_mod_depth = unpack_int(packed14, 1, 3)
        p.mod_type = safe_enum(ModType, unpack_int(packed14, 3, 4))
        p.bpm_sync = safe_enum(BpmSync, unpack_int(packed14, 1, 7))
        p.mod_speed = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.mod_depth = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.motion_sequence_status = data[offset]; offset += 1
        p.sequence_data = SequenceData(data[offset:offset + NUM_SEQUENCE_DATA])
        return p

    def to_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_PARTS_DRUM)
        offset = 0
        struct.pack_into('>h', buf, offset, self.sample_pointer); offset += 2
        struct.pack_into('b', buf, offset, self.slice_number); offset += 1
        buf[offset] = self.reserved_byte; offset += 1
        buf[offset] = int(self.filter_type); offset += 1
        struct.pack_into('b', buf, offset, self.cutoff); offset += 1
        buf[offset] = self.resonance; offset += 1
        struct.pack_into('b', buf, offset, self.eg_intensity); offset += 1
        struct.pack_into('b', buf, offset, self.pitch); offset += 1
        buf[offset] = self.level; offset += 1
        struct.pack_into('b', buf, offset, self.pan); offset += 1
        buf[offset] = self.eg_time; offset += 1
        buf[offset] = self.start_point; offset += 1
        packed13 = 0
        packed13 = pack_int(packed13, int(self.fx_select), 2, 0)
        packed13 = pack_int(packed13, int(self.fx_send), 1, 2)
        packed13 = pack_int(packed13, int(self.roll), 1, 3)
        packed13 = pack_int(packed13, int(self.amp_eg), 1, 4)
        packed13 = pack_int(packed13, int(self.reverse), 1, 5)
        packed13 = pack_int(packed13, self.reserved_bits_after_reverse, 2, 6)
        buf[offset] = packed13 & 0xFF; offset += 1
        packed14 = 0
        packed14 = pack_int(packed14, int(self.mod_dest), 3, 0)
        packed14 = pack_int(packed14, self.reserved_bit_after_mod_depth, 1, 3)
        packed14 = pack_int(packed14, int(self.mod_type), 3, 4)
        packed14 = pack_int(packed14, int(self.bpm_sync), 1, 7)
        buf[offset] = packed14 & 0xFF; offset += 1
        struct.pack_into('b', buf, offset, self.mod_speed); offset += 1
        struct.pack_into('b', buf, offset, self.mod_depth); offset += 1
        buf[offset] = self.motion_sequence_status; offset += 1
        seq = self.sequence_data.to_bytes()
        buf[offset:offset + NUM_SEQUENCE_DATA] = seq[:NUM_SEQUENCE_DATA]
        return bytes(buf)


class PartKeyboard:
    def __init__(self):
        self.sample_pointer = -1
        self.slice_number = 0
        self.reserved_byte = 0
        self.glide = 0
        self.filter_type = FilterType.LPF
        self.cutoff = 0
        self.resonance = 0
        self.eg_intensity = 0
        self.level = 0
        self.pan = 0
        self.eg_time = 0
        self.start_point = 0
        self.fx_select = FxSelect.FX1
        self.fx_send = FxSend.OFF
        self.roll = Roll.OFF
        self.amp_eg = AmpEg.GATE
        self.reverse = Reverse.OFF
        self.reserved_bits_after_reverse = 0
        self.mod_dest = ModDest.PITCH
        self.reserved_bit_after_mod_depth = 0
        self.mod_type = ModType.SAWTOOTH
        self.bpm_sync = BpmSync.OFF
        self.mod_speed = 0
        self.mod_depth = 0
        self.motion_sequence_status = 0
        self.sequence_data_note = SequenceDataNote()
        self.sequence_data_gate = SequenceDataGate()

    @classmethod
    def from_bytes(cls, data: bytes) -> 'PartKeyboard':
        p = cls()
        offset = 0
        p.sample_pointer = struct.unpack_from('>h', data, offset)[0]; offset += 2
        p.slice_number = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.reserved_byte = data[offset]; offset += 1
        p.glide = data[offset]; offset += 1
        p.filter_type = safe_enum(FilterType, data[offset]); offset += 1
        p.cutoff = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.resonance = data[offset]; offset += 1
        p.eg_intensity = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.level = data[offset]; offset += 1
        p.pan = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.eg_time = data[offset]; offset += 1
        p.start_point = data[offset]; offset += 1
        packed13 = data[offset]; offset += 1
        p.fx_select = safe_enum(FxSelect, unpack_int(packed13, 2, 0))
        p.fx_send = safe_enum(FxSend, unpack_int(packed13, 1, 2))
        p.roll = safe_enum(Roll, unpack_int(packed13, 1, 3))
        p.amp_eg = safe_enum(AmpEg, unpack_int(packed13, 1, 4))
        p.reverse = safe_enum(Reverse, unpack_int(packed13, 1, 5))
        p.reserved_bits_after_reverse = unpack_int(packed13, 2, 6)
        packed14 = data[offset]; offset += 1
        p.mod_dest = safe_enum(ModDest, unpack_int(packed14, 3, 0))
        p.reserved_bit_after_mod_depth = unpack_int(packed14, 1, 3)
        p.mod_type = safe_enum(ModType, unpack_int(packed14, 3, 4))
        p.bpm_sync = safe_enum(BpmSync, unpack_int(packed14, 1, 7))
        p.mod_speed = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.mod_depth = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.motion_sequence_status = data[offset]; offset += 1
        p.sequence_data_note = SequenceDataNote(data[offset:offset + NUM_SEQUENCE_DATA_NOTE])
        offset += NUM_SEQUENCE_DATA_NOTE
        p.sequence_data_gate = SequenceDataGate(data[offset:offset + NUM_SEQUENCE_DATA_GATE])
        return p

    def to_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_PARTS_KEYBOARD)
        offset = 0
        struct.pack_into('>h', buf, offset, self.sample_pointer); offset += 2
        struct.pack_into('b', buf, offset, self.slice_number); offset += 1
        buf[offset] = self.reserved_byte; offset += 1
        buf[offset] = self.glide; offset += 1
        buf[offset] = int(self.filter_type); offset += 1
        struct.pack_into('b', buf, offset, self.cutoff); offset += 1
        buf[offset] = self.resonance; offset += 1
        struct.pack_into('b', buf, offset, self.eg_intensity); offset += 1
        buf[offset] = self.level; offset += 1
        struct.pack_into('b', buf, offset, self.pan); offset += 1
        buf[offset] = self.eg_time; offset += 1
        buf[offset] = self.start_point; offset += 1
        packed13 = 0
        packed13 = pack_int(packed13, int(self.fx_select), 2, 0)
        packed13 = pack_int(packed13, int(self.fx_send), 1, 2)
        packed13 = pack_int(packed13, int(self.roll), 1, 3)
        packed13 = pack_int(packed13, int(self.amp_eg), 1, 4)
        packed13 = pack_int(packed13, int(self.reverse), 1, 5)
        packed13 = pack_int(packed13, self.reserved_bits_after_reverse, 2, 6)
        buf[offset] = packed13 & 0xFF; offset += 1
        packed14 = 0
        packed14 = pack_int(packed14, int(self.mod_dest), 3, 0)
        packed14 = pack_int(packed14, self.reserved_bit_after_mod_depth, 1, 3)
        packed14 = pack_int(packed14, int(self.mod_type), 3, 4)
        packed14 = pack_int(packed14, int(self.bpm_sync), 1, 7)
        buf[offset] = packed14 & 0xFF; offset += 1
        struct.pack_into('b', buf, offset, self.mod_speed); offset += 1
        struct.pack_into('b', buf, offset, self.mod_depth); offset += 1
        buf[offset] = self.motion_sequence_status; offset += 1
        note_data = self.sequence_data_note.to_bytes()
        buf[offset:offset + NUM_SEQUENCE_DATA_NOTE] = note_data[:NUM_SEQUENCE_DATA_NOTE]
        offset += NUM_SEQUENCE_DATA_NOTE
        gate_data = self.sequence_data_gate.to_bytes()
        buf[offset:offset + NUM_SEQUENCE_DATA_GATE] = gate_data[:NUM_SEQUENCE_DATA_GATE]
        return bytes(buf)


class PartStretchSlice:
    def __init__(self):
        self.sample_pointer = -1
        self.filter_type = FilterType.LPF
        self.cutoff = 0
        self.resonance = 0
        self.eg_intensity = 0
        self.pitch = 0
        self.level = 0
        self.pan = 0
        self.eg_time = 0
        self.start_point = 0
        self.fx_select = FxSelect.FX1
        self.fx_send = FxSend.OFF
        self.roll = Roll.OFF
        self.amp_eg = AmpEg.GATE
        self.reverse = Reverse.OFF
        self.reserved_bits_after_reverse = 0
        self.mod_dest = ModDest.PITCH
        self.reserved_bit_after_mod_depth = 0
        self.mod_type = ModType.SAWTOOTH
        self.bpm_sync = BpmSync.OFF
        self.mod_speed = 0
        self.mod_depth = 0
        self.motion_sequence_status = 0
        self.sequence_data = SequenceData()

    @classmethod
    def from_bytes(cls, data: bytes) -> 'PartStretchSlice':
        p = cls()
        offset = 0
        p.sample_pointer = struct.unpack_from('>h', data, offset)[0]; offset += 2
        p.filter_type = safe_enum(FilterType, data[offset]); offset += 1
        p.cutoff = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.resonance = data[offset]; offset += 1
        p.eg_intensity = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.pitch = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.level = data[offset]; offset += 1
        p.pan = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.eg_time = data[offset]; offset += 1
        p.start_point = data[offset]; offset += 1
        packed11 = data[offset]; offset += 1
        p.fx_select = safe_enum(FxSelect, unpack_int(packed11, 2, 0))
        p.fx_send = safe_enum(FxSend, unpack_int(packed11, 1, 2))
        p.roll = safe_enum(Roll, unpack_int(packed11, 1, 3))
        p.amp_eg = safe_enum(AmpEg, unpack_int(packed11, 1, 4))
        p.reverse = safe_enum(Reverse, unpack_int(packed11, 1, 5))
        p.reserved_bits_after_reverse = unpack_int(packed11, 2, 6)
        packed12 = data[offset]; offset += 1
        p.mod_dest = safe_enum(ModDest, unpack_int(packed12, 3, 0))
        p.reserved_bit_after_mod_depth = unpack_int(packed12, 1, 3)
        p.mod_type = safe_enum(ModType, unpack_int(packed12, 3, 4))
        p.bpm_sync = safe_enum(BpmSync, unpack_int(packed12, 1, 7))
        p.mod_speed = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.mod_depth = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.motion_sequence_status = data[offset]; offset += 1
        p.sequence_data = SequenceData(data[offset:offset + NUM_SEQUENCE_DATA])
        return p

    def to_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_PARTS_STRETCHSLICE)
        offset = 0
        struct.pack_into('>h', buf, offset, self.sample_pointer); offset += 2
        buf[offset] = int(self.filter_type); offset += 1
        struct.pack_into('b', buf, offset, self.cutoff); offset += 1
        buf[offset] = self.resonance; offset += 1
        struct.pack_into('b', buf, offset, self.eg_intensity); offset += 1
        struct.pack_into('b', buf, offset, self.pitch); offset += 1
        buf[offset] = self.level; offset += 1
        struct.pack_into('b', buf, offset, self.pan); offset += 1
        buf[offset] = self.eg_time; offset += 1
        buf[offset] = self.start_point; offset += 1
        packed11 = 0
        packed11 = pack_int(packed11, int(self.fx_select), 2, 0)
        packed11 = pack_int(packed11, int(self.fx_send), 1, 2)
        packed11 = pack_int(packed11, int(self.roll), 1, 3)
        packed11 = pack_int(packed11, int(self.amp_eg), 1, 4)
        packed11 = pack_int(packed11, int(self.reverse), 1, 5)
        packed11 = pack_int(packed11, self.reserved_bits_after_reverse, 2, 6)
        buf[offset] = packed11 & 0xFF; offset += 1
        packed12 = 0
        packed12 = pack_int(packed12, int(self.mod_dest), 3, 0)
        packed12 = pack_int(packed12, self.reserved_bit_after_mod_depth, 1, 3)
        packed12 = pack_int(packed12, int(self.mod_type), 3, 4)
        packed12 = pack_int(packed12, int(self.bpm_sync), 1, 7)
        buf[offset] = packed12 & 0xFF; offset += 1
        struct.pack_into('b', buf, offset, self.mod_speed); offset += 1
        struct.pack_into('b', buf, offset, self.mod_depth); offset += 1
        buf[offset] = self.motion_sequence_status; offset += 1
        seq = self.sequence_data.to_bytes()
        buf[offset:offset + NUM_SEQUENCE_DATA] = seq[:NUM_SEQUENCE_DATA]
        return bytes(buf)


class PartAudioIn:
    def __init__(self):
        self.filter_type = FilterType.LPF
        self.cutoff = 0
        self.resonance = 0
        self.eg_intensity = 0
        self.level = 0
        self.pan = 0
        self.eg_time = 0
        self.fx_select = FxSelect.FX1
        self.fx_send = FxSend.OFF
        self.roll = Roll.OFF
        self.amp_eg = AmpEg.GATE
        self.reserved_bits = 0
        self.mod_dest = ModDest.PITCH
        self.reserved_bit_after_mod_depth = 0
        self.mod_type = ModType.SAWTOOTH
        self.bpm_sync = BpmSync.OFF
        self.mod_speed = 0
        self.mod_depth = 0
        self.motion_sequence_status = 0
        self.sequence_data = SequenceData()
        self.sequence_data_gate = SequenceDataGate()

    @classmethod
    def from_bytes(cls, data: bytes) -> 'PartAudioIn':
        p = cls()
        offset = 0
        p.filter_type = safe_enum(FilterType, data[offset]); offset += 1
        p.cutoff = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.resonance = data[offset]; offset += 1
        p.eg_intensity = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.level = data[offset]; offset += 1
        p.pan = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.eg_time = data[offset]; offset += 1
        packed7 = data[offset]; offset += 1
        p.fx_select = safe_enum(FxSelect, unpack_int(packed7, 2, 0))
        p.fx_send = safe_enum(FxSend, unpack_int(packed7, 1, 2))
        p.roll = safe_enum(Roll, unpack_int(packed7, 1, 3))
        p.amp_eg = safe_enum(AmpEg, unpack_int(packed7, 1, 4))
        p.reserved_bits = unpack_int(packed7, 3, 5)
        packed8 = data[offset]; offset += 1
        p.mod_dest = safe_enum(ModDest, unpack_int(packed8, 3, 0))
        p.reserved_bit_after_mod_depth = unpack_int(packed8, 1, 3)
        p.mod_type = safe_enum(ModType, unpack_int(packed8, 3, 4))
        p.bpm_sync = safe_enum(BpmSync, unpack_int(packed8, 1, 7))
        p.mod_speed = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.mod_depth = struct.unpack_from('b', data, offset)[0]; offset += 1
        p.motion_sequence_status = data[offset]; offset += 1
        p.sequence_data = SequenceData(data[offset:offset + NUM_SEQUENCE_DATA])
        offset += NUM_SEQUENCE_DATA
        p.sequence_data_gate = SequenceDataGate(data[offset:offset + NUM_SEQUENCE_DATA_GATE])
        return p

    def to_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_PARTS_AUDIOIN)
        offset = 0
        buf[offset] = int(self.filter_type); offset += 1
        struct.pack_into('b', buf, offset, self.cutoff); offset += 1
        buf[offset] = self.resonance; offset += 1
        struct.pack_into('b', buf, offset, self.eg_intensity); offset += 1
        buf[offset] = self.level; offset += 1
        struct.pack_into('b', buf, offset, self.pan); offset += 1
        buf[offset] = self.eg_time; offset += 1
        packed7 = 0
        packed7 = pack_int(packed7, int(self.fx_select), 2, 0)
        packed7 = pack_int(packed7, int(self.fx_send), 1, 2)
        packed7 = pack_int(packed7, int(self.roll), 1, 3)
        packed7 = pack_int(packed7, int(self.amp_eg), 1, 4)
        packed7 = pack_int(packed7, self.reserved_bits, 3, 5)
        buf[offset] = packed7 & 0xFF; offset += 1
        packed8 = 0
        packed8 = pack_int(packed8, int(self.mod_dest), 3, 0)
        packed8 = pack_int(packed8, self.reserved_bit_after_mod_depth, 1, 3)
        packed8 = pack_int(packed8, int(self.mod_type), 3, 4)
        packed8 = pack_int(packed8, int(self.bpm_sync), 1, 7)
        buf[offset] = packed8 & 0xFF; offset += 1
        struct.pack_into('b', buf, offset, self.mod_speed); offset += 1
        struct.pack_into('b', buf, offset, self.mod_depth); offset += 1
        buf[offset] = self.motion_sequence_status; offset += 1
        seq = self.sequence_data.to_bytes()
        buf[offset:offset + NUM_SEQUENCE_DATA] = seq[:NUM_SEQUENCE_DATA]
        offset += NUM_SEQUENCE_DATA
        gate = self.sequence_data_gate.to_bytes()
        buf[offset:offset + NUM_SEQUENCE_DATA_GATE] = gate[:NUM_SEQUENCE_DATA_GATE]
        return bytes(buf)


class PartAccent:
    def __init__(self):
        self.level = 0
        self.motion_sequence_status = 0
        self.sequence_data = SequenceData()

    @classmethod
    def from_bytes(cls, data: bytes) -> 'PartAccent':
        p = cls()
        offset = 0
        p.level = data[offset]; offset += 1
        p.motion_sequence_status = data[offset]; offset += 1
        p.sequence_data = SequenceData(data[offset:offset + NUM_SEQUENCE_DATA])
        return p

    def to_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_PARTS_ACCENT)
        offset = 0
        buf[offset] = self.level; offset += 1
        buf[offset] = self.motion_sequence_status; offset += 1
        seq = self.sequence_data.to_bytes()
        buf[offset:offset + NUM_SEQUENCE_DATA] = seq[:NUM_SEQUENCE_DATA]
        return bytes(buf)


class ParametersFx:
    def __init__(self):
        self.effect_type = FxType.COMPRESSOR
        self.edit1 = 0
        self.edit2 = 0
        self.motion_sequence_status = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ParametersFx':
        p = cls()
        p.effect_type = safe_enum(FxType, data[0])
        p.edit1 = data[1]
        p.edit2 = data[2]
        p.motion_sequence_status = data[3]
        return p

    def to_bytes(self) -> bytes:
        return bytes([int(self.effect_type), self.edit1, self.edit2, self.motion_sequence_status])


class ParametersMotion:
    def __init__(self):
        self.operation_number = 0
        self.operations = bytes(NUM_MOTION_OPERATIONS)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'ParametersMotion':
        p = cls()
        p.operation_number = struct.unpack_from('>h', data, 0)[0]
        p.operations = data[2:2 + NUM_MOTION_OPERATIONS]
        return p

    def to_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_PARAMETERS_MOTION)
        struct.pack_into('>h', buf, 0, self.operation_number)
        ops = self.operations[:NUM_MOTION_OPERATIONS]
        buf[2:2 + len(ops)] = ops
        return bytes(buf)


class Tempo:
    MIN_TEMPO = 20.0
    MAX_TEMPO = 300.0

    def __init__(self, value=120.0):
        self.value = value

    @classmethod
    def from_short(cls, short_val: int) -> 'Tempo':
        t = cls()
        # iiiiiiii i000ffff
        # 9 bits at position 7 = integer part, 4 bits at position 0 = decimal
        unsigned_val = short_val & 0xFFFF
        tempo_whole = (unsigned_val >> 7) & 0x1FF
        tempo_decimal = unsigned_val & 0x0F
        if tempo_decimal > 9:
            tempo_decimal = 0
        if tempo_whole < 20:
            tempo_whole = 20
        if tempo_whole > 300:
            tempo_whole = 300
        t.value = float(f"{tempo_whole}.{tempo_decimal}")
        return t

    def to_short(self) -> int:
        clamped = max(self.MIN_TEMPO, min(self.MAX_TEMPO, abs(self.value)))
        tempo_whole = int(clamped)
        tempo_decimal = round((clamped - tempo_whole) * 10)
        return (tempo_whole << 7) | tempo_decimal

    def __str__(self):
        return f"{self.value:.1f}"


class Pattern:
    def __init__(self):
        self.name = ''
        self.tempo = Tempo()
        self.swing = Swing.PERCENT_50
        self.pattern_length = PatternLength.LENGTH_1
        self.reserved_bit_after_pattern_length = 0
        self.beat = Beat.BEAT_16TH
        self.roll_type = RollType.ROLL_1_8
        self.fx_chain = FxChain.NONE
        self.last_step = LastStep.STEP_16
        self.arpeggiator_scale = ArpeggiatorScale.CHROMATIC
        self.reserved_bits_after_arp_scale = 0
        self.arpeggiator_center_note = 0
        self.mute_status = 0
        self.swing_status = 0
        self.output_bus_status = 0
        self.accent_status = 0
        self.drum_parts = []
        self.keyboard_parts = []
        self.stretch_slice_parts = []
        self.audio_in_part = None
        self.accent_part = None
        self.fx_parameters = []
        self.motion_parameters = []
        self.pattern_number = -1
        self._raw = None

    @classmethod
    def from_bytes(cls, data: bytes, pattern_number: int = -1) -> 'Pattern':
        p = cls()
        p._raw = data
        p.pattern_number = pattern_number
        offset = 0

        # bytes 0~7: name
        p.name = decode_name(data[0:8])
        offset = 8

        # bytes 8~9: tempo
        p.tempo = Tempo.from_short(struct.unpack_from('>h', data, offset)[0])
        offset += 2

        # byte 10: swing
        p.swing = safe_enum(Swing, data[offset]); offset += 1

        # byte 11: packed
        packed11 = data[offset]; offset += 1
        p.pattern_length = safe_enum(PatternLength, unpack_int(packed11, 3, 0))
        p.reserved_bit_after_pattern_length = unpack_int(packed11, 1, 3)
        p.beat = safe_enum(Beat, unpack_int(packed11, 2, 4))
        p.roll_type = safe_enum(RollType, unpack_int(packed11, 2, 6))

        # byte 12
        p.fx_chain = safe_enum(FxChain, data[offset]); offset += 1
        # byte 13
        p.last_step = safe_enum(LastStep, data[offset]); offset += 1
        # byte 14
        packed14 = data[offset]; offset += 1
        p.arpeggiator_scale = safe_enum(ArpeggiatorScale, unpack_int(packed14, 5, 0))
        p.reserved_bits_after_arp_scale = unpack_int(packed14, 3, 5)
        # byte 15
        p.arpeggiator_center_note = data[offset]; offset += 1
        # bytes 16~17
        p.mute_status = struct.unpack_from('>h', data, offset)[0]; offset += 2
        # bytes 18~19
        p.swing_status = struct.unpack_from('>h', data, offset)[0]; offset += 2
        # bytes 20~21
        p.output_bus_status = struct.unpack_from('>h', data, offset)[0]; offset += 2
        # bytes 22~23
        p.accent_status = struct.unpack_from('>h', data, offset)[0]; offset += 2

        # bytes 24~329: drum parts (9 x 34 bytes)
        for i in range(NUM_PARTS_DRUM):
            chunk = data[offset:offset + CHUNKSIZE_PARTS_DRUM]
            p.drum_parts.append(PartDrum.from_bytes(chunk))
            offset += CHUNKSIZE_PARTS_DRUM

        # bytes 330~877: keyboard parts (2 x 274 bytes)
        for i in range(NUM_PARTS_KEYBOARD):
            chunk = data[offset:offset + CHUNKSIZE_PARTS_KEYBOARD]
            p.keyboard_parts.append(PartKeyboard.from_bytes(chunk))
            offset += CHUNKSIZE_PARTS_KEYBOARD

        # bytes 878~973: stretch/slice parts (3 x 32 bytes)
        for i in range(NUM_PARTS_STRETCHSLICE):
            chunk = data[offset:offset + CHUNKSIZE_PARTS_STRETCHSLICE]
            p.stretch_slice_parts.append(PartStretchSlice.from_bytes(chunk))
            offset += CHUNKSIZE_PARTS_STRETCHSLICE

        # bytes 974~1129: audio in part (156 bytes)
        p.audio_in_part = PartAudioIn.from_bytes(data[offset:offset + CHUNKSIZE_PARTS_AUDIOIN])
        offset += CHUNKSIZE_PARTS_AUDIOIN

        # bytes 1130~1147: accent part (18 bytes)
        p.accent_part = PartAccent.from_bytes(data[offset:offset + CHUNKSIZE_PARTS_ACCENT])
        offset += CHUNKSIZE_PARTS_ACCENT

        # bytes 1148~1159: FX parameters (3 x 4 bytes)
        for i in range(NUM_PARAMETERS_FX):
            chunk = data[offset:offset + CHUNKSIZE_PARAMETERS_FX]
            p.fx_parameters.append(ParametersFx.from_bytes(chunk))
            offset += CHUNKSIZE_PARAMETERS_FX

        # bytes 1160~4279: motion parameters (24 x 130 bytes)
        for i in range(NUM_PARAMETERS_MOTION):
            chunk = data[offset:offset + CHUNKSIZE_PARAMETERS_MOTION]
            p.motion_parameters.append(ParametersMotion.from_bytes(chunk))
            offset += CHUNKSIZE_PARAMETERS_MOTION

        return p

    def is_empty(self) -> bool:
        return not self.name.strip('\x00').strip()

    def to_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_PATTERN)
        offset = 0

        # name
        name_bytes = encode_name(self.name, 8, 0x00)
        buf[0:8] = name_bytes
        offset = 8

        # tempo
        struct.pack_into('>h', buf, offset, self.tempo.to_short()); offset += 2
        # swing
        buf[offset] = int(self.swing); offset += 1
        # packed11
        packed11 = 0
        packed11 = pack_int(packed11, int(self.pattern_length), 3, 0)
        packed11 = pack_int(packed11, self.reserved_bit_after_pattern_length, 1, 3)
        packed11 = pack_int(packed11, int(self.beat), 2, 4)
        packed11 = pack_int(packed11, int(self.roll_type), 2, 6)
        buf[offset] = packed11 & 0xFF; offset += 1
        buf[offset] = int(self.fx_chain); offset += 1
        buf[offset] = int(self.last_step); offset += 1
        packed14 = 0
        packed14 = pack_int(packed14, int(self.arpeggiator_scale), 5, 0)
        packed14 = pack_int(packed14, self.reserved_bits_after_arp_scale, 3, 5)
        buf[offset] = packed14 & 0xFF; offset += 1
        buf[offset] = self.arpeggiator_center_note; offset += 1
        struct.pack_into('>h', buf, offset, self.mute_status); offset += 2
        struct.pack_into('>h', buf, offset, self.swing_status); offset += 2
        struct.pack_into('>h', buf, offset, self.output_bus_status); offset += 2
        struct.pack_into('>h', buf, offset, self.accent_status); offset += 2

        for dp in self.drum_parts:
            d = dp.to_bytes()
            buf[offset:offset + CHUNKSIZE_PARTS_DRUM] = d
            offset += CHUNKSIZE_PARTS_DRUM

        for kp in self.keyboard_parts:
            k = kp.to_bytes()
            buf[offset:offset + CHUNKSIZE_PARTS_KEYBOARD] = k
            offset += CHUNKSIZE_PARTS_KEYBOARD

        for sp in self.stretch_slice_parts:
            s = sp.to_bytes()
            buf[offset:offset + CHUNKSIZE_PARTS_STRETCHSLICE] = s
            offset += CHUNKSIZE_PARTS_STRETCHSLICE

        if self.audio_in_part:
            a = self.audio_in_part.to_bytes()
            buf[offset:offset + CHUNKSIZE_PARTS_AUDIOIN] = a
        offset += CHUNKSIZE_PARTS_AUDIOIN

        if self.accent_part:
            a = self.accent_part.to_bytes()
            buf[offset:offset + CHUNKSIZE_PARTS_ACCENT] = a
        offset += CHUNKSIZE_PARTS_ACCENT

        for fx in self.fx_parameters:
            f = fx.to_bytes()
            buf[offset:offset + CHUNKSIZE_PARAMETERS_FX] = f
            offset += CHUNKSIZE_PARAMETERS_FX

        for mo in self.motion_parameters:
            m = mo.to_bytes()
            buf[offset:offset + CHUNKSIZE_PARAMETERS_MOTION] = m
            offset += CHUNKSIZE_PARAMETERS_MOTION

        return bytes(buf)

    def label(self) -> str:
        return f"{self.pattern_number} - {self.name}"
