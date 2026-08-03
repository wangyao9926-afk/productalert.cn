from __future__ import annotations

import hashlib
import io

from PIL import Image, ImageChops


def screenshot_hash(png: bytes) -> str:
    return hashlib.sha256(png).hexdigest()


def visual_change_ratio(before: bytes, after: bytes) -> float:
    """Return the share of pixels that differ after normalizing both PNGs."""
    if before == after:
        return 0.0

    with Image.open(io.BytesIO(before)) as before_image, Image.open(io.BytesIO(after)) as after_image:
        target_size = (
            max(before_image.width, after_image.width),
            max(before_image.height, after_image.height),
        )
        before_rgba = before_image.convert("RGBA").resize(target_size)
        after_rgba = after_image.convert("RGBA").resize(target_size)
        difference = ImageChops.difference(before_rgba, after_rgba)
        changed_pixels = sum(1 for pixel in difference.getdata() if pixel != (0, 0, 0, 0))
        return changed_pixels / (target_size[0] * target_size[1])
