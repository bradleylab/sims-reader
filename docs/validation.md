# Format validation protocol

This protocol separates storage fidelity from interpretation of the instrument
format. Passing the converter's tests does not establish pixel signedness,
orientation, physical scale, or acquisition timing.

## Inventory before decoding

Save a complete, paginated source listing privately, including file IDs,
versions, byte sizes, and remote checksums. Preserve original downloads without
renaming their contents or editing headers. Pair companions by exact filename
within the same folder and label that pairing as unvalidated until their
contents agree. Keep missing or ambiguous companions explicit.

`scripts/inventory_samples.py` produces a private matrix from that listing:

```sh
uv run --extra zarr --frozen python scripts/inventory_samples.py \
  --snapshot /private/path/box-inventory.json \
  --local-root /private/path/local-files \
  --output /private/path/sample-matrix.json
```

The local layout is `local-files/<folder-id>/<original-filename>`. The script
compares available files with the recorded remote SHA-1 before structural
inspection. These hashes check transfer identity, not authenticity against
malicious changes. Initial byte-size strata suggest candidate files only;
confirmed channel and acquisition diversity must come from inspected content.
The matrix and original files must remain outside the public repository.

## Required reference exports

For each selected acquisition, retain an export from a Cameca-compatible
application together with its application version, source identity, selected
channel and cycle, export settings, and processing history. Request both:

- A numerical pixel export with dimensions, row/column order, data type, and
  explicit statements about summation and any corrections or normalization.
- A display export identifying channel, cycle, orientation, and scale, with
  any cropping or display transforms recorded.

A screenshot corroborates appearance; it cannot establish numerical equality.
ROI spreadsheets and saved ROI files can help identify corresponding analyses,
but corrected ratios and summed ROI values are not raw pixel reference arrays.

## Comparisons and disposition

Compare dimensions, channel order, acquisition count, and raw pixel values
independently. For an untransformed integer reference, require exact equality.
Record discrepancies without changing axis order, scaling values, or selecting
a numerical tolerance merely to obtain agreement. If the export applies a
scientific transformation, document it and obtain agreement on a comparison
method before proceeding.

Compare sidecar fields with their exact source spelling, units, and acquisition
identity. Record conflicts between the binary file, sidecar, and vendor export.
Keep absent fields unknown; no default time interval, raster size, or depth may
be inferred from the file's appearance. A field mapping proposal precedes any
calibrated output schema change.

Each tested layout needs a support-matrix entry with the evidence, remaining
unknowns, and explicit disposition. Preserve comparison scripts and private
reports. Public regression fixtures should be independently synthetic rather
than copied private headers or pixel arrays. Changes to scientific
interpretation require researcher approval even when synthetic tests pass.
