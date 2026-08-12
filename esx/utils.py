import struct


def unpack_int(packed_int, num_bits, num_shifted_left):
    bits_unshifted = (1 << num_bits) - 1
    bits_shifted = bits_unshifted << num_shifted_left
    output_value = packed_int & bits_shifted
    return output_value >> num_shifted_left


def pack_int(packed_int, input_value, num_bits, num_shifted_left):
    bits_unshifted = (1 << num_bits) - 1
    bits_shifted = bits_unshifted << num_shifted_left
    shifted_input = input_value << num_shifted_left
    packed_int = packed_int & (~bits_shifted & 0xFF)
    packed_int = packed_int | shifted_input
    return packed_int


def read_bytes(data, offset, length):
    return data[offset:offset + length]


def read_byte(data, offset):
    return struct.unpack_from('B', data, offset)[0]


def read_sbyte(data, offset):
    return struct.unpack_from('b', data, offset)[0]


def read_short_be(data, offset):
    return struct.unpack_from('>h', data, offset)[0]


def read_ushort_be(data, offset):
    return struct.unpack_from('>H', data, offset)[0]


def read_int_be(data, offset):
    return struct.unpack_from('>i', data, offset)[0]


def read_long_be(data, offset):
    return struct.unpack_from('>q', data, offset)[0]


def decode_name(data, max_len=8):
    try:
        return data[:max_len].decode('ascii', errors='replace').rstrip('\x00')
    except Exception:
        return ''


def encode_name(name, length, fill_byte=0x00):
    b = bytearray(length)
    encoded = name.encode('ascii', errors='replace')
    for i in range(min(len(encoded), length)):
        b[i] = encoded[i]
    for i in range(len(encoded), length):
        b[i] = fill_byte
    return bytes(b)


class UnknownEnumValue(int):
    """An int-like stand-in for a byte that doesn't map to any known enum member.

    Real ESX files contain enum-coded bytes outside the ranges we've reverse
    engineered (e.g. sample stretch-step bytes of 0x80 in factory data). Silently
    collapsing those to a default value (as a plain lookup-with-fallback would)
    means every save rewrites them to something else, corrupting fields the user
    never touched. Keeping the raw byte here - while still behaving like a plain
    int for packing/comparison and exposing .name for UI code - makes unmodified
    fields round-trip byte-for-byte.
    """

    def __new__(cls, value):
        return int.__new__(cls, value)

    @property
    def name(self):
        return f"UNKNOWN_{int(self)}"


def safe_enum(enum_class, value):
    try:
        return enum_class(value)
    except (ValueError, KeyError):
        pass
    if isinstance(value, int) and value > 127:
        try:
            return enum_class(value - 256)
        except (ValueError, KeyError):
            pass
    return UnknownEnumValue(value)
