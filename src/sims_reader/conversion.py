"""Convert a local .im file into a fully verified, xarray-compatible Zarr store."""

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .models import ProvisionalFormatError, SourceChangedError
from .reader import ImageFile


@dataclass(frozen=True)
class ConversionResult:
    """Completed conversion receipt; interpretation remains provisional."""

    destination: str
    source_sha256: str
    planes_verified: int
    shape: tuple[int, ...]
    chunks: tuple[int, ...]
    format_status: str = "provisional"
    conversion_status: str = "complete"


def _receipt(destination: Path, content: dict[str, Any]) -> None:
    import zarr

    # A valid metadata-only subgroup keeps ordinary Zarr/xarray readers free of
    # unrecognized-file warnings. Only this conversion owns the reserved target.
    zarr.open_group(destination / "conversion", mode="w", zarr_format=3, attributes=content)


def convert_to_zarr(
    source: str | Path,
    destination: str | Path,
    *,
    accept_provisional: bool = False,
    spatial_chunks: tuple[int, int] | None = None,
) -> ConversionResult:
    """Stream a source into a new local Zarr v3 directory and verify every value.

    Parameters
    ----------
    source
        Read-only input file.
    destination
        New local directory. Existing paths, including incomplete outputs, are
        never overwritten. Parent directories must already exist.
    accept_provisional
        Explicitly acknowledge the reader's unvalidated pixel interpretation.
    spatial_chunks
        Optional row/column chunk sizes. Defaults to one complete plane per
        chunk, with one acquisition and channel per chunk in either case.

    Returns
    -------
    ConversionResult
        Receipt also saved as attributes on the ``conversion`` subgroup.

    Notes
    -----
    Requires the ``zarr`` extra. Work is staged in ``.partial`` inside an
    exclusively reserved destination. Only verified data are promoted to its
    root. The ``conversion`` subgroup with status ``complete`` is the completion marker.
    Failures retain an explicitly incomplete output for diagnosis; no resume or
    overwrite is attempted. Publication is a sequence of local renames, not an
    atomic transaction across all files. This function does not upload anything.
    """
    if not accept_provisional:
        raise ProvisionalFormatError("Conversion requires accept_provisional=True")
    try:
        import zarr

        from ._zarr_schema import create_store, provenance, verify_store
    except ImportError as error:
        raise ImportError("Zarr conversion requires installation of sims-reader[zarr]") from error
    target = Path(destination).absolute()
    if os.path.lexists(target):
        raise FileExistsError(f"Destination already exists: {target}")
    with ImageFile(source, accept_provisional=True) as image:
        info = image.metadata
        spatial = spatial_chunks if spatial_chunks is not None else info.candidate_plane_shape
        if len(spatial) != 2 or any(
            isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= limit
            for value, limit in zip(spatial, info.candidate_plane_shape)
        ):
            raise ValueError("Spatial chunks must be positive integers no larger than the image")
        chunks = (1, 1, *spatial)
        source_hash = image.source_sha256()
        attributes = provenance(image, chunks, source_hash)
        target.mkdir()  # Exclusive reservation; also rejects concurrent conversions.
        stage = target / ".partial"
        try:
            _receipt(target, {"conversion_status": "writing", "format_status": "provisional"})
            # Retain the original writer: write_empty_chunks is runtime state,
            # and Zarr 3.3 open_array does not retain this setting on reopen.
            _, data = create_store(stage, image, chunks, attributes)
            for acquisition in range(info.acquisition_count):
                for channel in info.channels:
                    data[acquisition, channel.index, :, :] = image.read_plane(
                        channel.index, acquisition
                    )
            _receipt(target, {"conversion_status": "verifying", "format_status": "provisional"})
            verified = verify_store(stage, image, attributes)
            if image.source_sha256() != source_hash:
                raise SourceChangedError("Source hash changed during conversion")
            # Root metadata moves last, so an ordinary Zarr opener cannot see a
            # root dataset while its verified arrays are still being promoted.
            entries = sorted(stage.iterdir(), key=lambda path: path.name == "zarr.json")
            for entry in entries:
                entry.rename(target / entry.name)
            stage.rmdir()
            completed = zarr.open_group(target, mode="r+", use_consolidated=False)
            completed.attrs["conversion_status"] = "complete"
            result = ConversionResult(
                str(target),
                source_hash,
                verified,
                (info.acquisition_count, len(info.channels), *info.candidate_plane_shape),
                chunks,
            )
            _receipt(target, asdict(result))
            return result
        except BaseException as error:
            try:
                if (target / "zarr.json").exists():
                    zarr.open_group(target, mode="r+").attrs["conversion_status"] = "failed"
                _receipt(
                    target,
                    {
                        "conversion_status": "failed",
                        "format_status": "provisional",
                        "error": f"{type(error).__name__}: {error}",
                    },
                )
            except OSError:
                pass  # Preserve the original failure; absent completion marker is sufficient.
            raise
