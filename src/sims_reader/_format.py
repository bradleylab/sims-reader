"""Structural parser for the observed 4201 layout; see README.md.

Marker values and field positions originate in the specimen investigation.
The parser derives the header boundary from pointers, without fixed file offsets.
"""

import struct
from math import isqrt
from typing import BinaryIO

from .models import Channel, FormatError, ImageMetadata, UnsupportedFormatError

SIGNATURE = 4201
DIRECTORY_BYTES = 84
CHANNEL_DIRECTORY_INDEX = 6
ACTIVE_SECTION_COUNT = 7
CHANNEL_RECORD_MARKER = 100
CHANNEL_RECORD_BYTES = 268
CHANNEL_NAME_OFFSET = 12
TABLE_MARKER = 103
TABLE_HEADER_BYTES = 72
# Only the two measured variable fields (plane count and byte length) are generalized.
TABLE_FIXED_PREFIX = (TABLE_MARKER, TABLE_HEADER_BYTES, 1)
TABLE_FIXED_SUFFIX = (4,) + (0,) * 12
CANDIDATE_PIXEL_BYTES = 2


class _BoundedReader:
    def __init__(self, stream: BinaryIO, size: int):
        self.stream = stream
        self.size = size
        self.metadata_end = 0

    def read(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset > self.size - length:
            raise FormatError(f"Metadata read outside file bounds: offset={offset}, bytes={length}")
        self.stream.seek(offset)
        result = self.stream.read(length)
        if len(result) != length:
            raise FormatError(f"Truncated metadata at byte {offset}")
        self.metadata_end = max(self.metadata_end, offset + length)
        return result

    def words(self, offset: int, count: int) -> tuple[int, ...]:
        return struct.unpack(f"<{count}i", self.read(offset, count * 4))


def _directory(reader: _BoundedReader) -> tuple[int, ...]:
    signature, first_section = reader.words(0, 2)
    if signature != SIGNATURE or first_section != DIRECTORY_BYTES:
        raise UnsupportedFormatError(
            f"Unsupported signature/directory ({signature}, {first_section}); "
            "only the investigated 4201 layout with an 84-byte directory is supported"
        )
    directory = reader.words(0, DIRECTORY_BYTES // 4)
    sections = directory[1 : ACTIVE_SECTION_COUNT + 1]
    if any(pointer < DIRECTORY_BYTES or pointer >= reader.size for pointer in sections):
        raise FormatError("Top-level section pointer outside file bounds")
    if any(left >= right for left, right in zip(sections, sections[1:])):
        raise FormatError("Top-level section pointers are not strictly increasing")
    if any(value != -1 for value in directory[ACTIVE_SECTION_COUNT + 1 :]):
        raise UnsupportedFormatError("Additional top-level sections are not yet supported")
    return directory


def _channel(reader: _BoundedReader, record: int, index: int) -> Channel:
    marker, record_bytes, table = reader.words(record, 3)
    if (marker, record_bytes) != (CHANNEL_RECORD_MARKER, CHANNEL_RECORD_BYTES):
        raise UnsupportedFormatError(f"Unsupported channel record at byte {record}")
    raw_record = reader.read(record, record_bytes)
    label_bytes = raw_record[CHANNEL_NAME_OFFSET:]
    if b"\0" not in label_bytes:
        raise FormatError(f"Unterminated channel label at byte {record}")
    try:
        label = label_bytes.split(b"\0", 1)[0].decode("ascii", errors="strict")
    except UnicodeDecodeError as error:
        raise UnsupportedFormatError(
            "Non-ASCII channel label; no lossy decoding performed"
        ) from error
    table_words = reader.words(table, TABLE_HEADER_BYTES // 4)
    if table_words[:3] != TABLE_FIXED_PREFIX or table_words[5:] != TABLE_FIXED_SUFFIX:
        raise UnsupportedFormatError(f"Unsupported image table at byte {table}")
    planes, plane_bytes = table_words[3:5]
    if planes <= 0 or plane_bytes <= 0:
        raise FormatError("Image count and block length must be positive")
    pointer_start = table + TABLE_HEADER_BYTES
    first_pointer = reader.words(pointer_start, 1)[0]
    # A pointer table must fit entirely before its own first image. This also
    # prevents an untrusted count from requesting more bytes than are available.
    if planes > (first_pointer - pointer_start) // 4 or first_pointer > reader.size:
        raise FormatError("Image pointer table cannot fit before the first image")
    offsets = reader.words(pointer_start, planes)
    if any(left >= right for left, right in zip(offsets, offsets[1:])):
        raise FormatError("Image offsets are not strictly increasing within a channel")
    if any(offset < 0 or offset > reader.size - plane_bytes for offset in offsets):
        raise FormatError("Image block outside file bounds; source may be truncated")
    return Channel(index, label, label_bytes, record, table, table_words, plane_bytes, offsets)


def parse(stream: BinaryIO, size: int) -> ImageMetadata:
    """Parse and validate metadata without reading image payloads.

    Parameters
    ----------
    stream
        Seekable binary stream opened for reading.
    size
        Length of that stream in bytes.

    Returns
    -------
    ImageMetadata
        Pointer-derived layout with provisional image interpretation.
    """
    reader = _BoundedReader(stream, size)
    directory = _directory(reader)
    section = directory[CHANNEL_DIRECTORY_INDEX]
    next_section = directory[CHANNEL_DIRECTORY_INDEX + 1]
    count = reader.words(section, 1)[0]
    if not 0 < count <= (next_section - section - 4) // CHANNEL_RECORD_BYTES:
        raise FormatError("Channel records do not fit in their directory section")
    channels = tuple(
        _channel(reader, section + 4 + index * CHANNEL_RECORD_BYTES, index)
        for index in range(count)
    )
    first = channels[0]
    if any(
        channel.plane_bytes != first.plane_bytes
        or len(channel.plane_offsets) != len(first.plane_offsets)
        for channel in channels
    ):
        raise UnsupportedFormatError(
            "Unequal channel shapes or acquisition counts are not supported"
        )
    header_bytes = min(channel.plane_offsets[0] for channel in channels)
    if reader.metadata_end > header_bytes or any(
        pointer >= header_bytes for pointer in directory[1 : ACTIVE_SECTION_COUNT + 1]
    ):
        raise FormatError("Metadata overlaps image payload")
    # Verify every offset against the observed acquisition-major/channel-minor
    # storage order, accounting for the entire payload with no skipped bytes.
    for channel in channels:
        for acquisition, offset in enumerate(channel.plane_offsets):
            expected = header_bytes + (acquisition * count + channel.index) * first.plane_bytes
            if offset != expected:
                raise FormatError("Gap, overlap, or unsupported interleaving in image pointers")
    if header_bytes + count * len(first.plane_offsets) * first.plane_bytes != size:
        raise FormatError("Payload does not end at EOF; trailing or missing bytes are unsupported")
    side = isqrt(first.plane_bytes // CANDIDATE_PIXEL_BYTES)
    if side * side * CANDIDATE_PIXEL_BYTES != first.plane_bytes:
        raise UnsupportedFormatError("Block length does not fit the provisional square-u16 model")
    return ImageMetadata(size, header_bytes, directory, channels, (side, side))
