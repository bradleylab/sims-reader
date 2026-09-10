"""Reader contracts checked against explicitly synthetic files."""

import hashlib
import io
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np
from fixtures import make_fixture

from sims_reader import FormatError, ImageFile, ProvisionalFormatError, SourceChangedError
from sims_reader._format import parse


class ReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = make_fixture(Path(self.temporary.name) / "fixture.im")

    def test_every_plane_exact_and_source_unchanged(self) -> None:
        f = self.fixture
        with ImageFile(f.path, accept_provisional=True) as image:
            self.assertEqual(image.metadata.status, "provisional")
            self.assertIsNone(image.metadata.signal_units)
            self.assertIsNone(image.metadata.pixel_size)
            self.assertEqual(image.metadata.acquisition_count, f.arrays.shape[0])
            self.assertEqual(image.read_header(), f.raw[: f.payload])
            self.assertEqual(image.source_sha256(), hashlib.sha256(f.raw).hexdigest())
            for channel in image.metadata.channels:
                for index, plane in enumerate(image.iter_planes(channel.label)):
                    np.testing.assert_array_equal(plane, f.arrays[index, channel.index])
                    self.assertFalse(plane.flags.writeable)
                    self.assertEqual(plane.dtype, np.dtype("<u2"))
        self.assertEqual(f.path.read_bytes(), f.raw)
        self.assertEqual(int(plane[-1, -1]), 65535)  # Synthetic sentinel survives close.

    def test_relocated_header_and_different_square_size(self) -> None:
        f = make_fixture(self.fixture.path, side=8, acquisitions=2, padding=100)
        with ImageFile(f.path, accept_provisional=True) as image:
            self.assertEqual(image.metadata.header_bytes, f.payload)
            self.assertEqual(image.metadata.candidate_plane_shape, (8, 8))
            np.testing.assert_array_equal(image.read_plane(1, 1), f.arrays[1, 1])

    def test_explicit_opt_in(self) -> None:
        with ImageFile(self.fixture.path) as image:
            self.assertEqual(len(image.metadata.channels), 2)
            with self.assertRaises(ProvisionalFormatError):
                image.read_plane(0, 0)

    def test_bad_selectors(self) -> None:
        with ImageFile(self.fixture.path, accept_provisional=True) as image:
            for selector in (-1, 2):
                with self.subTest(selector=selector), self.assertRaises(IndexError):
                    image.read_plane(selector, 0)
            with self.assertRaises(ValueError):
                image.channel("absent")
            for index in (-1, 3):
                with self.subTest(index=index), self.assertRaises(IndexError):
                    image.read_plane(0, index)
            for index in (True, 1.5):
                with self.subTest(index=index), self.assertRaises(TypeError):
                    image.read_plane(0, index)
            with self.assertRaises(TypeError):
                image.channel(True)

    def test_duplicate_names_use_index(self) -> None:
        f = make_fixture(self.fixture.path, labels=("same", "same"))
        with ImageFile(f.path, accept_provisional=True) as image:
            with self.assertRaisesRegex(ValueError, "2 matches"):
                image.read_plane("same", 0)
            np.testing.assert_array_equal(image.read_plane(1, 0), f.arrays[0, 1])

    def test_modified_source_rejected(self) -> None:
        with ImageFile(self.fixture.path, accept_provisional=True) as image:
            with self.fixture.path.open("ab") as stream:
                stream.write(b"changed")
            with self.assertRaises(SourceChangedError):
                image.read_plane(0, 0)
            with self.assertRaises(SourceChangedError):
                image.source_sha256()

    def test_closed_reader_rejected(self) -> None:
        image = ImageFile(self.fixture.path, accept_provisional=True)
        image.close()
        with self.assertRaisesRegex(ValueError, "closed"):
            image.read_plane(0, 0)

    def test_parse_reads_no_payload(self) -> None:
        fixture = self.fixture

        class HeaderOnlyStream(io.BytesIO):
            def read(self, size: int = -1) -> bytes:
                if size < 0 or self.tell() + size > fixture.payload:
                    raise AssertionError("Parser tried to read image payload")
                return super().read(size)

        parse(HeaderOnlyStream(fixture.raw), len(fixture.raw))

    def test_structural_corruption_rejected(self) -> None:
        f = self.fixture
        cases = {
            "signature": (0, 0),
            "directory length": (4, 0),
            "section bounds": (24, len(f.raw)),
            "extra section": (32, 84),
            "channel count": (164, -1),
            "record type": (f.records[0], 0),
            "table bounds": (f.records[0] + 8, len(f.raw)),
            "table type": (f.tables[0], 0),
            "table unknown flag": (f.tables[0] + 20, 0),
            "plane count": (f.tables[0] + 12, -1),
            "huge count": (f.tables[0] + 12, 2**31 - 1),
            "shape": (f.tables[0] + 16, 0),
            "overlap": (f.tables[0] + 76, f.payload),
            "gap": (f.tables[0] + 76, f.payload + 65),
            "payload pointer in header": (f.tables[0] + 72, 84),
        }
        for name, (offset, value) in cases.items():
            with self.subTest(name=name):
                raw = bytearray(f.raw)
                struct.pack_into("<i", raw, offset, value)
                with self.assertRaises(FormatError):
                    parse(io.BytesIO(raw), len(raw))

    def test_truncation_and_trailing_bytes_rejected(self) -> None:
        for raw in (b"", self.fixture.raw[:4], self.fixture.raw[:-1], self.fixture.raw + b"\0"):
            with self.subTest(size=len(raw)), self.assertRaises(FormatError):
                parse(io.BytesIO(raw), len(raw))

    def test_non_ascii_name_rejected_without_coercion(self) -> None:
        raw = bytearray(self.fixture.raw)
        raw[self.fixture.records[0] + 12] = 255
        with self.assertRaisesRegex(FormatError, "Non-ASCII"):
            parse(io.BytesIO(raw), len(raw))
