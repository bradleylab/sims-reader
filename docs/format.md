# Observed format contract

This contract describes a reverse-engineered layout supported by one local Cameca 7f-GEO specimen. It is not a vendor specification. Constants originate in the workspace's original `FORMAT_INVESTIGATION.md` and `scripts/preview_probe.py`; those specimen-bearing files remain outside the repository.

## Supported structure

The first little-endian int32 is 4201. Its vendor meaning is unknown. The next word is 84, which points to the first metadata section. A complete 84-byte directory holds the identifier, seven increasing section pointers, and thirteen unused entries containing -1. The parser requires this observed pattern rather than interpreting arbitrary `.im` variants as equivalent.

The sixth section pointer (directory word index 6) identifies a channel directory. Its first int32 is a channel count. Each subsequent active channel record is 268 bytes: a marker of 100, a record length of 268, an image-table pointer, and 256 bytes containing a null-terminated ASCII label. Names are retained verbatim, including raw name-field bytes. Unrecognized encodings are rejected, not replaced or coerced.

Each image table begins with eighteen int32 words. The supported pattern is `103, 72, 1, <plane_count>, <plane_bytes>, 4`, followed by twelve zero words. All fixed values are observed markers, not interpreted enumeration meanings. In particular, neither 1 nor 4 is asserted to be the pixel-type code. The table header is followed by `plane_count` absolute image offsets.

The first image offset across channels defines the header boundary. All parsed metadata and active top-level pointers must precede it. The complete preceding byte sequence is available through `read_header()` so undecoded metadata can be preserved.

Supported channels have equal block lengths and plane counts. Each acquisition index contains one block per channel in channel-directory order. The parser checks every pointer against that order and requires the final block to end exactly at EOF. Truncation, trailing data, gaps, overlap, non-monotonic pointers, unexpected flags, and uneven channel layouts fail explicitly. These restrictions may reject valid but unstudied Cameca variants; rejection is preferable to silently interpreting them with an unsupported layout.

## Provisional pixel interpretation

The candidate dtype is little-endian uint16. The candidate side length is the integer square root of `plane_bytes / 2`, accepted only when that square exactly accounts for the block. This preserves the original investigation's hypothesis; it does not decode a vendor dimension field. Numerical reading requires `accept_provisional=True`.

Rows and columns follow C-order reshaping without flipping or transposing. All stored values, including zero, are retained. Physical units, scale, acquisition timing, and prior correction status are unknown. The specimen's small values cannot establish signedness; uint16 remains provisional even though synthetic tests verify that its full range is preserved mechanically.

An image block's byte-perfect decode/re-encode checks implementation integrity. Spatial coherence and the operator's approximate recognition support plausibility. Neither establishes calibrated values, orientation, or full compatibility. Additional files and a Cameca numerical export are required for that.

## Relationship to existing software

The investigation tried `sims==2.0.2`, whose `peek()` method treats the second int32 as a file-type code when detecting byte order. The second word in this layout is instead consistent with a pointer, so that method rejects the file before parsing. This package implements the observed pointer-based structure independently; it does not patch or copy the upstream parser.

References: [sims package](https://pypi.org/project/sims/) and [upstream source](https://github.com/zanpeeters/sims/blob/master/sims/sims.py). Public documentation from [Cameca WinImage](https://www.cameca.com/service/software/winimage) describes support for Cameca Microsoft and UNIX `.im` files; WinImage is a potential reference for future comparison.
