"""Batch accounting, discovery, collisions, interruptions, and preservation."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from fixtures import make_fixture

from sims_reader.batch import _plan, convert_batch
from sims_reader.cli import main
from sims_reader.conversion import convert_to_zarr


class BatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.outputs = self.root / "outputs"

    def test_mixed_files_have_ordered_complete_accounting(self):
        make_fixture(self.inputs / "z.IM")
        make_fixture(self.inputs / "a.im")
        (self.inputs / "broken.im").write_bytes(b"unsupported")
        (self.inputs / "notes.txt").write_text("not an input")
        original = {p.name: p.read_bytes() for p in self.inputs.iterdir()}
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            status = main(["batch", str(self.inputs), str(self.outputs), "--accept-provisional"])
        report = json.loads(out.getvalue())
        self.assertEqual(status, 1)
        self.assertEqual((report["discovered"], report["succeeded"], report["failed"]), (3, 2, 1))
        self.assertEqual(
            [Path(r["source"]).name for r in report["items"]], ["a.im", "broken.im", "z.IM"]
        )
        self.assertIn("[3/3]", err.getvalue())
        self.assertEqual(original, {p.name: p.read_bytes() for p in self.inputs.iterdir()})

    def test_recursive_preserves_subdirectories_and_existing_targets(self):
        make_fixture(self.inputs / "same.im")
        nested = self.inputs / "nested"
        nested.mkdir()
        make_fixture(nested / "same.im")
        first = convert_batch(self.inputs, self.outputs, accept_provisional=True)
        self.assertEqual(first.discovered, 1)
        before = (self.outputs / "same.zarr" / "zarr.json").read_bytes()
        second = convert_batch(self.inputs, self.outputs, recursive=True, accept_provisional=True)
        self.assertEqual((second.succeeded, second.failed), (1, 1))
        self.assertTrue((self.outputs / "nested" / "same.zarr" / "zarr.json").exists())
        self.assertEqual(before, (self.outputs / "same.zarr" / "zarr.json").read_bytes())

    def test_case_and_ancestor_collisions_are_preflighted(self):
        # Explicit synthetic path plans also exercise case-sensitive platforms.
        _, errors = _plan([self.inputs / "a.im", self.inputs / "A.IM"], self.inputs, self.outputs)
        self.assertEqual(set(errors), {0, 1})
        make_fixture(self.inputs / "a.im")
        nested = self.inputs / "a.zarr"
        nested.mkdir()
        make_fixture(nested / "b.im")
        result = convert_batch(self.inputs, self.outputs, recursive=True, accept_provisional=True)
        self.assertEqual(result.failed, 2)
        self.assertFalse(self.outputs.exists())

    def test_interrupted_file_and_remaining_inputs_are_reported(self):
        for name in ("a.im", "b.im", "c.im"):
            make_fixture(self.inputs / name)

        def convert(source, target, **kwargs):
            if source.name == "b.im":
                target.mkdir()
                (target / ".partial").mkdir()
                raise KeyboardInterrupt
            return convert_to_zarr(source, target, **kwargs)

        with patch("sims_reader.batch.convert_to_zarr", side_effect=convert):
            result = convert_batch(self.inputs, self.outputs, accept_provisional=True)
        self.assertEqual([i.status for i in result.items], ["complete", "failed", "not_attempted"])
        self.assertTrue((self.outputs / "b.zarr" / ".partial").exists())
        retry = convert_batch(self.inputs, self.outputs, accept_provisional=True)
        self.assertEqual((retry.succeeded, retry.failed), (1, 2))

    def test_opt_in_empty_and_overlapping_trees(self):
        with self.assertRaises(ValueError):
            convert_batch(self.inputs, self.outputs)
        with self.assertRaisesRegex(ValueError, "No .im"):
            convert_batch(self.inputs, self.outputs, accept_provisional=True)
        make_fixture(self.inputs / "a.im")
        with self.assertRaisesRegex(ValueError, "disjoint"):
            convert_batch(self.inputs, self.inputs / "output", accept_provisional=True)
        self.assertFalse(self.outputs.exists())

    def test_symbolic_link_input_is_reported(self):
        source = make_fixture(self.root / "outside.im").path
        try:
            (self.inputs / "alias.im").symlink_to(source)
        except OSError:
            self.skipTest("Symlink creation unavailable")
        result = convert_batch(self.inputs, self.outputs, accept_provisional=True)
        self.assertEqual(result.failed, 1)
        self.assertFalse(self.outputs.exists())
