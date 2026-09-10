"""Shared JSON-compatible reader provenance."""

from importlib.metadata import version

from .reader import ImageFile


def describe(image: ImageFile, *, include_hash: bool = False) -> dict[str, object]:
    """Build a JSON-compatible description without assigning unknown units."""
    info = image.metadata
    result: dict[str, object] = {
        "reader_version": version("sims-reader"),
        "status": info.status,
        "assumptions": info.assumptions,
        "source": str(image.path),
        "source_bytes": info.source_bytes,
        "header_bytes": info.header_bytes,
        "directory_words": info.directory_words,
        "acquisition_count": info.acquisition_count,
        "candidate_plane_shape": info.candidate_plane_shape,
        "candidate_dtype": info.candidate_dtype,
        "signal_units": info.signal_units,
        "pixel_size": info.pixel_size,
        "channels": [
            {
                "index": channel.index,
                "label": channel.label,
                "record_offset": channel.record_offset,
                "table_offset": channel.table_offset,
                "table_words": channel.table_words,
                "plane_bytes": channel.plane_bytes,
                "plane_offsets": channel.plane_offsets,
            }
            for channel in info.channels
        ],
    }
    if include_hash:
        result["source_sha256"] = image.source_sha256()
    return result
