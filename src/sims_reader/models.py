"""Public metadata and errors for the provisional reader."""

from dataclasses import dataclass

PROVISIONAL_ASSUMPTIONS = (
    "Little-endian 16-bit image values; signedness is not established.",
    "Square image shape inferred from block length, not an explicit dimension field.",
    "Row-major file order; orientation relative to instrument display is unverified.",
    "Signal units, physical scale, timing, and prior corrections are unknown.",
    "Compatibility is demonstrated for one observed layout, not all Cameca files.",
)


class FormatError(ValueError):
    """File structure is inconsistent, truncated, or outside the supported layout."""


class UnsupportedFormatError(FormatError):
    """A layout marker does not match the investigated format."""


class ProvisionalFormatError(ValueError):
    """Reading numerical values requires explicit acceptance of the interpretation."""


class SourceChangedError(OSError):
    """The opened source changed after its metadata was inspected."""


@dataclass(frozen=True)
class Channel:
    """Stored channel name, metadata records, and ordered plane offsets.

    Notes
    -----
    Labels are retained verbatim. Duplicate labels require selection by index.
    Unknown table words and the original label bytes are exposed without inference.
    """

    index: int
    label: str
    label_bytes: bytes
    record_offset: int
    table_offset: int
    table_words: tuple[int, ...]
    plane_bytes: int
    plane_offsets: tuple[int, ...]


@dataclass(frozen=True)
class ImageMetadata:
    """Mechanically checked layout with explicit, unvalidated image assumptions."""

    source_bytes: int
    header_bytes: int
    directory_words: tuple[int, ...]
    channels: tuple[Channel, ...]
    candidate_plane_shape: tuple[int, int]
    candidate_dtype: str = "<u2"
    status: str = "provisional"
    assumptions: tuple[str, ...] = PROVISIONAL_ASSUMPTIONS
    signal_units: None = None
    pixel_size: None = None

    @property
    def acquisition_count(self) -> int:
        """Number of indexed planes per channel; not a calibrated time coordinate."""
        return len(self.channels[0].plane_offsets)
