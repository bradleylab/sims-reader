"""Build a private sample matrix from a saved Box listing and optional local files.

The snapshot must include folder_id, entries, totalCount, and file checksums.
This script does not contact Box, download files, or write into the public repo.
"""

import argparse
import hashlib
import json
from pathlib import Path

from sims_reader import ImageFile


def build_inventory(snapshot: dict, local_root: Path | None) -> dict:
    """Record exact-name companion matches and honest local inspection status."""
    samples = []
    for folder in snapshot["folders"]:
        if len(folder["entries"]) != folder["totalCount"]:
            raise ValueError("Incomplete Box listing: retrieve all pages first")
        by_name = {entry["name"]: entry for entry in folder["entries"]}
        for entry in folder["entries"]:
            name = entry["name"]
            if entry["type"] != "file" or Path(name).suffix.lower() != ".im":
                continue
            companions = {}
            for suffix in (".im_asc", ".aso"):
                candidate = str(Path(name).with_suffix(suffix))
                match = by_name.get(candidate)
                companions[suffix] = {
                    "status": "exact_name_match_unvalidated" if match else "missing_exact_match",
                    "file": match,
                }
            sample = {
                "folder_id": folder["folder_id"],
                "file": entry,
                "companions": companions,
                "inspection_status": "metadata_only",
                "candidate_shape": None,
                "channels": None,
            }
            # Local layout is folder-id/name, preventing ambiguous same-name
            # matching across remote directories. Never search unrelated paths.
            local = local_root / folder["folder_id"] / name if local_root else None
            if local and local.is_file():
                with local.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha1").hexdigest()
                sample["local_sha1"] = digest
                if digest != entry.get("sha1"):
                    sample["inspection_status"] = "checksum_mismatch"
                else:
                    try:
                        with ImageFile(local) as image:
                            sample["candidate_shape"] = [
                                image.metadata.acquisition_count,
                                len(image.metadata.channels),
                                *image.metadata.candidate_plane_shape,
                            ]
                            sample["channels"] = [c.label for c in image.metadata.channels]
                            sample["inspection_status"] = "structurally_supported_provisional"
                    except (ValueError, OSError) as error:
                        sample["inspection_status"] = "inspection_failed"
                        sample["error"] = f"{type(error).__name__}: {error}"
            samples.append(sample)
    samples.sort(key=lambda s: (s["folder_id"], s["file"]["name"]))
    # Size strata are an initial sampling strategy, never a format classification.
    selected_sizes = set()
    for sample in samples:
        size = sample["file"]["size"]
        sample["initial_candidate"] = size not in selected_sizes
        sample["selection_reason"] = (
            "First in deterministic order for this byte-size stratum; layout unverified"
            if size not in selected_sizes
            else "Same byte-size stratum as another candidate"
        )
        selected_sizes.add(size)
    return {
        "samples": samples,
        "sample_count": len(samples),
        "size_strata": sorted(selected_sizes),
        "limitations": "Remote SHA-1 is recorded provenance, not a local validation. "
        "Size strata do not establish channel, acquisition, or format diversity. "
        "Authoritative pixel exports still need to be identified.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--local-root", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if args.output.resolve().is_relative_to(repo):
        parser.error("Private inventory output must be outside the public repository")
    report = build_inventory(json.loads(args.snapshot.read_text()), args.local_root)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")
    print(f"Recorded {report['sample_count']} samples; raw-file inspection remains explicit")


if __name__ == "__main__":
    main()
