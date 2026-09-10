# Zarr output

Schema version 1.0 uses Zarr v3. It is not an OME-Zarr image.

| Path | Contents |
| --- | --- |
| `stored_signal` | Provisional uint16 array: acquisition_index × channel × row × column |
| `acquisition_index`, `channel`, `row`, `column` | Integer index coordinates; no physical units |
| `channel_label` | Stored strings indexed by channel; duplicates retained |
| `source/header` | Original opaque header bytes as uint8 |
| `conversion` | Metadata-only subgroup with completion receipt |

Root attributes record source metadata and SHA-256, header SHA-256, reader version and code hash, NumPy/Zarr versions, compression configuration, dimensions, chunks, and interpretation assumptions. Provenance includes the local source path and original header; review these before sharing a store.

Chunks default to one complete plane, with one acquisition and channel per chunk. Optional spatial tile sizes must fit the image. All chunks are written, including zeros. Zstandard compression is lossless. No `_FillValue` attribute is assigned: stored zeros are observations, not missing values.

## Completion and failure

The converter reserves a new destination directory and writes beneath `.partial`. Every value is read back and compared with the source reader; coordinate arrays, labels, header bytes, provenance, and physical chunk presence are checked. The source checksum is checked again. Only verified arrays are moved to the root, with root `zarr.json` last.

Publication consists of several filesystem operations. Consumers must require `conversion` subgroup attribute `conversion_status == "complete"`; root metadata alone is insufficient. Errors leave a failed or incomplete destination. Do not reuse it as an output target. There is no overwrite, resume, or cloud-upload mode. Completion verifies fidelity to the provisional decoder, not the scientific interpretation of that decoder.

## Python access

```python
from pathlib import Path
import zarr

path = Path("../results/CN_SiA_1.zarr")
root = zarr.open_group(path, mode="r")
assert root["conversion"].attrs["conversion_status"] == "complete"
plane = root["stored_signal"][0, 0, :, :]
```

Optional xarray access (installed in the repository development environment):

```python
import xarray as xr

ds = xr.open_zarr(path, chunks=None, consolidated=False)
plane = ds.stored_signal.isel(acquisition_index=0, channel=0).values
```

Named dimensions use native Zarr v3 metadata. `channel_label` is an auxiliary coordinate. `chunks=None` avoids adding Dask; indexing loads the requested data. The source header and completion receipt remain accessible through Zarr subgroups.

## Verify an existing store

```sh
uv run --extra zarr --frozen sims-reader verify ../results/CN_SiA_1.zarr \
  --source ../CN_SiA_1.im --accept-provisional
```

Verification opens both inputs read-only and returns a JSON report with exit status zero on success or nonzero on failure. It checks completion, source and header hashes, source-derived metadata, schema, labels, coordinates, chunk presence, and every plane. Files may be relocated: historical source and destination paths are retained rather than compared with current locations. The reader code hash and historical software versions are structurally checked but cannot be authenticated from the raw file. This is not proof against deliberate tampering or simultaneous modification of the output; verify a quiescent store. A pass establishes agreement with the current provisional decoder, not vendor validation.
