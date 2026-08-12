import struct
from .constants import (
    CHUNKSIZE_GLOBAL_PARAMETERS, NUM_MIDI_CHANNELS, NUM_PART_NOTE_NUMBERS,
    NUM_MIDI_CONTROL_CHANGE_ASSIGNMENTS, NUM_PATTERN_SET_PARAMETERS,
    EnabledFlag, ArpeggiatorControl, AudioInMode, MidiClock, PitchBendRange,
    MidiChannel, MIDI_CHANNEL_TYPE_NAMES, PART_NOTE_NUMBER_NAMES, MIDI_CC_ASSIGNMENT_NAMES
)
from .utils import unpack_int, pack_int, safe_enum


class MidiChannelType:
    def __init__(self, name='', channel=MidiChannel.CHANNEL_1):
        self.name = name
        self.channel = channel


class PartNoteNumber:
    def __init__(self, name='', note_number=0):
        self.name = name
        self.note_number = note_number


class MidiControlChangeAssignment:
    def __init__(self, name='', value=0):
        self.name = name
        self.value = value


class PatternSetParameter:
    def __init__(self, pattern_pointer=0):
        self.pattern_pointer = pattern_pointer


class GlobalParameters:
    def __init__(self):
        self.memory_protect_enabled = EnabledFlag.DISABLED
        self.reserved_byte = 0
        self.arpeggiator_control = ArpeggiatorControl.NORMAL
        self.audio_in_mode = AudioInMode.MONO
        self.midi_clock = MidiClock.INT
        self.note_message_enabled = EnabledFlag.DISABLED
        self.system_ex_enabled = EnabledFlag.DISABLED
        self.control_change_enabled = EnabledFlag.DISABLED
        self.program_change_enabled = EnabledFlag.DISABLED
        self.reserved_bits_after_program_change = 0
        self.pitch_bend_range = PitchBendRange.PITCH_BEND_N12
        self.midi_channels = []
        self.part_note_numbers = []
        self.midi_cc_assignments = []
        self.reserved_long = 0
        self.pattern_set_parameters = []

    @classmethod
    def from_bytes(cls, data: bytes) -> 'GlobalParameters':
        gp = cls()
        offset = 0

        # byte 0
        gp.memory_protect_enabled = safe_enum(EnabledFlag, data[offset]); offset += 1
        # byte 1
        gp.reserved_byte = data[offset]; offset += 1
        # byte 2
        gp.arpeggiator_control = safe_enum(ArpeggiatorControl, data[offset]); offset += 1
        # byte 3
        gp.audio_in_mode = safe_enum(AudioInMode, data[offset]); offset += 1
        # byte 4
        gp.midi_clock = safe_enum(MidiClock, data[offset]); offset += 1
        # byte 5 - packed bits
        packed5 = data[offset]; offset += 1
        gp.note_message_enabled = safe_enum(EnabledFlag, unpack_int(packed5, 1, 0))
        gp.system_ex_enabled = safe_enum(EnabledFlag, unpack_int(packed5, 1, 1))
        gp.control_change_enabled = safe_enum(EnabledFlag, unpack_int(packed5, 1, 2))
        gp.program_change_enabled = safe_enum(EnabledFlag, unpack_int(packed5, 1, 3))
        gp.reserved_bits_after_program_change = unpack_int(packed5, 4, 4)
        # byte 6
        gp.pitch_bend_range = safe_enum(PitchBendRange, data[offset]); offset += 1
        # bytes 7~9 - MIDI channels
        for i in range(NUM_MIDI_CHANNELS):
            name = MIDI_CHANNEL_TYPE_NAMES[i] if i < len(MIDI_CHANNEL_TYPE_NAMES) else f"Channel{i}"
            ch = safe_enum(MidiChannel, data[offset]); offset += 1
            gp.midi_channels.append(MidiChannelType(name, ch))
        # bytes 10~22 - part note numbers
        for i in range(NUM_PART_NOTE_NUMBERS):
            name = PART_NOTE_NUMBER_NAMES[i] if i < len(PART_NOTE_NUMBER_NAMES) else f"Part{i}"
            nn = data[offset]; offset += 1
            gp.part_note_numbers.append(PartNoteNumber(name, nn))
        # bytes 23~55 - MIDI CC assignments
        for i in range(NUM_MIDI_CONTROL_CHANGE_ASSIGNMENTS):
            name = MIDI_CC_ASSIGNMENT_NAMES[i] if i < len(MIDI_CC_ASSIGNMENT_NAMES) else f"CC{i}"
            val = struct.unpack_from('b', data, offset)[0]; offset += 1
            gp.midi_cc_assignments.append(MidiControlChangeAssignment(name, val))
        # bytes 56~63 - reserved long
        gp.reserved_long = struct.unpack_from('>q', data, offset)[0]; offset += 8
        # bytes 64~191 - pattern set parameters
        for i in range(NUM_PATTERN_SET_PARAMETERS):
            ptr = data[offset]; offset += 1
            gp.pattern_set_parameters.append(PatternSetParameter(ptr))

        return gp

    def to_bytes(self) -> bytes:
        buf = bytearray(CHUNKSIZE_GLOBAL_PARAMETERS)
        offset = 0

        buf[offset] = int(self.memory_protect_enabled); offset += 1
        buf[offset] = self.reserved_byte & 0xFF; offset += 1
        buf[offset] = int(self.arpeggiator_control); offset += 1
        buf[offset] = int(self.audio_in_mode); offset += 1
        buf[offset] = int(self.midi_clock); offset += 1

        packed5 = 0
        packed5 = pack_int(packed5, int(self.note_message_enabled), 1, 0)
        packed5 = pack_int(packed5, int(self.system_ex_enabled), 1, 1)
        packed5 = pack_int(packed5, int(self.control_change_enabled), 1, 2)
        packed5 = pack_int(packed5, int(self.program_change_enabled), 1, 3)
        packed5 = pack_int(packed5, self.reserved_bits_after_program_change, 4, 4)
        buf[offset] = packed5 & 0xFF; offset += 1

        buf[offset] = int(self.pitch_bend_range); offset += 1

        for mch in self.midi_channels:
            buf[offset] = int(mch.channel); offset += 1

        for pnn in self.part_note_numbers:
            buf[offset] = pnn.note_number & 0xFF; offset += 1

        for cc in self.midi_cc_assignments:
            buf[offset] = cc.value & 0xFF; offset += 1

        struct.pack_into('>q', buf, offset, self.reserved_long); offset += 8

        for psp in self.pattern_set_parameters:
            buf[offset] = psp.pattern_pointer & 0xFF; offset += 1

        return bytes(buf)
