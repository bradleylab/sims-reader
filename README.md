# sims-reader

A Python reader and lossless `.im` → Zarr translator for the **provisional Cameca 7f-GEO image layout** investigated in this workspace. Use [napari](https://napari.org/) to explore the converted ion images and draw regions of interest. This project focuses on file translation.

The reader follows channel and image-pointer tables, derives the header boundary from those pointers, and loads individual planes. It retains stored labels and opaque header bytes. It does not apply corrections or infer signal units, physical scale, or elapsed time.

**Status:** one real specimen has supported the structural interpretation. Pixel values are provisionally interpreted as square, little-endian 16-bit arrays. The exact vendor type, signedness, dimensions, orientation, and units still need independent verification. Metadata inspection is available by default; numerical decoding requires explicit opt-in. This is not a general reader for all Cameca `.im` variants.

## Install and inspect

Requires Python 3.12 or later. From this repository directory:

```sh
uv sync --extra zarr --frozen
uv run --extra zarr --frozen sims-reader inspect ../CN_SiA_1.im
```

Add `--hash` to compute a full-file SHA-256. Ordinary inspection reads structural metadata only; hashing reads the complete file. Paths passed on the command line resolve relative to your current directory. No sample data are included in the repository.

## Python API

```python
from pathlib import Path
from sims_reader import ImageFile

source = Path("../CN_SiA_1.im")  # Replace with your file location.
with ImageFile(source) as image:
    print(image.metadata)
    print(image.metadata.assumptions)

# Opt in after reviewing the provisional interpretation.
with ImageFile(source, accept_provisional=True) as image:
    channel = image.metadata.channels[0]
    plane = image.read_plane(channel.index, acquisition_index=0)
    header_bytes = image.read_header()  # Full original header, including unknown fields.
    checksum = image.source_sha256()
```

`read_plane` returns a read-only NumPy array that remains usable after closing the source. Exact unique labels can substitute for channel indices. Duplicate labels require an index. Indices are zero-based and negative indexing is deliberately rejected. `iter_planes(channel)` yields planes in stored acquisition order.

Use `ImageFile` as a context manager or call `close()`. Instances are not thread-safe. The reader detects ordinary source-file modifications while open and refuses further access; do not edit the file during a session.

## Extract one plane

```sh
uv run --extra zarr --frozen sims-reader plane ../CN_SiA_1.im \
  --channel-index 0 \
  --index 0 \
  --accept-provisional \
  --output-dir results/first-plane
```

The new directory contains `plane.npy` and `metadata.json`, including provisional assumptions, selected indices, source hash, plane-payload hash, and reader version. An existing output directory is never overwritten. No scientific transformations are performed.

## Convert to Zarr

```sh
uv run --extra zarr --frozen sims-reader convert ../CN_SiA_1.im \
  ../results/CN_SiA_1.zarr --accept-provisional
```

The destination must be new and its parent must exist. Conversion streams planes into Zarr v3, then reopens and verifies every pixel, coordinate, label, and original header byte. It checks the source checksum again before marking completion. Existing destinations are never overwritten. Failed conversions retain an incomplete directory for diagnosis.

`stored_signal` has dimensions `(acquisition_index, channel, row, column)`. Values retain their provisional unsigned 16-bit interpretation; zeros remain data. Default chunks contain one plane; `--spatial-chunks ROWS COLUMNS` selects smaller spatial tiles. Lossless Zstandard compression is used. No physical scale, elapsed time, or depth is invented.

See [the Zarr schema and Python examples](docs/zarr.md) and [existing viewers and OME-Zarr assessment](docs/viewers.md). This output is ordinary Zarr, not OME-Zarr.

## View in napari

The `.im` → Zarr → napari workflow has been exercised locally with napari 0.9.1 on macOS: all four ion channels from the first acquisition loaded, and the user confirmed the display worked. Interactive ROI workflows remain untested.

Install napari in a separate environment and use the [napari loading example](docs/viewers.md#first-choice-napari) to open the converted data. It uses `napari.Viewer()` and `viewer.add_image()` with channel labels preserved. The output is plain Zarr, so automatic loading through an OME-Zarr plugin is not assumed.

## Test and check

```sh
uv run --extra zarr --frozen python -m unittest discover -s tests -v
uv run --extra zarr --frozen ruff check .
uv run --extra zarr --frozen ruff format --check .
uv run --extra zarr --frozen mypy
uv build
```

The routine suite generates explicitly synthetic binary fixtures locally. It requires no private data and checks exact pixel preservation, pointer relocation, per-plane access, provisional opt-in, malformed inputs, changed sources, duplicate labels, and CLI behavior.

For the optional local regression check against the original investigation script:

```sh
uv run --extra zarr --frozen python scripts/verify_sample.py \
  --input ../CN_SiA_1.im \
  --reference-probe ../scripts/preview_probe.py \
  --output results/sample-regression.json
```

Only load a trusted local reference script: this command imports it as Python code. The report compares every plane against the original probe's layout and checks that the source hash is unchanged. It demonstrates regression agreement, not validation against Cameca software.

## Format and scope

Read [the format notes](docs/format.md), [methods](METHODS.md), and [roadmap](ROADMAP.md). Unsupported layouts fail explicitly; no fallback guesses, dropped planes, or lossy label decoding occur.

This repository was created inside the surrounding investigation workspace. Original images, investigation results, and the reference script remain outside it. No remote or release is configured. License selection remains open before distribution.
