# Next steps

## Scope and current state

The public repository is bradleylab/sims-reader. The existing converter preserves a narrowly supported provisional .im decoding in Zarr; the first acquisition has been displayed successfully in napari. This plan covers development work only. It does not authorize new scientific corrections, public sample release, or a custom viewer.

## Order of work

Start sample inventory and standalone verification independently; continuous integration can also start immediately. Inventory feeds vendor comparison and sidecar investigation. Verification feeds batch conversion. Broader parser support follows reference evidence. Release preparation follows CI, verification, and batch conversion. OME-Zarr requires an explicit semantic decision before conditional implementation.

Instrument sidecars may resolve metadata questions earlier than more binary reverse engineering. Their reported purpose is a lead to investigate, not proof that their fields are correctly decoded. Existing ROI files and spreadsheets may provide comparison context; they are not assumed to be uncorrected pixel exports.

## Planned work and acceptance criteria

### Inventory representative files and companion exports

Build a local-only inventory of authorized sample files and companions. Record checksums, sizes, file versions where available, pairing confidence, and missing companions. Select cases covering different sizes, channel layouts, and acquisition counts; file size alone does not establish format.

**Done when:** A reproducible inventory and representative sample matrix exist outside public Git. Each case has provenance and an explicit reason for selection. No private links, raw files, or sample metadata enter public fixtures.

**Depends on:** No prerequisite task.

### Validate decoding against authoritative Cameca exports

Compare selected specimens with matching numerical and display exports from Cameca-compatible software. Establish pixel type, dimensions, axis order, orientation, and stored-value semantics separately. ROI spreadsheets can corroborate context but are not raw pixel ground truth; corrections and aggregation must be understood before any comparison.

**Done when:** A reproducible comparison records exact agreement or explicit discrepancies for each tested field. Unknowns remain provisional. Any scientific interpretation change is presented for researcher approval before updating the format contract.

**Depends on:** Inventory representative files and companion exports.

### Investigate and preserve acquisition sidecar metadata

Inspect original .im_asc bytes and determine encoding, field grammar, units, channel associations, and acquisition timing. Treat .aso as ROI context, not a reason to build an ROI editor. Preserve original companion files and provenance in any proposed extension; distinguish source fields from inferred values.

**Done when:** A sourced field mapping and schema proposal identify scale, timing, detector metadata, unknowns, conflicts, and parsing failures. Tests can use independently synthetic text. No calibrated interpretation is enabled without supporting evidence and approval.

**Depends on:** Inventory representative files and companion exports.

### Expand supported-layout coverage and explicit failure diagnostics

Exercise the current reader against representative files, then implement only layouts backed by evidence. Add synthetic regression cases for discovered structural differences. Produce a support matrix and actionable errors for unsupported variants.

**Done when:** Each claimed layout has a documented source of evidence and synthetic tests. Unsupported layouts fail without fallback guesses, lost planes, or implicit coercion. Private samples remain optional local tests.

**Depends on:** Inventory representative files and companion exports; Validate decoding against authoritative Cameca exports.

### Add standalone Zarr verification command

Add sims-reader verify OUTPUT.zarr --source INPUT.im using the existing conversion verification logic. Check source hash, complete receipt, schema, coordinates, labels, original header, chunk presence, and all decoded planes. Verify read-only and emit a machine-readable report plus a nonzero exit status on failure. Preserve provenance and require explicit provisional acceptance for source decoding.

**Done when:** Valid output passes; corrupt pixels, missing all-zero chunks, wrong source, changed metadata, and incomplete stores fail. Tests show neither source nor output is mutated. Methods and CLI help describe exactly what a pass establishes.

**Depends on:** No prerequisite task.

### Add deterministic batch conversion and per-file reports

Convert a local directory with explicit discovery and recursion rules. Plan destination paths before writes, prevent basename collisions and overwrites, keep raw inputs read-only, stream data, and continue to independent files after per-file failures. Reuse mandatory conversion verification and provide progress and JSON summary.

**Done when:** Tests cover mixed valid and unsupported files, naming collisions, existing targets, interrupted output, and deterministic ordering. The report accounts for every discovered input with outcome and diagnostic. Any failure yields an unsuccessful batch exit status without hiding successful conversions.

**Depends on:** Add standalone Zarr verification command.

### Add continuous integration with synthetic fixtures

Add GitHub Actions for the existing unit tests, lint, type checks, and package build. Define a Python and operating-system support matrix consistent with package metadata and dependency availability. Keep GUI dependencies and private specimens out of routine CI.

**Done when:** A fresh checkout reproduces documented checks with the locked environment. CI has no data credentials or specimen downloads, and published platform claims match passing jobs. New verify and batch tests join the same suite as those features land.

**Depends on:** No prerequisite task.

### Prepare licensing and a versioned release

Choose a license with the owner, audit dependency and package metadata, update installation and napari examples, document provisional support and known limitations, and prepare release artifacts. Correct stale local-only status prose. PyPI publishing is a separate explicit decision.

**Done when:** The owner has selected the license; README, methods, changelog, and package metadata agree. A clean-environment install and CLI smoke test pass. Release artifacts contain no private data. Commit, tag, release, or package publication follows explicit approval.

**Depends on:** Add continuous integration with synthetic fixtures; Add standalone Zarr verification command; Add deterministic batch conversion and per-file reports.

### Decide an evidence-based OME-Zarr axis mapping

Compare ordinary Zarr with OME-Zarr using confirmed acquisition semantics and current specification requirements. Evaluate a per-acquisition image collection versus a justified time axis, including unknown physical calibration. Keep raw values intact and avoid derived projections without an agreed scientific method.

**Done when:** A decision document cites the selected specification version, explains axis and unit mapping, and identifies an existing viewer and reproducible compatibility test. It may conclude that export should remain deferred. The researcher approves any semantic assumptions.

**Depends on:** Validate decoding against authoritative Cameca exports; Investigate and preserve acquisition sidecar metadata.

### Implement and test optional OME-Zarr export after the mapping decision

If the mapping decision supports export, implement it as an optional output path preserving canonical raw values and source provenance. Test with the chosen existing viewer. This issue is conditional; a decision to defer OME-Zarr does not authorize implementation.

**Done when:** Output satisfies the selected specification, passes full value verification, and opens correctly in the selected viewer. Channel labels and acquisition mapping are checked. No bespoke viewer, unapproved downsampling, or silent axis reinterpretation is introduced.

**Depends on:** Decide an evidence-based OME-Zarr axis mapping.

## Tracking and boundaries

Local Beads issues track this plan with the stated dependencies. Priorities indicate suggested sequencing, not estimates. Keep issues open until acceptance evidence exists. Keep private inventories, Box references, proprietary data, and numerical comparison reports outside the public repository. Public tests use synthetic fixtures. Do not commit or publish this plan or Beads state without approval.

## Beads issue map

Epic: `sims-76c`. Execution is authorized under the active goal. Consult `bd list` for live status; this document defines scope and acceptance criteria.

| Issue | Work |
| --- | --- |
| `sims-76c.1` | Inventory representative files and companion exports |
| `sims-76c.2` | Validate decoding against authoritative Cameca exports |
| `sims-76c.3` | Investigate and preserve acquisition sidecar metadata |
| `sims-76c.4` | Expand supported-layout coverage and explicit failure diagnostics |
| `sims-76c.5` | Add standalone Zarr verification command |
| `sims-76c.6` | Add deterministic batch conversion and per-file reports |
| `sims-76c.7` | Add continuous integration with synthetic fixtures |
| `sims-76c.8` | Prepare licensing and a versioned release |
| `sims-76c.9` | Decide an evidence-based OME-Zarr axis mapping |
| `sims-76c.10` | Implement and test optional OME-Zarr export after the mapping decision |

Standalone verification and batch conversion are implemented and locally tested. Sample inventory and CI are in progress; vendor interpretation and hosted CI acceptance remain outstanding. The dependency graph was checked for cycles.
