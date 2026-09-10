"""Compare every plane with a trusted local investigation probe; no source edits."""

import argparse
import hashlib
import importlib.util
import json
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np

from sims_reader import ImageFile


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--reference-probe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; select a new path")
    before = file_hash(args.input)
    spec = importlib.util.spec_from_file_location("trusted_reference_probe", args.reference_probe)
    if spec is None or spec.loader is None:
        parser.error("Cannot import the supplied reference probe")
    reference = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = reference
    spec.loader.exec_module(reference)
    with args.input.open("rb") as source:
        header = source.read(reference.OBSERVED_HEADER_BYTES)
    _, expected_channels = reference.parse_header(header, args.input.stat().st_size)
    compared = 0
    with ImageFile(args.input, accept_provisional=True) as image:
        if len(expected_channels) != len(image.metadata.channels):
            raise AssertionError("Channel count differs")
        if image.read_header() != header:
            raise AssertionError("Header boundary or bytes differ")
        for index, expected in enumerate(expected_channels):
            channel = image.metadata.channels[index]
            if (channel.label, channel.plane_offsets, channel.plane_bytes) != (
                expected.label,
                expected.pointers,
                expected.plane_bytes,
            ):
                raise AssertionError("Channel metadata differ")
            side = image.metadata.candidate_plane_shape[0]
            for acquisition, pointer in enumerate(expected.pointers):
                baseline = np.memmap(
                    args.input,
                    mode="r",
                    dtype=reference.CANDIDATE_DTYPE,
                    offset=pointer,
                    shape=(side, side),
                )
                np.testing.assert_array_equal(image.read_plane(index, acquisition), baseline)
                compared += 1
        after = image.source_sha256()
    if before != after or before != file_hash(args.input):
        raise AssertionError("Source changed during verification")
    result = {
        "status": "regression passed; vendor interpretation still provisional",
        "reader_version": version("sims-reader"),
        "source_sha256": before,
        "source_unchanged": True,
        "planes_compared": compared,
        "reference_probe_sha256": file_hash(args.reference_probe),
        "numpy_version": np.__version__,
        "all_planes_exactly_equal": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
