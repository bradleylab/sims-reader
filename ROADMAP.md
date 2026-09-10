# Roadmap

## Current scope: .im to Zarr

Maintain a narrowly scoped reader and lossless, verified local Zarr translator. Preserve raw header bytes, source provenance, stored labels, acquisition order, and explicit uncertainties. Existing applications handle viewing and ROI work; no custom viewer or analysis suite is planned here.

## Format validation

Compare additional specimens and a matching Cameca numerical/display export to establish pixel type, dimensions, orientation, scale, signal units, timing, and detector metadata. Unsupported variants must fail explicitly. Keep private specimens outside the repository and use synthetic fixtures for routine tests.

## Interoperability

Test an existing viewer against representative outputs. Consider an optional OME-Zarr export only after resolving acquisition-axis semantics or agreeing on a per-acquisition image collection. Keep the lossless canonical data intact. See `docs/viewers.md` for the current assessment.

## Distribution

The repository is public at https://github.com/bradleylab/sims-reader. License selection and a versioned release remain outstanding. Commit and publication actions require approval.

## Next development plan

See [the next-steps plan](docs/next-steps.md) for sample and vendor validation, sidecar metadata investigation, broader format coverage, standalone verification, batch conversion, continuous integration, release preparation, and conditional OME-Zarr export. Local Beads issues track this plan; no implementation work is started by creating those issues.
