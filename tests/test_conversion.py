"""Lossless conversion, xarray interoperability, and incomplete-output handling."""

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import numpy as np
import xarray as xr
import zarr
from fixtures import make_fixture

from sims_reader import ProvisionalFormatError, convert_to_zarr
from sims_reader._zarr_schema import VerificationError, verify_store
from sims_reader.cli import main


class ConversionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.fixture = make_fixture(self.folder / "input.im")
        self.destination = self.folder / "output.zarr"

    def test_lossless_zarr_and_xarray(self) -> None:
        result = convert_to_zarr(self.fixture.path, self.destination, accept_provisional=True)
        root = zarr.open_group(self.destination, mode="r")
        np.testing.assert_array_equal(root["stored_signal"][:], self.fixture.arrays)
        self.assertEqual(root["stored_signal"].dtype, np.dtype("<u2"))
        self.assertEqual(
            root["source/header"][:].tobytes(), self.fixture.raw[: self.fixture.payload]
        )
        self.assertEqual(root.attrs["conversion_status"], "complete")
        self.assertEqual(root.attrs["format_status"], "provisional")
        self.assertIsNone(root.attrs["source_metadata"]["signal_units"])
        self.assertFalse((self.destination / ".partial").exists())
        receipt = dict(zarr.open_group(self.destination / "conversion", mode="r").attrs)
        self.assertEqual(receipt["conversion_status"], "complete")
        self.assertEqual(result.planes_verified, 6)
        self.assertEqual(result.chunks, (1, 1, 4, 4))
        self.assertEqual(self.fixture.path.read_bytes(), self.fixture.raw)
        for mask_and_scale in (True, False):
            with xr.open_zarr(
                self.destination, chunks=None, consolidated=False, mask_and_scale=mask_and_scale
            ) as ds:
                self.assertEqual(
                    ds.stored_signal.dims, ("acquisition_index", "channel", "row", "column")
                )
                self.assertEqual(ds.stored_signal.dtype, np.dtype("uint16"))
                self.assertEqual(ds.stored_signal.values[0, 0, 0, 0], 0)
                self.assertEqual(ds.stored_signal.values[-1, -1, -1, -1], 65535)
                np.testing.assert_array_equal(ds.stored_signal.values, self.fixture.arrays)
                self.assertEqual(list(ds.channel_label.values), ["synthetic-A", "synthetic-B"])
                self.assertIn("channel_label", ds.coords)

    def test_custom_chunks_and_cli(self) -> None:
        with redirect_stdout(io.StringIO()) as output:
            status = main(
                [
                    "convert",
                    str(self.fixture.path),
                    str(self.destination),
                    "--accept-provisional",
                    "--spatial-chunks",
                    "3",
                    "2",
                ]
            )
        self.assertEqual(status, 0, output.getvalue())
        root = zarr.open_group(self.destination, mode="r")
        self.assertEqual(root["stored_signal"].chunks, (1, 1, 3, 2))
        np.testing.assert_array_equal(root["stored_signal"][:], self.fixture.arrays)

    def test_existing_and_symlink_destinations_untouched(self) -> None:
        self.destination.mkdir()
        sentinel = self.destination / "existing.txt"
        sentinel.write_text("preserve")
        with self.assertRaises(FileExistsError):
            convert_to_zarr(self.fixture.path, self.destination, accept_provisional=True)
        self.assertEqual(sentinel.read_text(), "preserve")
        alias = self.folder / "alias.zarr"
        alias.symlink_to(self.folder / "absent")
        with self.assertRaises(FileExistsError):
            convert_to_zarr(self.fixture.path, alias, accept_provisional=True)
        self.assertTrue(alias.is_symlink())

    def test_no_output_without_consent_or_valid_parameters(self) -> None:
        with self.assertRaises(ProvisionalFormatError):
            convert_to_zarr(self.fixture.path, self.destination)
        self.assertFalse(self.destination.exists())
        for chunks in ((0, 2), (-1, 2), (5, 2), (True, 2)):
            with self.subTest(chunks=chunks), self.assertRaises(ValueError):
                convert_to_zarr(
                    self.fixture.path,
                    self.destination,
                    accept_provisional=True,
                    spatial_chunks=chunks,
                )
            self.assertFalse(self.destination.exists())

    def test_corrupt_value_fails_before_promotion(self) -> None:
        def corrupt(path, image, attrs):
            root = zarr.open_group(path, mode="r+")
            root["stored_signal"][0, 0, 0, 0] = 999  # Explicit synthetic corruption.
            return verify_store(path, image, attrs)

        with patch("sims_reader._zarr_schema.verify_store", side_effect=corrupt):
            with self.assertRaisesRegex(VerificationError, "Pixel mismatch"):
                convert_to_zarr(self.fixture.path, self.destination, accept_provisional=True)
        self.assertFalse((self.destination / "zarr.json").exists())
        self.assertTrue((self.destination / ".partial").is_dir())
        self.assertEqual(
            dict(zarr.open_group(self.destination / "conversion", mode="r").attrs)[
                "conversion_status"
            ],
            "failed",
        )

    def test_missing_zero_chunk_is_not_silently_filled(self) -> None:
        raw = bytearray(self.fixture.raw)
        size = self.fixture.arrays[0, 0].nbytes
        raw[self.fixture.payload : self.fixture.payload + size] = bytes(size)
        self.fixture.path.write_bytes(raw)

        def remove_zero_chunk(path, image, attrs):
            root = zarr.open_group(path, mode="r")
            data = root["stored_signal"]
            key = data.metadata.encode_chunk_key((0, 0, 0, 0))
            (path / "stored_signal" / key).unlink()
            return verify_store(path, image, attrs)

        with patch("sims_reader._zarr_schema.verify_store", side_effect=remove_zero_chunk):
            with self.assertRaisesRegex(VerificationError, "Missing stored chunks"):
                convert_to_zarr(self.fixture.path, self.destination, accept_provisional=True)

    def test_metadata_corruption_rejected(self) -> None:
        def corrupt(path, image, attrs):
            root = zarr.open_group(path, mode="r+")
            root.attrs["source_sha256"] = "incorrect"
            return verify_store(path, image, attrs)

        with patch("sims_reader._zarr_schema.verify_store", side_effect=corrupt):
            with self.assertRaisesRegex(VerificationError, "provenance"):
                convert_to_zarr(self.fixture.path, self.destination, accept_provisional=True)
