from dataclasses import replace
import pytest
from PIL import Image
from gr_studio.imaging import EditSettings, render
from gr_studio.frames import RATIOS
from gr_studio.state import Library


@pytest.mark.parametrize("ratio", RATIOS)
@pytest.mark.parametrize("size", [(600, 400), (400, 600)])
def test_canvas_ratio_preserves_full_photo(ratio, size):
    image = Image.new("RGB", size, "red")
    image.putpixel((0, 0), (0, 255, 0))
    image.putpixel((size[0] - 1, size[1] - 1), (0, 0, 255))
    output = render(
        image, EditSettings(border="canvas", border_ratio=ratio, border_width=8)
    )
    rw, rh = RATIOS[ratio]
    assert output.width * rh == output.height * rw
    x, y = (output.width - size[0]) // 2, (output.height - size[1]) // 2
    assert output.crop((x, y, x + size[0], y + size[1])).tobytes() == image.tobytes()


def test_even_width_custom_color_and_zero_border():
    image = Image.new("RGB", (600, 400), "red")
    settings = EditSettings(border="even", border_width=10, border_color="#123456")
    output = render(image, settings)
    assert output.size == (680, 480)
    assert output.getpixel((0, 0)) == (18, 52, 86)
    assert render(image, replace(settings, border_width=0)).tobytes() == image.tobytes()


def test_backgrounds_and_rounding():
    image = Image.new("RGB", (600, 400), "red")
    rounded = render(
        image,
        EditSettings(
            border="even", border_width=10, border_color="#ffffff", border_radius=20
        ),
    )
    assert rounded.getpixel((40, 40)) == (255, 255, 255)
    assert rounded.getpixel((340, 240)) == (255, 0, 0)
    for background in ("photo", "blur"):
        output = render(
            image, EditSettings(border="canvas", border_background=background)
        )
        assert output.getpixel((0, 0)) == (255, 0, 0)


def test_frame_settings_restore_and_old_sessions_keep_defaults(tmp_path):
    library = Library(tmp_path)
    settings = EditSettings(
        border="canvas",
        border_ratio="4:5",
        border_width=12,
        border_radius=8,
        border_background="blur",
    )
    library.save_edit("photo", settings)
    assert Library(tmp_path).settings("photo") == settings
    library.edits["old"] = {"border": "classic"}
    assert library.settings("old") == EditSettings(border="classic")
