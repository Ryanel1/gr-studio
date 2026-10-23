"""Accuracy and conservative failure cases for the lightweight roll estimator."""

import time
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter
from gr_studio.imaging import auto_straighten, render, EditSettings


def horizon(size=(1400, 950)):
    image = Image.new("RGB", size, "#b9c9d0")
    draw = ImageDraw.Draw(image)
    width, height = size
    draw.rectangle((0, height // 2, width, height), fill="#738b65")
    for fraction in (0.20, 0.75):
        y = round(height * fraction)
        draw.line((width // 10, y, width * 9 // 10, y), width=4, fill="#364045")
    return image


@pytest.mark.parametrize("tilt", [-14, -10, -6, -2.5, 2.5, 6, 10, 14])
def test_known_roll_correction_and_residual(tilt):
    tilted = horizon().rotate(-tilt, Image.Resampling.BICUBIC)
    correction, reason = auto_straighten(tilted)
    assert abs(correction - tilt) < 0.4, reason
    residual, reason = auto_straighten(render(tilted, EditSettings(angle=correction)))
    assert abs(residual) < 0.4, reason


@pytest.mark.parametrize("seed", range(6))
@pytest.mark.parametrize("blur", [0, 1.5, 4])
def test_random_texture_abstains(seed, blur):
    rng = np.random.default_rng(seed)
    texture = Image.fromarray(rng.integers(0, 256, (950, 1400), dtype=np.uint8))
    if blur:
        texture = texture.filter(ImageFilter.GaussianBlur(blur))
    angle, reason = auto_straighten(texture)
    assert angle == 0 and "manually" in reason


def test_conflicting_long_lines_abstain():
    image = Image.new("RGB", (1000, 700), "#d0d0d0")
    draw = ImageDraw.Draw(image)
    draw.line((50, 180, 950, 275), fill="#202020", width=5)
    draw.line((50, 520, 950, 425), fill="#202020", width=5)
    angle, reason = auto_straighten(image)
    assert angle == 0 and "disagree" in reason


def test_short_edges_do_not_establish_horizon():
    image = Image.new("RGB", (1000, 700), "#d0d0d0")
    draw = ImageDraw.Draw(image)
    draw.line((400, 330, 560, 345), fill="#202020", width=5)
    angle, reason = auto_straighten(image)
    assert angle == 0 and "manually" in reason


def test_preview_analysis_finishes_under_one_second():
    image = horizon().rotate(-6, Image.Resampling.BICUBIC)
    start = time.perf_counter()
    angle, _ = auto_straighten(image)
    assert abs(angle - 6) < 0.4
    assert time.perf_counter() - start < 1.0
