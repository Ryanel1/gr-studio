"""Bounded-memory finishing adjustments shared by previews and full-size exports.

Float work is restricted to strips. Spatial filters use Pillow byte images;
filter radii scale with the long side (reference 1600px), with bounded maxima.
These are intentionally lightweight photographic approximations, not RAW recovery.
"""
from __future__ import annotations

import math
import numpy as np
from PIL import Image, ImageFilter

STRIP_HEIGHT = 128
CURVES = ("Linear", "Soft contrast", "Faded shadows", "Strong contrast")
CURVE_PRESETS = CURVES
BANDS = {"red": 0, "orange": 30, "yellow": 60, "green": 120,
         "aqua": 180, "blue": 240, "purple": 270, "magenta": 300}
SIGNED = ("whites", "blacks", "tint", "vibrance", "texture", "clarity", "dehaze", "vignette")
UNSIGNED = ("grain", "sharpening", "noise_reduction")


def _amount(value, unsigned=False):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("An edit value is not a finite number.")
    return max(0 if unsigned else -100, min(100, value)) / 100


def _boxes(image):
    for top in range(0, image.height, STRIP_HEIGHT):
        yield (0, top, image.width, min(top + STRIP_HEIGHT, image.height))


def _pixels(image, box):
    return np.asarray(image.crop(box), dtype=np.float32) / 255


def _paste(image, box, data):
    image.paste(Image.fromarray(np.rint(np.clip(data, 0, 1) * 255).astype(np.uint8)), box[:2])


def _luma(data):
    return data[..., 0] * .2126 + data[..., 1] * .7152 + data[..., 2] * .0722


def _hsv(data):
    maximum, minimum = data.max(axis=2), data.min(axis=2)
    delta = maximum - minimum
    safe = np.maximum(delta, 1e-6)
    hue = np.where(maximum == data[..., 0], (data[..., 1] - data[..., 2]) / safe,
                   np.where(maximum == data[..., 1], 2 + (data[..., 2] - data[..., 0]) / safe,
                            4 + (data[..., 0] - data[..., 1]) / safe))
    return (hue / 6) % 1, delta / np.maximum(maximum, 1e-6), maximum


def _rgb(h, s, v):
    # Continuous triangular channels avoid allocating six candidate RGB images.
    channels = np.stack([np.abs((h * 6 + offset) % 6 - 3) - 1 for offset in (0, 4, 2)], axis=2)
    return v[..., None] * (1 + (np.clip(channels, 0, 1) - 1) * s[..., None])


def _mix(data, mixer):
    hue, saturation, value = _hsv(data)
    dh, ds, dl = (np.zeros_like(hue) for _ in range(3))
    for name, settings in mixer.items():
        distance = np.abs((hue * 360 - BANDS[name] + 180) % 360 - 180)
        # Raised cosine windows wrap around red and have no discontinuous edges.
        weight = .5 + .5 * np.cos(np.minimum(distance / 60, 1) * np.pi)
        weight *= np.minimum(saturation * 4, 1)
        dh += weight * settings[0] / 12  # maximum shift is 30 degrees per band
        ds += weight * settings[1]
        dl += weight * settings[2]
    result = _rgb((hue + np.clip(dh, -1/12, 1/12)) % 1,
                  np.clip(saturation * (1 + ds), 0, 1), value)
    # A bounded blend toward white/black retains hue and never colors neutrals.
    dl = np.clip(dl, -1, 1)[..., None] * .45
    return result + np.where(dl >= 0, (1 - result) * dl, result * dl)


def curve_values(x, preset):
    """Evaluate a normalized curve, shared with the interactive curve graph."""
    if preset not in CURVES:
        raise ValueError(f"Unknown tone curve: {preset}")
    x = np.asarray(x)
    if preset == "Linear":
        return x.copy()
    if preset == "Faded shadows":
        return .065 + .935 * x - .035 * np.sin(np.pi * x)
    strength = .18 if preset == "Soft contrast" else .40
    return x + strength * (x - .5) * (1 - (2 * x - 1) ** 2)


def _tone_pass(image, values, curve, mixer):
    for box in _boxes(image):
        data = _pixels(image, box)
        lum = _luma(data)
        data += (.24 * (values['whites'] * lum ** 5 + values['blacks'] * (1-lum) ** 5))[..., None]
        if values['tint']:
            data += np.array([.04, -.08, .04], dtype=np.float32) * values['tint']
        data = np.clip(data, 0, 1)
        if curve != 'Linear':
            data = curve_values(data, curve)
        if values['dehaze']:
            # Invert a modest neutral airlight veil; negative amount adds haze.
            amount = values['dehaze']
            if amount > 0:
                transmission = 1 - .30 * amount
                data = (data - .85 * (1 - transmission)) / transmission
            else:
                data = data * (1 + .25 * amount) - .85 * .25 * amount
            data = np.clip(data, 0, 1)
        if values['vibrance']:
            maximum, minimum = data.max(axis=2), data.min(axis=2)
            sat = (maximum-minimum) / np.maximum(maximum, 1e-6)
            gray = _luma(data)[..., None]
            data = gray + (data-gray) * (1 + values['vibrance'] * (1-sat))[..., None]
        if mixer:
            data = _mix(np.clip(data, 0, 1), mixer)
        _paste(image, box, data)


def _denoise(image, amount):
    """Small bilateral neighborhood: range weights reject samples across edges."""
    source = image.copy()
    sigma = .035 + .10 * amount
    for box in _boxes(image):
        top, bottom = box[1], box[3]
        halo = (0, max(0, top-1), image.width, min(image.height, bottom+1))
        patch = _pixels(source, halo)
        patch = np.pad(patch, ((int(top == 0), int(bottom == image.height)), (1, 1), (0, 0)), mode='edge')
        center = patch[1:-1, 1:-1]
        total, weights = center.copy(), np.ones(center.shape[:2], dtype=np.float32)
        for dy in range(3):
            for dx in range(3):
                if dx == dy == 1:
                    continue
                neighbor = patch[dy:dy+center.shape[0], dx:dx+center.shape[1]]
                weight = np.exp(-np.mean((neighbor-center)**2, axis=2) / (2*sigma*sigma))
                weight *= .75 if dx == 1 or dy == 1 else .5
                total += neighbor * weight[..., None]
                weights += weight
        _paste(image, box, center * (1-amount) + total / weights[..., None] * amount)


def _detail(image, amount, radius, strength, protect=False):
    blurred = image.filter(ImageFilter.GaussianBlur(radius))
    for box in _boxes(image):
        data = _pixels(image, box)
        detail = _luma(data) - _luma(_pixels(blurred, box))
        if protect:
            detail *= 1 - np.exp(-(detail / .012) ** 2)
        data += (detail * amount * strength)[..., None]
        _paste(image, box, data)


def _finish(image, grain, vignette):
    x = (np.arange(image.width, dtype=np.float32) + .5) / image.width * 2 - 1
    for box in _boxes(image):
        data = _pixels(image, box)
        if vignette:
            y = (np.arange(box[1], box[3], dtype=np.float32) + .5) / image.height * 2 - 1
            falloff = np.clip((x[None, :]**2 + y[:, None]**2) / 2, 0, 1) ** 1.25
            # Positive values lighten corners; negative values darken them.
            amount = vignette * .65 * falloff[..., None]
            data += np.where(amount > 0, (1-data)*amount, data*amount)
        if grain:
            # Stateless coordinate hashing makes grain deterministic across strip sizes.
            xx = np.arange(image.width, dtype=np.uint32)[None, :]
            yy = np.arange(box[1], box[3], dtype=np.uint32)[:, None]
            seed = xx * np.uint32(374761393) + yy * np.uint32(668265263) + np.uint32(1447)
            seed = (seed ^ (seed >> 13)) * np.uint32(1274126177)
            seed ^= seed >> 16
            noise = (seed.astype(np.float32) / 4294967295 - .5) * .18 * grain
            data += noise[..., None] * (.35 + .65 * (1-np.abs(2*_luma(data)-1)))[..., None]
        _paste(image, box, data)


def apply_tuning(image, settings):
    """Apply finishing controls in place to render's independent RGB copy."""
    values = {name: _amount(getattr(settings, name), name in UNSIGNED) for name in SIGNED + UNSIGNED}
    curve = settings.curve
    if curve not in CURVES:
        raise ValueError(f"Unknown tone curve: {curve}")
    mixer = {}
    for name, band in settings.mixer.items():
        if name not in BANDS:
            raise ValueError(f"Unknown mixer color: {name}")
        amounts = tuple(_amount(band.get(key, 0)) for key in ('hue', 'saturation', 'luminance'))
        if any(amounts):
            mixer[name] = amounts
    if not any(values.values()) and curve == 'Linear' and not mixer:
        return image
    if any(values[n] for n in ('whites', 'blacks', 'tint', 'vibrance', 'dehaze')) or curve != 'Linear' or mixer:
        _tone_pass(image, values, curve, mixer)
    if values['noise_reduction']:
        _denoise(image, values['noise_reduction'])
    scale = max(image.size) / 1600
    for name, radius, strength in (('texture', max(.6, min(4, scale * 1.2)), 1.2),
                                   ('clarity', max(2, min(48, scale * 16)), 1.0),
                                   ('sharpening', max(.5, min(3, scale * .8)), 1.8)):
        if values[name]:
            _detail(image, values[name], radius, strength, protect=name == 'sharpening')
    if values['grain'] or values['vignette']:
        _finish(image, values['grain'], values['vignette'])
    return image
