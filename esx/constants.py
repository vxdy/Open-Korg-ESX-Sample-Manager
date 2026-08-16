from enum import IntEnum

# File addresses
ADDR_VALID_ESX_CHECK_1 = 0x00000000
ADDR_GLOBAL_PARAMETERS = 0x00000020
ADDR_PATTERN_DATA = 0x00000200
ADDR_SONG_DATA = 0x00130000
ADDR_SONG_EVENT_DATA = 0x00138400
ADDR_VALID_ESX_CHECK_2 = 0x001B0000
ADDR_NUM_MONO_SAMPLES = 0x001B0020
ADDR_NUM_STEREO_SAMPLES = 0x001B0024
ADDR_CURRENT_OFFSET = 0x001B0028
ADDR_SAMPLE_HEADER_MONO = 0x001B0100
ADDR_SAMPLE_HEADER_STEREO = 0x001B2900
ADDR_SLICE_DATA = 0x001B4200
ADDR_SAMPLE_DATA = 0x00250000

# Pattern offsets (within a pattern chunk)
PATTERN_OFFSET_PARTS_DRUM = 24
PATTERN_OFFSET_PARTS_KEYBOARD = 330
PATTERN_OFFSET_PARTS_STRETCHSLICE = 878
PATTERN_OFFSET_PARTS_AUDIOIN = 974
PATTERN_OFFSET_PARTS_ACCENT = 1130
PATTERN_OFFSET_PARAMETERS_FX = 1148
PATTERN_OFFSET_PARAMETERS_MOTION = 1160

# Chunk sizes
CHUNKSIZE_GLOBAL_PARAMETERS = 192
CHUNKSIZE_PATTERN = 4280
CHUNKSIZE_SONG = 528
CHUNKSIZE_SONG_EVENT = 8
CHUNKSIZE_SAMPLE_HEADER_MONO = 40
CHUNKSIZE_SAMPLE_HEADER_STEREO = 44
CHUNKSIZE_PARAMETERS_FX = 4
CHUNKSIZE_PARAMETERS_MOTION = 130
CHUNKSIZE_PARTS_DRUM = 34
CHUNKSIZE_PARTS_KEYBOARD = 274
CHUNKSIZE_PARTS_STRETCHSLICE = 32
CHUNKSIZE_PARTS_ACCENT = 18
CHUNKSIZE_PARTS_AUDIOIN = 156
CHUNKSIZE_SLICE_DATA = 2048

# Counts
NUM_MIDI_CHANNELS = 3
NUM_PART_NOTE_NUMBERS = 13
NUM_MIDI_CONTROL_CHANGE_ASSIGNMENTS = 33
NUM_PATTERN_SET_PARAMETERS = 128
NUM_PATTERNS = 256
NUM_SONGS = 64
NUM_SONG_PATTERNS = 256
NUM_SAMPLES_MONO = 256
NUM_SAMPLES_STEREO = 128
NUM_SAMPLES = NUM_SAMPLES_MONO + NUM_SAMPLES_STEREO
NUM_PARAMETERS_FX = 3
NUM_PARAMETERS_MOTION = 24
NUM_MOTION_OPERATIONS = 128
NUM_PARTS = 16
NUM_PARTS_DRUM = 9
NUM_PARTS_KEYBOARD = 2
NUM_PARTS_STRETCHSLICE = 3
NUM_PARTS_ACCENT = 1
NUM_PARTS_AUDIOIN = 1
NUM_SEQUENCE_DATA = 16
NUM_SEQUENCE_DATA_GATE = 128
NUM_SEQUENCE_DATA_NOTE = 128
NUM_SLICE_DATA = 256

DEFAULT_SAMPLING_RATE = 44100
MAX_SAMPLE_MEM_IN_FRAMES = 0xC00000
MAX_SAMPLE_MEM_IN_BYTES = MAX_SAMPLE_MEM_IN_FRAMES * 2
MAX_NUM_SONG_EVENTS = 20000
SIZE_FILE_MIN = 0x00250010
SIZE_FILE_MAX = SIZE_FILE_MIN + MAX_SAMPLE_MEM_IN_BYTES


class AmpEg(IntEnum):
    GATE = 0
    EG = 1


class ArpeggiatorControl(IntEnum):
    NORMAL = 0
    REVERSE = 1


class ArpeggiatorScale(IntEnum):
    CHROMATIC = 0
    MAJOR = 1
    MINOR = 2
    PENTA_MAJOR = 3
    PENTA_MINOR = 4
    WHOLE_TONE = 5
    DIMINISH = 6
    H_DIMINISH = 7
    HARMONIC_MINOR = 8
    ALTERED = 9
    DORIAN = 10
    PHRYGIAN = 11
    LYDIAN = 12
    MIXOLYDIAN = 13
    LOCRIAN = 14
    BLUES_SCALE = 15
    RYUKYU = 16
    KAEDE = 17
    USER = 18


class AudioInMode(IntEnum):
    MONO = 0
    STEREO = 1


class Beat(IntEnum):
    BEAT_16TH = 0
    BEAT_32ND = 1
    BEAT_8TRI = 2
    BEAT_16TRI = 3


class BpmSync(IntEnum):
    OFF = 0
    ON = 1


class EnabledFlag(IntEnum):
    DISABLED = 0
    ENABLED = 1


class FilterType(IntEnum):
    LPF = 0
    HPF = 1
    BPF = 2
    BPF_PLUS = 3
    LOWPASS_12DB = 0
    LOWPASS_24DB = 1
    HIGHPASS_12DB = 1
    BANDPASS_12DB = 2


class FxChain(IntEnum):
    NONE = 0
    FX_12 = 1
    FX_23 = 2
    FX_123 = 3


class FxSelect(IntEnum):
    FX1 = 0
    FX2 = 1
    FX3 = 2


class FxSend(IntEnum):
    OFF = 0
    ON = 1


class FxType(IntEnum):
    REVERB = 0
    BPM_SYNC_DELAY = 1
    SHORT_DELAY = 2
    MOD_DELAY = 3
    GRAIN_SHIFTER = 4
    CHO_FLG = 5
    PHASER = 6
    RING_MOD = 7
    TALKING_MOD = 8
    PITCH_SHIFTER = 9
    COMPRESSOR = 10
    DISTORTION = 11
    DECIMATOR = 12
    EQ = 13
    LPF = 14
    HPF = 15


class LastStep(IntEnum):
    STEP_1 = 0
    STEP_2 = 1
    STEP_3 = 2
    STEP_4 = 3
    STEP_5 = 4
    STEP_6 = 5
    STEP_7 = 6
    STEP_8 = 7
    STEP_9 = 8
    STEP_10 = 9
    STEP_11 = 10
    STEP_12 = 11
    STEP_13 = 12
    STEP_14 = 13
    STEP_15 = 14
    STEP_16 = 15
    STEP_17 = 16
    STEP_18 = 17
    STEP_19 = 18
    STEP_20 = 19
    STEP_21 = 20
    STEP_22 = 21
    STEP_23 = 22
    STEP_24 = 23
    STEP_25 = 24
    STEP_26 = 25
    STEP_27 = 26
    STEP_28 = 27
    STEP_29 = 28
    STEP_30 = 29
    STEP_31 = 30
    STEP_32 = 31


class LoopType(IntEnum):
    NO = 0
    YES = 1
    IF_MONO = 2


class MidiChannel(IntEnum):
    CHANNEL_1 = 0
    CHANNEL_2 = 1
    CHANNEL_3 = 2
    CHANNEL_4 = 3
    CHANNEL_5 = 4
    CHANNEL_6 = 5
    CHANNEL_7 = 6
    CHANNEL_8 = 7
    CHANNEL_9 = 8
    CHANNEL_10 = 9
    CHANNEL_11 = 10
    CHANNEL_12 = 11
    CHANNEL_13 = 12
    CHANNEL_14 = 13
    CHANNEL_15 = 14
    CHANNEL_16 = 15
    OFF = 16


class MidiClock(IntEnum):
    INT = 0
    EXT = 1


class ModDest(IntEnum):
    PITCH = 0
    FILTER_CUTOFF = 1
    AMP = 2
    PAN = 3


class ModType(IntEnum):
    SAWTOOTH = 0
    SQUARE = 1
    TRIANGLE = 2
    S_AND_H = 3
    ENVELOPE = 4
    EG = 4


class MotionSequenceStatus(IntEnum):
    OFF = 0
    ON = 1
    SMOOTH = 2


class MuteHold(IntEnum):
    OFF = 0
    ON = 1


class PatternLength(IntEnum):
    LENGTH_1 = 0
    LENGTH_2 = 1
    LENGTH_3 = 2
    LENGTH_4 = 3
    LENGTH_5 = 4
    LENGTH_6 = 5
    LENGTH_7 = 6
    LENGTH_8 = 7


class PitchBendRange(IntEnum):
    PITCH_BEND_N12 = 0
    PITCH_BEND_N11 = 1
    PITCH_BEND_N10 = 2
    PITCH_BEND_N9 = 3
    PITCH_BEND_N8 = 4
    PITCH_BEND_N7 = 5
    PITCH_BEND_N6 = 6
    PITCH_BEND_N5 = 7
    PITCH_BEND_N4 = 8
    PITCH_BEND_N3 = 9
    PITCH_BEND_N2 = 10
    PITCH_BEND_N1 = 11
    PITCH_BEND_0 = 12
    PITCH_BEND_P1 = 13
    PITCH_BEND_P2 = 14
    PITCH_BEND_P3 = 15
    PITCH_BEND_P4 = 16
    PITCH_BEND_P5 = 17
    PITCH_BEND_P6 = 18
    PITCH_BEND_P7 = 19
    PITCH_BEND_P8 = 20
    PITCH_BEND_P9 = 21
    PITCH_BEND_P10 = 22
    PITCH_BEND_P11 = 23
    PITCH_BEND_P12 = 24


class Reverse(IntEnum):
    OFF = 0
    ON = 1


class Roll(IntEnum):
    OFF = 0
    ON = 1


class RollType(IntEnum):
    ROLL_1_8 = 0
    ROLL_1_12 = 1
    ROLL_1_16 = 2
    ROLL_1_32 = 3


class Swing(IntEnum):
    PERCENT_50 = 0
    PERCENT_51 = 1
    PERCENT_52 = 2
    PERCENT_53 = 3
    PERCENT_54 = 4
    PERCENT_55 = 5
    PERCENT_56 = 6
    PERCENT_57 = 7
    PERCENT_58 = 8
    PERCENT_59 = 9
    PERCENT_60 = 10
    PERCENT_61 = 11
    PERCENT_62 = 12
    PERCENT_63 = 13
    PERCENT_64 = 14
    PERCENT_65 = 15
    PERCENT_66 = 16
    PERCENT_67 = 17
    PERCENT_68 = 18
    PERCENT_69 = 19
    PERCENT_70 = 20
    PERCENT_71 = 21
    PERCENT_72 = 22
    PERCENT_73 = 23
    PERCENT_74 = 24
    PERCENT_75 = 25


StretchStep = IntEnum(
    'StretchStep',
    {'OFF': -1, **{f'STEP_{step}': step - 1 for step in range(1, 129)}}
)


class TempoLock(IntEnum):
    OFF = 0
    ON = 1


class PlayLevel(IntEnum):
    DB_0 = 0
    DB_12 = 1

    @classmethod
    def safe_get(cls, value):
        try:
            return cls(value & 0x7F)
        except ValueError:
            return cls.DB_0


# Note number labels (MIDI)
NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

MIDI_CHANNEL_TYPE_NAMES = [
    "Global", "Drum", "Keyboard"
]

PART_NOTE_NUMBER_NAMES = [
    "Drum1", "Drum2", "Drum3", "Drum4", "Drum5",
    "Drum6", "Drum7", "Drum8", "Drum9",
    "Keyboard1", "Keyboard2", "AudioIn", "Accent"
]

PATTERN_PART_NAMES = [
    "Drum1", "Drum2", "Drum3", "Drum4", "Drum5",
    "Drum6a", "Drum6b", "Drum7a", "Drum7b",
    "Accent", "Keyboard1", "Keyboard2",
    "Stretch1", "Stretch2", "Slice", "AudioIn"
]

MIDI_CC_ASSIGNMENT_NAMES = [
    "VolumeCC", "PanCC", "Cutoff", "Resonance",
    "AmpAttack", "AmpDecay", "ModDepth", "ModRate",
    "LfoDepth", "LfoRate", "Pitch", "Start",
    "End", "LoopStart", "Level", "Tune",
    "EgAttack", "EgDecay", "CC18", "CC19",
    "CC20", "CC21", "CC22", "CC23",
    "CC24", "CC25", "CC26", "CC27",
    "CC28", "CC29", "CC30", "CC31",
    "CC32"
]
