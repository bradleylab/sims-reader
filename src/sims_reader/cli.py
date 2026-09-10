"""Command-line inspection and explicitly provisional plane extraction."""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path

import numpy as np

from .provenance import describe
from .reader import ImageFile


def main(argv: list[str] | None = None) -> int:
    """Run the local CLI; errors are diagnostics, never silent fallback decodes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=version("sims-reader"))
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Inspect metadata; no numerical decoding")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--hash", action="store_true", help="Also hash the entire source")
    plane = commands.add_parser("plane", help="Extract one provisional plane and its provenance")
    plane.add_argument("path", type=Path)
    selectors = plane.add_mutually_exclusive_group(required=True)
    selectors.add_argument("--channel", type=str, help="Exact stored label")
    selectors.add_argument("--channel-index", type=int, help="Zero-based index")
    plane.add_argument("--index", type=int, required=True, help="Zero-based acquisition index")
    plane.add_argument("--accept-provisional", action="store_true")
    plane.add_argument(
        "--output-dir", type=Path, required=True, help="New directory; never overwritten"
    )
    convert = commands.add_parser("convert", help="Write and verify a new local Zarr v3 store")
    convert.add_argument("path", type=Path)
    convert.add_argument("destination", type=Path)
    convert.add_argument("--accept-provisional", action="store_true")
    convert.add_argument("--spatial-chunks", nargs=2, type=int, metavar=("ROWS", "COLUMNS"))
    args = parser.parse_args(argv)
    try:
        if args.command == "convert":
            from .conversion import convert_to_zarr

            chunks = (
                (args.spatial_chunks[0], args.spatial_chunks[1])
                if args.spatial_chunks is not None
                else None
            )
            result = convert_to_zarr(
                args.path,
                args.destination,
                accept_provisional=args.accept_provisional,
                spatial_chunks=chunks,
            )
            print(json.dumps(asdict(result), indent=2))
            return 0
        with ImageFile(
            args.path, accept_provisional=getattr(args, "accept_provisional", False)
        ) as image:
            if args.command == "inspect":
                print(json.dumps(describe(image, include_hash=args.hash), indent=2))
            else:
                selector = args.channel if args.channel is not None else args.channel_index
                selected = image.channel(selector)
                array = image.read_plane(selected.index, args.index)
                metadata = describe(image, include_hash=True)
                metadata.update(
                    {
                        "selected_channel_index": selected.index,
                        "selected_acquisition_index": args.index,
                        "plane_payload_sha256": hashlib.sha256(array.tobytes()).hexdigest(),
                        "processing": "No corrections or calibration; stored values only.",
                    }
                )
                args.output_dir.mkdir(parents=True, exist_ok=False)
                with (args.output_dir / "plane.npy").open("xb") as output:
                    np.save(output, array, allow_pickle=False)
                (args.output_dir / "metadata.json").write_text(
                    json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
                )
                print(f"Provisional plane and provenance written to {args.output_dir}")
    except (OSError, ValueError, IndexError, TypeError, ImportError) as error:
        print(f"sims-reader: {error}", file=sys.stderr)
        return 1
    return 0
