"""CLI error, provenance, and non-overwriting output behavior."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import numpy as np
from fixtures import make_fixture

from sims_reader.cli import main


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.fixture = make_fixture(self.folder / "test.im")

    def invoke(self, args: list[str]) -> tuple[int, str, str]:
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            result = main(args)
        return result, output.getvalue(), error.getvalue()

    def test_inspection_json(self) -> None:
        status, output, error = self.invoke(["inspect", str(self.fixture.path), "--hash"])
        self.assertEqual(status, 0, error)
        info = json.loads(output)
        self.assertEqual(info["status"], "provisional")
        self.assertEqual(info["header_bytes"], self.fixture.payload)
        self.assertEqual(info["channels"][0]["label"], "synthetic-A")
        self.assertEqual(len(info["source_sha256"]), 64)

    def test_plane_requires_opt_in_and_preserves_output(self) -> None:
        output = self.folder / "extraction"
        args = [
            "plane",
            str(self.fixture.path),
            "--channel-index",
            "1",
            "--index",
            "2",
            "--output-dir",
            str(output),
        ]
        status, _, error = self.invoke(args)
        self.assertEqual(status, 1)
        self.assertIn("provisional", error)
        self.assertFalse(output.exists())
        status, _, error = self.invoke(args + ["--accept-provisional"])
        self.assertEqual(status, 0, error)
        np.testing.assert_array_equal(np.load(output / "plane.npy"), self.fixture.arrays[2, 1])
        info = json.loads((output / "metadata.json").read_text())
        self.assertEqual(info["selected_acquisition_index"], 2)
        self.assertEqual(info["status"], "provisional")
        before = (output / "plane.npy").read_bytes()
        status, _, error = self.invoke(args + ["--accept-provisional"])
        self.assertEqual(status, 1)
        self.assertEqual((output / "plane.npy").read_bytes(), before)

    def test_invalid_file_has_concise_error(self) -> None:
        self.fixture.path.write_bytes(b"bad")
        status, _, error = self.invoke(["inspect", str(self.fixture.path)])
        self.assertEqual(status, 1)
        self.assertIn("sims-reader:", error)
        self.assertNotIn("Traceback", error)
