"""Read-only, per-plane access with source integrity and provisional status."""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from types import TracebackType
from typing import BinaryIO, Iterator, Self

import numpy as np
from numpy.typing import NDArray

from ._format import parse
from .models import Channel, ProvisionalFormatError, SourceChangedError


def _identity(stream: BinaryIO) -> tuple[int, ...]:
    info = os.fstat(stream.fileno())
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


class ImageFile:
    """Inspect the observed Cameca layout and retrieve individual image planes.

    Parameters
    ----------
    path
        Source file. It is opened read-only and held until ``close``.
    accept_provisional
        Explicitly allow the candidate square, little-endian u16 interpretation.
        Metadata inspection is permitted without this opt-in.

    Notes
    -----
    Use as a context manager. Instances are not thread-safe. Metadata are frozen;
    arrays are read-only snapshots, independent of the open file's lifetime.
    The source must remain unchanged while open. This guard detects normal file
    changes, not adversarial modifications that restore filesystem metadata.
    """

    def __init__(self, path: str | Path, *, accept_provisional: bool = False):
        self.path = Path(path).resolve()
        self._stream = self.path.open("rb")
        try:
            if not stat.S_ISREG(os.fstat(self._stream.fileno()).st_mode):
                raise ValueError("Input must be a regular file")
            self._source_identity = _identity(self._stream)
            self.metadata = parse(self._stream, self._source_identity[2])
            self._accept_provisional = accept_provisional
            self._check_source()
        except BaseException:
            self._stream.close()
            raise

    def __enter__(self) -> Self:
        self._check_source()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the source handle; previously returned arrays remain usable."""
        self._stream.close()

    def _check_source(self) -> None:
        if self._stream.closed:
            raise ValueError("ImageFile is closed")
        if _identity(self._stream) != self._source_identity:
            raise SourceChangedError("Source changed after inspection; reopen and revalidate it")

    def _read(self, offset: int, length: int) -> bytes:
        self._check_source()
        self._stream.seek(offset)
        result = self._stream.read(length)
        self._check_source()
        if len(result) != length:
            raise SourceChangedError("Short read after metadata validation")
        return result

    def channel(self, selector: str | int) -> Channel:
        """Select a channel by zero-based index or exact, unambiguous stored label."""
        if isinstance(selector, bool):
            raise TypeError("Channel selector must be an integer index or a label")
        if isinstance(selector, int):
            if not 0 <= selector < len(self.metadata.channels):
                raise IndexError(f"Channel index {selector} is out of range")
            return self.metadata.channels[selector]
        if not isinstance(selector, str):
            raise TypeError("Channel selector must be an integer index or a label")
        matches = [channel for channel in self.metadata.channels if channel.label == selector]
        if len(matches) != 1:
            raise ValueError(f"Channel label {selector!r} has {len(matches)} matches; use an index")
        return matches[0]

    def read_plane(self, channel: str | int, acquisition_index: int) -> NDArray[np.uint16]:
        """Read one uncorrected plane without loading any other planes.

        Parameters
        ----------
        channel
            Exact channel label or zero-based channel index.
        acquisition_index
            Zero-based index in the channel's pointer table; not elapsed time.

        Returns
        -------
        numpy.ndarray
            Read-only array of stored values in the provisional pixel layout.
            No correction, normalization, missing-value handling, or calibration
            is applied. Units remain unknown.
        """
        self._check_source()
        if not self._accept_provisional:
            raise ProvisionalFormatError(
                "Numerical decoding is provisional; reopen with accept_provisional=True "
                "after reviewing metadata.assumptions"
            )
        selected = self.channel(channel)
        if isinstance(acquisition_index, bool) or not isinstance(acquisition_index, int):
            raise TypeError("Acquisition index must be an integer")
        if not 0 <= acquisition_index < len(selected.plane_offsets):
            raise IndexError(f"Acquisition index {acquisition_index} is out of range")
        raw = self._read(selected.plane_offsets[acquisition_index], selected.plane_bytes)
        return np.frombuffer(raw, dtype=np.dtype("<u2")).reshape(
            self.metadata.candidate_plane_shape
        )

    def iter_planes(self, channel: str | int) -> Iterator[NDArray[np.uint16]]:
        """Yield every plane in one channel in stored acquisition order."""
        selected = self.channel(channel)
        for index in range(len(selected.plane_offsets)):
            yield self.read_plane(selected.index, index)

    def read_header(self) -> bytes:
        """Return all original bytes preceding the payload, including unknown metadata."""
        return self._read(0, self.metadata.header_bytes)

    def source_sha256(self) -> str:
        """Hash the full open source; this explicitly reads the whole file."""
        self._check_source()
        self._stream.seek(0)
        digest = hashlib.file_digest(self._stream, "sha256").hexdigest()
        self._check_source()
        return digest
