import numpy as np
import pytest
from PIL import Image
from gr_studio.imaging import auto_adjust, render, EditSettings


def ramp(low, high):
    row = np.linspace(low, high, 256).astype(np.uint8)
    return Image.fromarray(np.repeat(np.tile(row, (100, 1))[..., None], 3, axis=2))


def test_auto_lifts_dark_photo_and_leaves_original_intact():
    image = ramp(10, 135)
    original = image.tobytes()
    values = auto_adjust(image)
    assert values["exposure"] > 0
    assert (
        np.asarray(render(image, EditSettings(**values))).mean()
        > np.asarray(image).mean()
    )
    assert image.tobytes() == original
    assert values == auto_adjust(image)
    assert values["warmth"] == values["saturation"] == 0


def test_auto_reduces_overbright_exposure():
    image = ramp(150, 255)
    values = auto_adjust(image)
    assert values["exposure"] < 0
    assert (
        np.asarray(render(image, EditSettings(**values))).mean()
        < np.asarray(image).mean()
    )


@pytest.mark.parametrize("color", ["black", "white", "#808080"])
def test_auto_does_not_force_featureless_images_to_gray(color):
    assert all(
        value == 0 for value in auto_adjust(Image.new("RGB", (30, 30), color)).values()
    )


def test_auto_does_not_neutralize_colorful_scene():
    pixels = np.asarray(ramp(10, 200)).copy()
    pixels[..., 1:] //= 4
    values = auto_adjust(Image.fromarray(pixels))
    assert values["warmth"] == 0
    assert values["saturation"] == 0
