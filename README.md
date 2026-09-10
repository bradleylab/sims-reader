# sims-reader

Convert Cameca 7f-GEO `.im` ion images to Zarr for viewing in
[napari](https://napari.org/) or use in Python.

## Install

Requires Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/bradleylab/sims-reader.git
cd sims-reader
uv sync --extra zarr --frozen
```

## Convert

Replace the example paths with your own. The output directory must not exist,
and its parent must exist.

```sh
uv run --extra zarr --frozen sims-reader inspect /path/to/image.im

uv run --extra zarr --frozen sims-reader convert /path/to/image.im \
  /path/to/image.zarr --accept-provisional
```

Conversion checks every pixel, coordinate, channel label, and original header
byte after writing, and confirms that the source checksum has not changed.
Existing outputs are never overwritten. Failed conversions retain an incomplete
output directory; do not use it as a completed store.

To verify an existing conversion:

```sh
uv run --extra zarr --frozen sims-reader verify /path/to/image.zarr \
  --source /path/to/image.im --accept-provisional
```

To convert a folder:

```sh
uv run --extra zarr --frozen sims-reader batch /path/to/inputs /path/to/outputs \
  --recursive --accept-provisional > batch-report.json
```

Input and output folders must be disjoint. Omit `--recursive` to process only
immediate files. Relative subfolders are preserved. A failed file is reported
without stopping other conversions; any failure produces a nonzero exit code.
Progress goes to stderr and the JSON report goes to stdout.

## View in napari

Install the viewer separately from the converter:

```sh
uv venv .venv-napari
uv pip install --python .venv-napari 'napari[pyqt6]==0.9.1' 'zarr==3.3.0'
```

Save the following as `view.py`, change the store path, and run it with the
viewer environment's Python (`.venv-napari/bin/python view.py` on macOS/Linux,
`.venv-napari\Scripts\python.exe view.py` on Windows):

```python
import napari
import zarr

root = zarr.open_group("/path/to/image.zarr", mode="r")
assert root["conversion"].attrs["conversion_status"] == "complete"
viewer = napari.Viewer()
viewer.add_image(
    root["stored_signal"][0, :, :, :],
    channel_axis=0,
    name=list(root["channel_label"][:]),
    axis_labels=("row", "column"),
)
napari.run()
```

This displays the first acquisition, with one image layer per channel. Change
`0` to another acquisition index. Napari can display the images and draw ROIs;
the converter does not calculate ROI statistics.

## Output and methods

The output is Zarr v3, not OME-Zarr. `stored_signal` has dimensions
`(acquisition_index, channel, row, column)`, with separate index coordinates and
`channel_label` values. Original header bytes are retained in `source/header`.
Source SHA-256, reader provenance, and a completion receipt are included.
Compression is lossless Zstandard. Default chunks contain one image plane;
`--spatial-chunks ROWS COLUMNS` selects smaller spatial tiles.

The reader follows channel records and absolute image pointers, derives the
header boundary from the first image, and requires complete, non-overlapping
coverage of the remaining file. Unsupported layouts fail explicitly.

**The format interpretation remains provisional.** Image blocks are interpreted
as square, little-endian unsigned 16-bit arrays, with dimensions inferred from
block length. Rows and columns retain their stored order without flipping or
transposing. Zeros remain data. No correction, normalization, filtering,
calibration, or aggregation is applied. Signal units, physical scale, timing,
and prior instrument corrections are not inferred.

Eight additional real files passed exact conversion readback, covering 3, 4,
and 8 channels and 32–300 acquisitions. Matching instrument sidecars agreed on
acquisition counts and channel order. These checks establish preservation under
the current decoder; independent vendor pixel exports are still needed to
confirm pixel interpretation and orientation. This is not a general reader for
all Cameca `.im` variants.

## Python access

```python
from sims_reader import ImageFile

with ImageFile("/path/to/image.im", accept_provisional=True) as image:
    print(image.metadata)
    plane = image.read_plane(channel=0, acquisition_index=0)
```

Run `sims-reader --help` for all commands. Sample data are not included.
