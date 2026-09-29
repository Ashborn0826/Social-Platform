"""Pillow thumbnail generation tests.

We construct small test images in-memory (no fixture files needed) and
verify the output dimensions, format, and aspect-ratio preservation.
"""
import io

from PIL import Image

from app.media_processing.thumbnail import generate_thumbnail


def _make_jpeg(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), (100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png(width: int, height: int) -> bytes:
    img = Image.new("RGBA", (width, height), (100, 150, 200, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_thumbnail_resizes_to_max_width():
    src = _make_jpeg(800, 600)
    thumb = generate_thumbnail(src, max_width=400)
    img = Image.open(io.BytesIO(thumb))
    assert img.width == 400
    # Aspect ratio: 800:600 → 400:300
    assert img.height == 300


def test_thumbnail_does_not_enlarge_small_images():
    src = _make_jpeg(200, 150)
    thumb = generate_thumbnail(src, max_width=400)
    img = Image.open(io.BytesIO(thumb))
    assert img.width == 200
    assert img.height == 150


def test_thumbnail_output_is_jpeg():
    src = _make_jpeg(800, 600)
    thumb = generate_thumbnail(src, max_width=400)
    img = Image.open(io.BytesIO(thumb))
    assert img.format == "JPEG"


def test_thumbnail_png_with_alpha_composites_to_white_background():
    src = _make_png(800, 600)
    thumb = generate_thumbnail(src, max_width=400)
    img = Image.open(io.BytesIO(thumb))
    assert img.mode == "RGB"
    assert img.width == 400


def test_thumbnail_preserves_aspect_ratio_for_16_9():
    src = _make_jpeg(1920, 1080)
    thumb = generate_thumbnail(src, max_width=400)
    img = Image.open(io.BytesIO(thumb))
    assert img.width == 400
    # 1920:1080 = 16:9 → 400:225
    assert img.height == 225


def test_thumbnail_default_max_width_is_400():
    src = _make_jpeg(1000, 1000)
    thumb = generate_thumbnail(src)  # no max_width arg → default
    img = Image.open(io.BytesIO(thumb))
    assert img.width == 400


def test_thumbnail_output_is_smaller_than_input():
    """The thumbnail bytes should be smaller (400 px < 800 px, JPEG quality 85)."""
    src = _make_jpeg(800, 600)
    thumb = generate_thumbnail(src, max_width=400)
    assert len(thumb) < len(src)
