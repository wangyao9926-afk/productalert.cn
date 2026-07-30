from __future__ import annotations

import hashlib
import struct
import unittest
import zlib

from app.visual_evidence import screenshot_hash, visual_change_ratio


def png_for_pixel(red: int, green: int, blue: int, alpha: int = 255) -> bytes:
    """Create a deterministic one-pixel RGBA PNG without image libraries."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    body = zlib.compress(b"\x00" + bytes((red, green, blue, alpha)))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", body) + chunk(b"IEND", b"")


class VisualEvidenceTests(unittest.TestCase):
    def test_identical_screenshot_has_stable_hash_and_zero_visual_change(self) -> None:
        white = png_for_pixel(255, 255, 255)

        self.assertEqual(screenshot_hash(white), hashlib.sha256(white).hexdigest())
        self.assertEqual(visual_change_ratio(white, white), 0.0)

    def test_single_changed_pixel_reports_full_visual_change(self) -> None:
        white = png_for_pixel(255, 255, 255)
        black = png_for_pixel(0, 0, 0)

        self.assertNotEqual(screenshot_hash(white), screenshot_hash(black))
        self.assertEqual(visual_change_ratio(white, black), 1.0)


if __name__ == "__main__":
    unittest.main()
