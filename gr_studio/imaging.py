"""Non-destructive JPEG/TIFF/PNG processing and conservative horizon correction."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import math
import os
import re

from .frames import frame as _frame
from .geometry import IDENTITY, transform_geometry
from .tuning import apply_tuning

import numpy as np
from PIL import Image, ImageCms, ImageOps


@dataclass
class EditSettings:
    exposure: float = 0.0
    contrast: float = 0.0
    highlights: float = 0.0
    shadows: float = 0.0
    saturation: float = 0.0
    warmth: float = 0.0
    whites: float = 0.0
    blacks: float = 0.0
    tint: float = 0.0
    vibrance: float = 0.0
    texture: float = 0.0
    clarity: float = 0.0
    dehaze: float = 0.0
    grain: float = 0.0
    vignette: float = 0.0
    sharpening: float = 0.0
    noise_reduction: float = 0.0
    curve: str = "Linear"
    mixer: dict[str, dict[str, float]] = field(default_factory=dict)
    angle: float = 0.0
    geometry: tuple = IDENTITY
    geometry_mode: str = "off"
    vertical: float = 0.0
    horizontal: float = 0.0
    aspect: float = 0.0
    border: str = "none"
    border_color: str = "#f4f0e7"
    caption: str = ""
    border_width: float = 5.5
    border_bottom: float = 20.0
    border_ratio: str = "1:1"
    border_background: str = "solid"
    border_radius: float = 0.0


def load_image(
    path: str | Path, max_size: int | tuple[int, int] | None = None
) -> Image.Image:
    """Return an independent, oriented RGB image in sRGB; never modify its source."""
    path = Path(path)
    if path.suffix.lower() in {".dng", ".nef", ".arw", ".cr2", ".cr3", ".raf"}:
        raise ValueError(
            "RAW editing is not available yet. Open the matching JPEG to edit it."
        )
    bounds = None
    if max_size is not None:
        bounds = (max_size, max_size) if isinstance(max_size, int) else max_size
        if len(bounds) != 2 or min(bounds) < 1:
            raise ValueError("Preview dimensions must be positive.")
    with Image.open(path) as source:
        if bounds is not None and source.format == "JPEG":
            # JPEG can decode at 1/2, 1/4 or 1/8 size. Account for EXIF rotation
            # before asking the decoder, then apply an exact thumbnail afterward.
            orientation = source.getexif().get(274, 1)
            decode_bounds = bounds[::-1] if orientation in (5, 6, 7, 8) else bounds
            source.draft("RGB", decode_bounds)
        source.load()
        oriented = ImageOps.exif_transpose(source)
        icc = source.info.get("icc_profile")
        image = oriented.convert("RGB")
        if icc:
            try:
                image = ImageCms.profileToProfile(
                    image,
                    ImageCms.ImageCmsProfile(BytesIO(icc)),
                    ImageCms.createProfile("sRGB"),
                    outputMode="RGB",
                )
            except (ImageCms.PyCMSError, OSError, ValueError):
                # A malformed camera profile must not make an otherwise usable JPEG unreadable.
                pass
        if bounds is not None:
            image.thumbnail(bounds, Image.Resampling.LANCZOS)
        return image.copy()


def _clamp(value: float, limit: float) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("An edit value is not a finite number.")
    return max(-limit, min(limit, value))


def _straighten(image: Image.Image, degrees: float) -> Image.Image:
    """Rotate and crop the largest axis-aligned rectangle inside the rotated source."""
    if abs(degrees) < 0.001:
        return image.copy()
    width, height = image.size
    angle = math.radians(abs(degrees))
    sin_a, cos_a = math.sin(angle), math.cos(angle)
    long_side, short_side = max(width, height), min(width, height)
    if short_side <= 2 * sin_a * cos_a * long_side:
        half_short = short_side / 2
        crop_width, crop_height = half_short / sin_a, half_short / cos_a
        if width < height:
            crop_width, crop_height = crop_height, crop_width
    else:
        cos_2a = cos_a * cos_a - sin_a * sin_a
        crop_width = (width * cos_a - height * sin_a) / cos_2a
        crop_height = (height * cos_a - width * sin_a) / cos_2a
    rotated = image.rotate(degrees, Image.Resampling.BICUBIC, expand=True)
    # A two-pixel inset avoids interpolation sampling the unpopulated rotated edge.
    cw = max(1, min(rotated.width, math.floor(crop_width) - 4))
    ch = max(1, min(rotated.height, math.floor(crop_height) - 4))
    x, y = (rotated.width - cw) // 2, (rotated.height - ch) // 2
    return rotated.crop((x, y, x + cw, y + ch))


def render(
    image: Image.Image, settings: EditSettings, preview: bool = False
) -> Image.Image:
    """Apply edits to a copy. Preview and export share the same processing pipeline."""
    rgb = image.convert("RGB")
    if preview:
        rgb.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    exposure = _clamp(settings.exposure, 2)
    contrast = _clamp(settings.contrast, 100) / 100
    highlights = _clamp(settings.highlights, 100) / 100
    shadows = _clamp(settings.shadows, 100) / 100
    saturation = _clamp(settings.saturation, 100) / 100
    warmth = _clamp(settings.warmth, 100) / 100
    if any((exposure, contrast, highlights, shadows, saturation, warmth)):
        # Calculate exposure once per 8-bit input value, retaining float precision
        # for following adjustments. Process strips to avoid several full-frame
        # float arrays (hundreds of MB each for a GR IV original).
        exposure_lut = np.arange(256, dtype=np.float32) / 255
        exposure_lut = np.where(
            exposure_lut <= 0.04045,
            exposure_lut / 12.92,
            ((exposure_lut + 0.055) / 1.055) ** 2.4,
        )
        exposure_lut *= 2**exposure
        np.clip(exposure_lut, 0, 1, out=exposure_lut)
        exposure_lut = np.where(
            exposure_lut <= 0.0031308,
            exposure_lut * 12.92,
            1.055 * exposure_lut ** (1 / 2.4) - 0.055,
        )
        for top in range(0, rgb.height, 256):
            box = (0, top, rgb.width, min(top + 256, rgb.height))
            data = exposure_lut[np.asarray(rgb.crop(box))]
            if highlights or shadows:
                luminance = (
                    data[..., 0] * 0.2126
                    + data[..., 1] * 0.7152
                    + data[..., 2] * 0.0722
                )
                adjustment = (
                    highlights * 0.3 * luminance**3
                    + shadows * 0.3 * (1 - luminance) ** 3
                )
                data += adjustment[..., None]
            if contrast:
                data -= 0.5
                data *= 1 + contrast * 0.8
                data += 0.5
            if saturation:
                gray = (
                    data[..., 0] * 0.2126
                    + data[..., 1] * 0.7152
                    + data[..., 2] * 0.0722
                )
                data -= gray[..., None]
                data *= 1 + saturation
                data += gray[..., None]
            if warmth:
                data[..., 0] += warmth * 0.08
                data[..., 2] -= warmth * 0.08
            np.clip(data, 0, 1, out=data)
            data *= 255
            np.rint(data, out=data)
            rgb.paste(Image.fromarray(data.astype(np.uint8)), box[:2])
    rgb = transform_geometry(rgb, settings)
    rgb = _straighten(rgb, _clamp(settings.angle, 15))
    rgb = apply_tuning(rgb, settings)
    return _frame(rgb, settings)


def auto_adjust(image: Image.Image) -> dict[str, float]:
    """Conservative, repeatable tone/color suggestions from a bounded original.

    Percentiles avoid letting isolated black or white pixels drive exposure.
    White balance only uses abundant near-neutral midtones, never gray-world
    assumptions about an entire colorful scene. No geometry or frame edits.
    """
    sample = image.convert("RGB")
    sample.thumbnail((512, 512), Image.Resampling.LANCZOS)
    rgb = np.asarray(sample, dtype=np.float32) / 255
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    low, middle, high = np.percentile(lum, [5, 50, 98])
    result = dict(
        exposure=0.0,
        contrast=0.0,
        highlights=0.0,
        shadows=0.0,
        saturation=0.0,
        warmth=0.0,
    )
    if high - low < 0.03:
        return result

    def linear(value):
        return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

    exposure = np.clip(math.log2(linear(0.46) / max(linear(middle), 0.005)), -0.65, 0.9)
    if exposure > 0:
        # Reserve highlight headroom; already-bright images get shadow recovery.
        headroom = max(0, math.log2(linear(0.96) / max(linear(high), 0.005)))
        exposure = min(exposure, headroom)
    result["exposure"] = round(float(exposure), 1)
    adjusted = (
        np.asarray(
            render(sample, EditSettings(exposure=result["exposure"])), dtype=np.float32
        )
        / 255
    )
    tones = adjusted @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    p10, p50, p95 = np.percentile(tones, [10, 50, 95])
    result["shadows"] = (
        float(round(np.clip((0.20 - p10) * 130, 0, 26))) if p50 < 0.65 else 0.0
    )
    result["highlights"] = float(round(-np.clip((p95 - 0.86) * 200, 0, 28)))
    span = p95 - p10
    result["contrast"] = float(round(np.clip((0.72 - span) * 32, -6, 12)))
    maximum, minimum = rgb.max(axis=2), rgb.min(axis=2)
    saturation = (maximum - minimum) / np.maximum(maximum, 0.001)
    midtones = (lum > 0.15) & (lum < 0.85)
    if np.any(midtones):
        color = float(np.median(saturation[midtones]))
        if 0.04 < color < 0.35:
            result["saturation"] = float(round(min(8, (0.35 - color) * 25)))
    neutral = midtones & ((maximum - minimum) < 0.12)
    if np.count_nonzero(neutral) > lum.size * 0.10:
        cast = float(np.median((rgb[..., 0] - rgb[..., 2])[neutral]))
        result["warmth"] = float(round(np.clip(-cast / 0.0016, -12, 12)))
    return result


def auto_straighten(image: Image.Image) -> tuple[float, str]:
    """Suggest a roll correction from long, coherent near-horizontal edges.

    A bounded NumPy Hough vote avoids a video/vision runtime dependency. Positive
    returned degrees are Pillow counter-clockwise corrections. This detects
    geometry, not the semantic horizon, and abstains without strong evidence.
    """
    from PIL import ImageFilter

    sample = image.convert("L")
    sample.thumbnail((720, 720), Image.Resampling.LANCZOS)
    width, height = sample.size
    if min(sample.size) < 64:
        return (
            0.0,
            "Image is too small to estimate a horizon. Adjust the angle manually.",
        )
    gray = np.asarray(sample.filter(ImageFilter.GaussianBlur(0.8)), dtype=np.float32)
    gx = (gray[1:-1, 2:] - gray[1:-1, :-2]) * 0.5
    gy = (gray[2:, 1:-1] - gray[:-2, 1:-1]) * 0.5
    strength = np.abs(gy)
    threshold = max(5.0, float(np.percentile(strength, 85)))
    # Thin vertical gradient maxima; near-horizontal contours have vertical normals.
    mask = (strength >= threshold) & (np.abs(gx) <= strength * 0.6)
    mask[1:-1] &= (strength[1:-1] >= strength[:-2]) & (strength[1:-1] >= strength[2:])
    # Discard artificial edges where rotation or scanning created an image border.
    margin_x, margin_y = max(3, width // 25), max(3, height // 25)
    mask[:margin_y] = False
    mask[-margin_y:] = False
    mask[:, :margin_x] = False
    mask[:, -margin_x:] = False
    ys, xs = np.nonzero(mask)
    if len(xs) < width * 0.30:
        return 0.0, "No clear horizon found. Adjust the angle manually."
    weights = strength[ys, xs]
    if len(xs) > 35000:
        strongest = np.argpartition(weights, -35000)[-35000:]
        xs, ys, weights = xs[strongest], ys[strongest], weights[strongest]
    # Clip extreme contrast so a short black object cannot overwhelm a horizon.
    weights = np.minimum(weights, 40.0)
    xs = xs.astype(np.float32)
    ys = ys.astype(np.float32)
    offset = width // 3 + 4
    bins = height + offset * 2
    angles = np.arange(-15.0, 15.001, 0.25)
    scores = np.zeros(len(angles), dtype=np.float64)
    # A valid line needs contiguous horizontal coverage, not just many noisy pixels.
    for index, angle in enumerate(angles):
        projected = (
            np.rint(ys - xs * math.tan(math.radians(float(angle)))).astype(np.int32)
            + offset
        )
        counts = np.bincount(projected, minlength=bins)
        votes = np.bincount(projected, weights=weights, minlength=bins)
        votes = np.convolve(votes, [1, 1, 1], mode="same")
        counts = np.convolve(counts, [1, 1, 1], mode="same")
        usable = votes.copy()
        for _ in range(3):
            center = int(np.argmax(usable))
            if counts[center] < width * 0.35:
                break
            near = np.abs(projected - center) <= 1
            columns = np.unique(xs[near].astype(np.int32))
            if len(columns) >= width * 0.38 and np.ptp(columns) >= width * 0.58:
                coverage = np.bincount(
                    np.minimum((columns * 10 // width), 9), minlength=10
                )
                if np.count_nonzero(coverage >= width * 0.025) >= 6:
                    # Sharp peaks win over diffuse noise or curved/short contours.
                    scores[index] += votes[center]
            usable[max(0, center - 5) : center + 6] = 0
    best = int(np.argmax(scores))
    peak = scores[best]
    if peak <= 0:
        return 0.0, "No clear horizontal reference found. Adjust the angle manually."
    distant = np.abs(angles - angles[best]) > 2.0
    if np.any(scores[distant] > peak * 0.75):
        return 0.0, "Horizontal edges disagree. Adjust the angle manually."
    # Average only the sharp summit; broad neighbouring angles are not extra evidence.
    summit = (np.abs(angles - angles[best]) <= 0.5) & (scores >= peak * 0.85)
    correction = float(np.average(angles[summit], weights=scores[summit]))
    if abs(correction) < 0.15:
        return 0.0, "The strongest horizontal edges already look level."
    correction = round(correction, 2)
    return (
        correction,
        f"Suggested {correction:+.2f}° from horizontal edges. Check the preview.",
    )


def _export_exif(source: Path, size: tuple[int, int]) -> bytes:
    """Keep capture metadata but omit source thumbnails, maker offsets and GPS."""
    result = Image.Exif()
    with Image.open(source) as original:
        exif = original.getexif()
        for tag in (271, 272, 305, 306, 315, 33432):
            if tag in exif:
                result[tag] = exif[tag]
        try:
            capture = exif.get_ifd(34665)
        except (KeyError, ValueError, OSError):
            capture = {}
        safe_capture = {
            tag: capture[tag]
            for tag in (
                33434,
                33437,
                34850,
                34855,
                36867,
                36868,
                37377,
                37378,
                37380,
                37383,
                37385,
                37386,
                41989,
                42034,
                42035,
                42036,
            )
            if tag in capture
        }
        safe_capture.update({40961: 1, 40962: size[0], 40963: size[1]})
        result[34665] = safe_capture
    result[274] = 1
    result[256], result[257] = size
    return result.tobytes()


def export_image(
    source_path: str | Path,
    settings: EditSettings,
    folder: str | Path,
    quality: int = 95,
) -> Path:
    """Export full-resolution sRGB JPEG to a new filename, never over originals."""
    source = Path(source_path)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    image = render(load_image(source), settings)
    stem = re.sub(r"[^\w .-]", "_", source.stem)[:100] or "photo"
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    exif = _export_exif(source, image.size)
    index = 1
    while True:
        suffix = "" if index == 1 else f"-{index}"
        output = folder / f"{stem}-edited{suffix}.jpg"
        try:
            handle = output.open("xb")
            break
        except FileExistsError:
            index += 1
    try:
        with handle:
            image.save(
                handle,
                "JPEG",
                quality=max(1, min(100, int(quality))),
                subsampling=0,
                icc_profile=profile,
                exif=exif,
            )
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise
    return output
