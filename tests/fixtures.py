"""Artificial structural fixtures; no measured data or private header contents.

Small dimensions, labels, padding, and pixel values are test inputs deliberately
chosen to exercise relocation, ordering, signedness, and malformed-file guards.
They are not claims about instrument output. The binary layout follows docs/format.md.
The encoder is independent of the reader's parser constants.
"""

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


@dataclass
class Fixture:
    path: Path
    raw: bytes
    arrays: NDArray[np.uint16]
    records: tuple[int, ...]
    tables: tuple[int, ...]
    payload: int


def make_fixture(
    path: Path,
    *,
    side: int = 4,
    acquisitions: int = 3,
    labels: tuple[str, ...] = ("synthetic-A", "synthetic-B"),
    padding: int = 36,
) -> Fixture:
    channels = len(labels)
    sections = (84, 100, 116, 132, 148, 164, 168 + channels * 268)
    records = tuple(168 + index * 268 for index in range(channels))
    table_size = 72 + acquisitions * 4
    tables = tuple(sections[-1] + 16 + index * table_size for index in range(channels))
    payload = tables[-1] + table_size + padding
    plane_bytes = side * side * 2
    raw = bytearray(payload + acquisitions * channels * plane_bytes)
    struct.pack_into("<21i", raw, 0, 4201, *sections, *([-1] * 13))
    struct.pack_into("<i", raw, sections[5], channels)
    arrays = np.arange(acquisitions * channels * side * side, dtype="<u2").reshape(
        acquisitions, channels, side, side
    )
    # Explicit edge cases prove no signed conversion and no zero-as-missing policy.
    arrays[0, 0, 0, 0] = 0
    arrays[-1, -1, -1, -1] = np.iinfo(np.uint16).max
    for channel, (record, table, label) in enumerate(zip(records, tables, labels)):
        struct.pack_into("<3i", raw, record, 100, 268, table)
        encoded = label.encode("ascii")
        raw[record + 12 : record + 12 + len(encoded)] = encoded
        struct.pack_into("<18i", raw, table, 103, 72, 1, acquisitions, plane_bytes, 4, *([0] * 12))
        for index in range(acquisitions):
            pointer = payload + (index * channels + channel) * plane_bytes
            struct.pack_into("<i", raw, table + 72 + 4 * index, pointer)
            raw[pointer : pointer + plane_bytes] = arrays[index, channel].tobytes()
    path.write_bytes(raw)
    return Fixture(path, bytes(raw), arrays, records, tables, payload)
