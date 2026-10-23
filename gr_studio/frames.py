"""Photo frames shared by preview and full-resolution export."""

import math
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont, ImageOps

FRAME_FIELDS = (
    "border",
    "border_color",
    "border_width",
    "border_bottom",
    "border_ratio",
    "border_background",
    "border_radius",
)
RATIOS = {
    "1:1": (1, 1),
    "4:5": (4, 5),
    "9:16": (9, 16),
    "3:2": (3, 2),
    "2:3": (2, 3),
    "16:9": (16, 9),
}


def _font(size):
    for name in ("DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _percent(value, maximum):
    if not math.isfinite(value):
        raise ValueError("Frame values must be finite.")
    return max(0, min(maximum, value)) / 100


def frame(image, settings):
    if settings.border == "none":
        return image.copy()
    if settings.border not in {"classic", "square", "even", "canvas"}:
        raise ValueError(f"Unknown border: {settings.border}")
    if settings.border == "square":
        side = min(image.size)
        x, y = (image.width - side) // 2, (image.height - side) // 2
        image = image.crop((x, y, x + side, y + side))
    short = min(image.size)
    edge = round(short * _percent(settings.border_width, 30))
    polaroid = settings.border in {"classic", "square"}
    if polaroid and settings.border_width > 0:
        edge = max(8, edge)  # Preserve existing Polaroid sessions.
    bottom = (
        max(edge, round(short * _percent(settings.border_bottom, 50)))
        if polaroid
        else edge
    )
    width, height = image.width + 2 * edge, image.height + edge + bottom
    x, y = edge, edge
    if settings.border == "canvas":
        if settings.border_ratio not in RATIOS:
            raise ValueError("Unknown canvas ratio")
        rw, rh = RATIOS[settings.border_ratio]
        unit = math.ceil(max(width / rw, height / rh))
        width, height = rw * unit, rh * unit
        x, y = (width - image.width) // 2, (height - image.height) // 2
    # Reject pathological canvases before allocating an enormous bitmap.
    if width * height > 160_000_000:
        raise ValueError(
            "This frame would exceed 160 megapixels. Choose a closer canvas ratio or a smaller border."
        )
    if settings.border_background == "solid":
        color = settings.border_color
        framed = Image.new("RGB", (width, height), color)
    elif settings.border_background == "photo":
        sample = image.copy()
        sample.thumbnail((64, 64))
        color = sample.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
        framed = Image.new("RGB", (width, height), color)
    elif settings.border_background == "blur":
        sample = image.copy()
        sample.thumbnail((512, 512))
        bounds = (
            max(1, round(width * min(1, 512 / max(width, height)))),
            max(1, round(height * min(1, 512 / max(width, height)))),
        )
        background = ImageOps.fit(sample, bounds).filter(
            ImageFilter.GaussianBlur(max(bounds) * 0.035)
        )
        framed = background.resize((width, height), Image.Resampling.BILINEAR)
    else:
        raise ValueError("Unknown frame background")
    radius = round(short * _percent(settings.border_radius, 50))
    if radius:
        # Antialias a bounded mask, then enlarge it for full-resolution exports.
        scale = min(2, 1600 / max(image.size))
        mw, mh = max(1, round(image.width * scale)), max(1, round(image.height * scale))
        mask = Image.new("L", (mw, mh), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            (0, 0, mw - 1, mh - 1), radius=radius * scale, fill=255
        )
        mask = mask.resize(image.size, Image.Resampling.LANCZOS)
        framed.paste(image, (x, y), mask)
    else:
        framed.paste(image, (x, y))
    caption = settings.caption.strip().replace("\n", " ")[:160]
    if caption and polaroid and bottom >= short * 0.04:
        draw = ImageDraw.Draw(framed)
        font = _font(max(10, round(short * 0.025)))
        available = max(1, image.width - 2 * edge)
        original = caption
        while caption and draw.textlength(caption, font=font) > available:
            caption = caption[:-1]
        if caption != original:
            caption = caption[:-3].rstrip() + "..." if len(caption) > 3 else "..."
        box = draw.textbbox((0, 0), caption, font=font)
        tx = (width - draw.textlength(caption, font=font)) / 2
        ty = y + image.height + (bottom - (box[3] - box[1])) / 2 - box[1]
        color = framed.getpixel(
            (width // 2, min(height - 1, y + image.height + bottom // 2))
        )
        if isinstance(color, str):
            color = ImageColor.getrgb(color)
        ink = (
            "#f4f0e7"
            if sum(c * v for c, v in zip(color, (0.2126, 0.7152, 0.0722))) < 125
            else "#45433f"
        )
        draw.text((tx, ty), caption, font=font, fill=ink)
    return framed
