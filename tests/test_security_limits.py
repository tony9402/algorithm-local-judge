from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path

from judge.core.errors import LimitExceededError
from judge.utils.limited_io import (
    content_length,
    copy_limited,
    ensure_text_limit,
    write_text_limited,
)


class SecurityLimitsTest(unittest.TestCase):
    """Tests for byte-limit helpers used by upload and download paths."""

    def test_copy_limited_accepts_exact_limit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-limit-test-") as tmp:
            target = Path(tmp) / "source.py"
            written = copy_limited(
                io.BytesIO(b"abcd"),
                target,
                limit_bytes=4,
                label="source upload",
                chunk_size=2,
            )
            self.assertEqual(written, 4)
            self.assertEqual(target.read_bytes(), b"abcd")

    def test_copy_limited_rejects_and_removes_partial_file(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-limit-test-") as tmp:
            target = Path(tmp) / "source.py"
            with self.assertRaisesRegex(LimitExceededError, "source upload exceeds"):
                copy_limited(
                    io.BytesIO(b"abcdef"),
                    target,
                    limit_bytes=4,
                    label="source upload",
                    chunk_size=2,
                )
            self.assertFalse(target.exists())

    def test_text_limit_uses_utf8_bytes(self) -> None:
        self.assertEqual(ensure_text_limit("가", 3, "source text"), "가".encode())
        with self.assertRaisesRegex(LimitExceededError, "source text exceeds"):
            ensure_text_limit("가", 2, "source text")

    def test_write_text_limited_uses_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="alj-limit-test-") as tmp:
            target = Path(tmp) / "main.py"
            written = write_text_limited("abc", target, limit_bytes=3, label="source text")
            self.assertEqual(written, 3)
            self.assertEqual(target.read_text(encoding="utf-8"), "abc")

    def test_content_length_parsing(self) -> None:
        self.assertEqual(content_length({"Content-Length": "42"}), 42)
        self.assertEqual(content_length({"content-length": "7"}), 7)
        self.assertIsNone(content_length({"Content-Length": "bad"}))
        self.assertIsNone(content_length({}))


if __name__ == "__main__":
    unittest.main()
