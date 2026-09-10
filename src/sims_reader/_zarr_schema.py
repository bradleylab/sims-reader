"""Lossless Zarr v3 schema and read-back verification; see docs/zarr.md."""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

import numpy as np
import zarr
from zarr.codecs import BytesCodec, ZstdCodec

from .provenance import describe
from .reader import ImageFile

DIMENSIONS = ("acquisition_index", "channel", "row", "column")
SCHEMA_VERSION = "1.0"


class VerificationError(ValueError):
    """Written data or metadata differ from the source or conversion contract."""


def provenance(image: ImageFile, chunks: tuple[int, ...], source_hash: str) -> dict[str, Any]:
    """Record the exact interpretation, software, and compression configuration."""
    code_hash = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        code_hash.update(path.name.encode())
        code_hash.update(path.read_bytes())
    result = {
        "sims_reader_schema": SCHEMA_VERSION,
        "conversion_status": "verifying",
        "format_status": image.metadata.status,
        "source_metadata": describe(image),
        "source_sha256": source_hash,
        "reader_code_sha256": code_hash.hexdigest(),
        "numpy_version": np.__version__,
        "zarr_version": version("zarr"),
        "dimensions": DIMENSIONS,
        "chunks": chunks,
        "compression": ZstdCodec().to_dict(),
        "header_sha256": hashlib.sha256(image.read_header()).hexdigest(),
        "processing": "Lossless storage only; no corrections, calibration, masking, "
        "normalization, imputation, aggregation, or downsampling.",
    }
    # Normalize tuples to their actual JSON representation before comparison.
    return cast(dict[str, Any], json.loads(json.dumps(result)))


def create_store(
    path: Path, image: ImageFile, chunks: tuple[int, ...], attributes: dict[str, Any]
) -> tuple[zarr.Group, zarr.Array[Any]]:
    """Create arrays with named dimensions and materialized zero-valued chunks."""
    info = image.metadata
    shape = (info.acquisition_count, len(info.channels), *info.candidate_plane_shape)
    root = zarr.open_group(path, mode="w-", zarr_format=3, attributes=attributes)
    data = root.create_array(
        "stored_signal",
        shape=shape,
        dtype=info.candidate_dtype,
        chunks=chunks,
        dimension_names=DIMENSIONS,
        compressors=[ZstdCodec()],
        serializer=BytesCodec(endian="little"),
        fill_value=0,
        config={"write_empty_chunks": True},
        attributes={"coordinates": "channel_label", "interpretation_status": "provisional"},
    )
    for dimension, length in zip(DIMENSIONS, shape):
        root.create_array(
            dimension,
            data=np.arange(length, dtype="<i8"),
            chunks=(length,),
            dimension_names=(dimension,),
            config={"write_empty_chunks": True},
            attributes={"long_name": dimension + " (index; no physical calibration)"},
        )
    labels = root.create_array(
        "channel_label",
        shape=(len(info.channels),),
        dtype="str",
        chunks=(len(info.channels),),
        dimension_names=("channel",),
        config={"write_empty_chunks": True},
    )
    labels[:] = [channel.label for channel in info.channels]
    source = root.create_group("source")
    header = image.read_header()
    source.create_array(
        "header",
        data=np.frombuffer(header, dtype="u1"),
        chunks=(len(header),),
        dimension_names=("header_byte",),
        config={"write_empty_chunks": True},
        compressors=[ZstdCodec()],
    )
    return root, data


def get_array(root: zarr.Group, name: str) -> zarr.Array[Any]:
    """Require a named array rather than accepting a group in its place."""
    result = root[name]
    if not isinstance(result, zarr.Array):
        raise VerificationError(f"Expected an array: {name}")
    return result


def _dimensions(array: zarr.Array[Any]) -> tuple[str, ...]:
    names = array.metadata.to_dict().get("dimension_names")
    if not isinstance(names, (list, tuple)) or any(not isinstance(name, str) for name in names):
        raise VerificationError("Missing or invalid dimension names")
    return cast(tuple[str, ...], tuple(names))


def verify_store(path: Path, image: ImageFile, attributes: dict[str, Any]) -> int:
    """Reopen and compare every plane, coordinate, label, header byte, and metadata.

    No fill chunks are permitted: even all-zero chunks must have been written.
    Verification confirms conversion fidelity, not the provisional decoding model.
    """
    root = zarr.open_group(path, mode="r", use_consolidated=False)
    if dict(root.attrs) != attributes:
        raise VerificationError("Root provenance metadata changed")
    data = get_array(root, "stored_signal")
    info = image.metadata
    shape = (info.acquisition_count, len(info.channels), *info.candidate_plane_shape)
    if data.shape != shape or np.dtype(data.dtype) != np.dtype(info.candidate_dtype):
        raise VerificationError("Signal shape or dtype changed")
    if _dimensions(data) != DIMENSIONS or tuple(data.chunks) != tuple(attributes["chunks"]):
        raise VerificationError("Signal dimensions or chunks changed")
    if dict(data.attrs) != {"coordinates": "channel_label", "interpretation_status": "provisional"}:
        raise VerificationError("Signal attributes changed")
    encoding = data.metadata.to_dict()
    if encoding.get("zarr_format") != 3 or encoding.get("fill_value") != 0:
        raise VerificationError("Signal storage metadata changed")
    codecs = encoding.get("codecs")
    if not isinstance(codecs, (list, tuple)) or list(codecs) != [
        BytesCodec(endian="little").to_dict(),
        attributes["compression"],
    ]:
        raise VerificationError("Signal codec metadata changed")
    if data.nchunks_initialized != data.nchunks:
        raise VerificationError("Missing stored chunks; refusing implicit fill values")
    for dimension, length in zip(DIMENSIONS, shape):
        coordinate = get_array(root, dimension)
        if (
            dict(coordinate.attrs) != {"long_name": dimension + " (index; no physical calibration)"}
            or coordinate.dtype != np.dtype("<i8")
            or _dimensions(coordinate) != (dimension,)
            or coordinate.nchunks_initialized != coordinate.nchunks
            or not np.array_equal(np.asarray(coordinate[:]), np.arange(length, dtype="<i8"))
        ):
            raise VerificationError(f"Coordinate mismatch: {dimension}")
    labels = get_array(root, "channel_label")
    if (
        dict(labels.attrs) != {}
        or _dimensions(labels) != ("channel",)
        or labels.nchunks_initialized != labels.nchunks
        or list(np.asarray(labels[:])) != [channel.label for channel in info.channels]
    ):
        raise VerificationError("Channel labels changed")
    header = get_array(root, "source/header")
    if (
        dict(header.attrs) != {}
        or _dimensions(header) != ("header_byte",)
        or header.dtype != np.dtype("u1")
        or header.nchunks_initialized != header.nchunks
        or np.asarray(header[:]).tobytes() != image.read_header()
    ):
        raise VerificationError("Opaque header changed")
    verified = 0
    for acquisition in range(info.acquisition_count):
        for channel in info.channels:
            if not np.array_equal(
                np.asarray(data[acquisition, channel.index, :, :]),
                image.read_plane(channel.index, acquisition),
            ):
                raise VerificationError(
                    f"Pixel mismatch: acquisition {acquisition}, channel {channel.index}"
                )
            verified += 1
    return verified
