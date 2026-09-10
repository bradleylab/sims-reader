"""Independent verification must detect damage without repairing it."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import zarr
from fixtures import make_fixture

from sims_reader import convert_to_zarr
from sims_reader.cli import main
from sims_reader.verification import verify_zarr


class VerificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)
        self.source = make_fixture(self.path / "source.im").path
        self.store = self.path / "output.zarr"
        convert_to_zarr(self.source, self.store, accept_provisional=True)

    def snapshot(self):
        return {
            str(p.relative_to(self.path)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in self.path.rglob("*")
            if p.is_file()
        }

    def test_moved_source_and_store_pass_read_only(self):
        self.source = self.source.rename(self.path / "moved.im")
        self.store = self.store.rename(self.path / "moved.zarr")
        before = self.snapshot()
        result = verify_zarr(self.store, self.source, accept_provisional=True)
        self.assertEqual(result.planes_verified, 6)
        self.assertEqual(before, self.snapshot())

    def test_corruption_and_failure_reports(self):
        mutations = {
            "pixel": lambda r: r["stored_signal"].__setitem__((0, 0, 0, 0), 17),
            "metadata": lambda r: r.attrs.__setitem__("header_sha256", "wrong"),
            "receipt": lambda r: r["conversion"].attrs.__setitem__("planes_verified", 0),
            "incomplete": lambda r: r["conversion"].attrs.__setitem__(
                "conversion_status", "failed"
            ),
            "coordinate_units": lambda r: r["row"].attrs.__setitem__("units", "meters"),
            "labels": lambda r: r["channel_label"].__setitem__(0, "wrong"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                target = self.path / (name + ".zarr")
                convert_to_zarr(self.source, target, accept_provisional=True)
                mutate(zarr.open_group(target, mode="r+"))
                before = self.snapshot()
                with redirect_stdout(io.StringIO()) as output:
                    status = main(
                        [
                            "verify",
                            str(target),
                            "--source",
                            str(self.source),
                            "--accept-provisional",
                        ]
                    )
                self.assertEqual(status, 1)
                self.assertEqual(json.loads(output.getvalue())["verification_status"], "failed")
                self.assertEqual(before, self.snapshot())

    def test_wrong_source_and_missing_chunk(self):
        wrong = make_fixture(self.path / "wrong.im", labels=("different", "labels")).path
        with self.assertRaises(ValueError):
            verify_zarr(self.store, wrong, accept_provisional=True)
        root = zarr.open_group(self.store, mode="r")
        key = root["stored_signal"].metadata.encode_chunk_key((0, 0, 0, 0))
        (self.store / "stored_signal" / key).unlink()
        with self.assertRaisesRegex(ValueError, "Missing stored chunks"):
            verify_zarr(self.store, self.source, accept_provisional=True)

    def test_missing_all_zero_chunk_fails(self):
        fixture = make_fixture(self.path / "zeros.im")
        raw = bytearray(fixture.raw)
        raw[fixture.payload : fixture.payload + fixture.arrays[0, 0].nbytes] = bytes(
            fixture.arrays[0, 0].nbytes
        )
        fixture.path.write_bytes(raw)
        target = self.path / "zeros.zarr"
        convert_to_zarr(fixture.path, target, accept_provisional=True)
        root = zarr.open_group(target, mode="r")
        key = root["stored_signal"].metadata.encode_chunk_key((0, 0, 0, 0))
        (target / "stored_signal" / key).unlink()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Missing stored chunks"):
            verify_zarr(target, fixture.path, accept_provisional=True)
        self.assertEqual(before, self.snapshot())

    def test_opt_in_and_success_json(self):
        with self.assertRaises(ValueError):
            verify_zarr(self.store, self.source)
        with redirect_stdout(io.StringIO()) as output:
            status = main(
                ["verify", str(self.store), "--source", str(self.source), "--accept-provisional"]
            )
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["verification_status"], "passed")
