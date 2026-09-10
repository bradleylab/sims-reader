# sims-reader

`sims-reader` converts Cameca 7f-GEO `.im` ion images to the open Zarr format for viewing in [napari](https://napari.org/) or analysis in Python.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/bradleylab/sims-reader.git
cd sims-reader
uv sync --extra zarr --frozen
```

## Convert an image

First inspect the file:

```sh
uv run --extra zarr --frozen sims-reader inspect /path/to/image.im
```

Then convert it:

```sh
uv run --extra zarr --frozen sims-reader convert /path/to/image.im \
  /path/to/image.zarr --accept-provisional
```

The converter verifies the output against the original `.im` file after writing it and never overwrites an existing output.

You can also verify a previous conversion:

```sh
uv run --extra zarr --frozen sims-reader verify /path/to/image.zarr \
  --source /path/to/image.im --accept-provisional
```

Or convert a folder of files:

```sh
uv run --extra zarr --frozen sims-reader batch /path/to/inputs /path/to/outputs \
  --recursive --accept-provisional > batch-report.json
```

Remove `--recursive` to process only files directly inside the input folder. Failed files are reported without stopping the rest of the batch.

## View in napari

Install napari in a separate environment:

```sh
uv venv .venv-napari
uv pip install --python .venv-napari 'napari[pyqt6]==0.9.1' 'zarr==3.3.0'
```

Example viewer:

```python
import napari
import zarr

root = zarr.open_group("/path/to/image.zarr", mode="r")

viewer = napari.Viewer()
viewer.add_image(
    root["stored_signal"][0],
    channel_axis=0,
    name=list(root["channel_label"][:]),
    axis_labels=("row", "column"),
)
napari.run()
```

This displays the first acquisition with one image layer per channel. Change `0` to view another acquisition.

## Use in Python

You can also read `.im` files directly:

```python
from sims_reader import ImageFile

with ImageFile("/path/to/image.im", accept_provisional=True) as image:
    print(image.metadata)
    plane = image.read_plane(channel=0, acquisition_index=0)
```

## Output format

The output is Zarr v3. Image data are stored as:

```text
stored_signal[acquisition, channel, row, column]
```

The Zarr store also includes channel labels, the original file header, source checksum, conversion provenance, and verification information. Compression is lossless.

The converter preserves the recorded pixel values as-is. It does not apply corrections, normalization, filtering, calibration, or aggregation.

## Current limitations

The Cameca `.im` format is proprietary, so the format interpretation used here remains provisional.

The reader currently interprets image blocks as square, little-endian unsigned 16-bit arrays and preserves their stored row and column order. This interpretation has been tested successfully on additional Cameca 7f-GEO files containing 3–8 channels and 32–300 acquisitions, with instrument sidecar files agreeing on acquisition counts and channel order.

Independent comparison with vendor-exported pixel data is still needed to confirm pixel orientation and interpretation. For this reason, `--accept-provisional` is currently required.

This is a reader for the tested Cameca 7f-GEO files, not a general reader for every Cameca `.im` variant.

Run `sims-reader --help` for additional commands and options.
