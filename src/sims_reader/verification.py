"""Read-only verification of completed stores against original source bytes."""

import re
from dataclasses import dataclass
from pathlib import Path

from .models import ProvisionalFormatError, SourceChangedError
from .reader import ImageFile


@dataclass(frozen=True)
class VerificationResult:
    """Evidence of agreement with this decoder, not vendor validation."""

    store: str
    source_sha256: str
    planes_verified: int
    verification_status: str = "passed"
    format_status: str = "provisional"


def verify_zarr(
    store: str | Path, source: str | Path, *, accept_provisional: bool = False
) -> VerificationResult:
    """Compare a completed local store with its source without writing either.

    Source and store may have moved. Recorded software identifiers are checked
    structurally, not authenticated; historical paths and software versions
    cannot be independently proven from source bytes.
    """
    if not accept_provisional:
        raise ProvisionalFormatError("Verification requires accept_provisional=True")
    import zarr

    from ._zarr_schema import VerificationError, get_array, provenance, verify_store

    path = Path(store)
    root = zarr.open_group(path, mode="r", use_consolidated=False)
    attrs = dict(root.attrs)
    receipt = dict(zarr.open_group(path / "conversion", mode="r").attrs)
    if (
        attrs.get("conversion_status") != "complete"
        or receipt.get("conversion_status") != "complete"
    ):
        raise VerificationError("Incomplete conversion")
    with ImageFile(source, accept_provisional=True) as image:
        checksum = image.source_sha256()
        data = get_array(root, "stored_signal")
        expected = provenance(image, tuple(data.chunks), checksum)
        expected["conversion_status"] = "complete"
        # Preserve historical software provenance and source location. Compare
        # every source-derived field independently using the current decoder.
        for key in ("reader_code_sha256", "numpy_version", "zarr_version"):
            value = attrs.get(key)
            if not isinstance(value, str) or not value:
                raise VerificationError(f"Invalid software provenance: {key}")
            if key.endswith("sha256") and not re.fullmatch(r"[0-9a-f]{64}", value):
                raise VerificationError("Invalid reader code hash")
            expected[key] = value
        metadata = attrs.get("source_metadata")
        if not isinstance(metadata, dict):
            raise VerificationError("Missing source metadata")
        for key in ("reader_version", "source"):
            if not isinstance(metadata.get(key), str) or not metadata[key]:
                raise VerificationError(f"Invalid historical metadata: {key}")
            expected["source_metadata"][key] = metadata[key]
        if attrs != expected:
            raise VerificationError("Source or schema provenance mismatch")
        shape = (
            image.metadata.acquisition_count,
            len(image.metadata.channels),
            *image.metadata.candidate_plane_shape,
        )
        for key, receipt_value in {
            "source_sha256": checksum,
            "shape": list(shape),
            "chunks": list(data.chunks),
            "planes_verified": shape[0] * shape[1],
            "format_status": "provisional",
        }.items():
            if receipt.get(key) != receipt_value:
                raise VerificationError(f"Completion receipt mismatch: {key}")
        verified = verify_store(path, image, expected)
        if image.source_sha256() != checksum:
            raise SourceChangedError("Source changed during verification")
        # Catch ordinary metadata changes during the scan without modifying it.
        current = zarr.open_group(path, mode="r", use_consolidated=False)
        if dict(current.attrs) != attrs:
            raise VerificationError("Store metadata changed during verification")
        return VerificationResult(str(path.absolute()), checksum, verified)
