"""Deterministic local batch conversion without overwrites or hidden failures."""

import os
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .conversion import ConversionResult, convert_to_zarr
from .models import ProvisionalFormatError


@dataclass(frozen=True)
class BatchItem:
    """Outcome for one discovered input."""

    source: str
    destination: str
    status: str
    error: str | None = None
    conversion: ConversionResult | None = None


@dataclass(frozen=True)
class BatchResult:
    """Complete accounting of discovered inputs, in deterministic order."""

    items: tuple[BatchItem, ...]
    batch_status: str
    discovered: int
    succeeded: int
    failed: int
    not_attempted: int


def _discover(folder: Path, recursive: bool) -> list[Path]:
    def fail(error: OSError) -> None:
        raise error

    paths = []
    for base, directories, files in os.walk(folder, followlinks=False, onerror=fail):
        for name in files:
            path = Path(base) / name
            if path.suffix.lower() == ".im":
                paths.append(path)
        if not recursive:
            directories.clear()
    return sorted(paths, key=lambda p: p.relative_to(folder).as_posix())


def _plan(sources: list[Path], folder: Path, output: Path) -> tuple[list[Path], dict[int, str]]:
    targets = [output / p.relative_to(folder).with_suffix(".zarr") for p in sources]
    # Conservative on every OS: avoid collisions after Unicode normalization
    # and case folding, including a store that would contain another store.
    keys = [tuple(unicodedata.normalize("NFC", x).casefold() for x in p.parts) for p in targets]
    errors: dict[int, str] = {}
    for i, key in enumerate(keys):
        for j in range(i):
            other = keys[j]
            if key[: len(other)] == other or other[: len(key)] == key:
                errors[i] = errors[j] = "Destination collision in batch plan"
        if sources[i].is_symlink():
            errors[i] = "Symbolic-link inputs are not followed"
        if os.path.lexists(targets[i]):
            errors[i] = "Destination already exists; no overwrite or resume"
        for ancestor in targets[i].parents:
            if ancestor == output.parent:
                break
            if ancestor.is_symlink() or (ancestor.exists() and not ancestor.is_dir()):
                errors[i] = "Destination parent is a symlink or not a directory"
    return targets, errors


def convert_batch(
    folder: str | Path,
    output: str | Path,
    *,
    accept_provisional: bool = False,
    recursive: bool = False,
    spatial_chunks: tuple[int, int] | None = None,
    progress: Callable[[str], None] | None = None,
) -> BatchResult:
    """Convert discovered .im files with mandatory per-file read-back checks.

    Discovery is nonrecursive unless requested. Directory symlinks are not
    traversed; file symlinks are reported as failures. Input and output trees
    must be disjoint. Relative subdirectories are preserved. Ctrl-C records
    the interrupted file and all remaining files as not attempted. Process
    termination or power loss may prevent the final report from being emitted.
    """
    if not accept_provisional:
        raise ProvisionalFormatError("Batch conversion requires accept_provisional=True")
    source_dir, target_dir = Path(folder).resolve(), Path(output).absolute()
    if not source_dir.is_dir():
        raise NotADirectoryError(source_dir)
    resolved_output = target_dir.resolve()
    if resolved_output.is_relative_to(source_dir) or source_dir.is_relative_to(resolved_output):
        raise ValueError("Input and output directory trees must be disjoint")
    sources = _discover(source_dir, recursive)
    if not sources:
        raise ValueError("No .im files found under the selected discovery rules")
    targets, errors = _plan(sources, source_dir, target_dir)
    results: list[BatchItem] = []
    interrupted = False
    for index, (source, destination) in enumerate(zip(sources, targets)):
        if interrupted:
            results.append(
                BatchItem(str(source), str(destination), "not_attempted", "Batch interrupted")
            )
            continue
        if progress:
            progress(f"[{index + 1}/{len(sources)}] {source.relative_to(source_dir)}")
        if index in errors:
            results.append(BatchItem(str(source), str(destination), "failed", errors[index]))
            continue
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            conversion = convert_to_zarr(
                source, destination, accept_provisional=True, spatial_chunks=spatial_chunks
            )
            results.append(
                BatchItem(str(source), str(destination), "complete", conversion=conversion)
            )
        except KeyboardInterrupt:
            interrupted = True
            results.append(BatchItem(str(source), str(destination), "failed", "Interrupted"))
        except Exception as error:
            # Each independent file still gets a result, including unexpected
            # decoder errors. Never convert an exception into apparent success.
            results.append(
                BatchItem(
                    str(source), str(destination), "failed", f"{type(error).__name__}: {error}"
                )
            )
    succeeded = sum(item.status == "complete" for item in results)
    failed = sum(item.status == "failed" for item in results)
    not_attempted = sum(item.status == "not_attempted" for item in results)
    return BatchResult(
        tuple(results),
        "complete" if succeeded == len(sources) else "failed",
        len(sources),
        succeeded,
        failed,
        not_attempted,
    )
