"""Generate thumbnails from arbitrary image bytes.

Pillow (PIL) handles JPEG, PNG, WebP, GIF, etc. We always output JPEG (small,
universal, no alpha). Aspect ratio is preserved.

The compositing step for RGBA images pastes onto a white background so the
result looks correct (JPEG doesn't support alpha).
"""
from io import BytesIO

from PIL import Image


def generate_thumbnail(source_bytes: bytes, max_width: int = 400) -> bytes:
    """Return JPEG bytes resized so width <= max_width, height scaled proportionally."""
    img = Image.open(BytesIO(source_bytes))

    # Resize only if wider than max_width (no upscaling).
    if img.width > max_width:
        ratio = max_width / img.width
        new_height = max(1, int(img.height * ratio))
        img = img.resize((max_width, new_height), Image.LANCZOS)

    # JPEG needs RGB; composite RGBA onto white background.
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])  # alpha channel
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    output = BytesIO()
    img.save(output, format="JPEG", quality=85)
    return output.getvalue()