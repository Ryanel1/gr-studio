import numpy as np
import pytest
from PIL import Image, ImageDraw

from gr_studio.imaging import (
    EditSettings,
    auto_straighten,
    export_image,
    load_image,
    render,
)


def test_defaults_preserve_pixels():
    rng = np.random.default_rng(4)
    original = Image.fromarray(rng.integers(0, 255, (120, 180, 3), dtype=np.uint8))
    before = original.tobytes()
    assert render(original, EditSettings()).tobytes() == before
    render(original, EditSettings(exposure=1, warmth=20, contrast=15))
    assert original.tobytes() == before


@pytest.mark.parametrize("size", [(900, 600), (600, 900), (1000, 120), (120, 1000)])
@pytest.mark.parametrize("angle", [-15, -5, 5, 15])
def test_rotated_crop_has_no_empty_corners(size, angle):
    im = Image.new("RGB", size, (220, 220, 220))
    out = render(im, EditSettings(angle=angle))
    assert np.asarray(out).min() >= 215
    assert out.width < size[0] and out.height < size[1]


def test_auto_straighten_direction_and_recovery():
    im = Image.new("RGB", (1000, 700), "#d6d2c8")
    draw = ImageDraw.Draw(im)
    for y in [170, 350, 530]:
        draw.line((30, y, 970, y), fill="#333333", width=5)
    tilted = im.rotate(-6, resample=Image.Resampling.BICUBIC)
    correction, reason = auto_straighten(tilted)
    assert 5 < correction < 7, reason
    fixed = render(tilted, EditSettings(angle=correction))
    residual, _ = auto_straighten(fixed)
    assert abs(residual) < 0.5


def test_auto_straighten_abstains_on_blank():
    correction, reason = auto_straighten(Image.new("RGB", (900, 600), "white"))
    assert correction == 0
    assert "manually" in reason


def test_frame_dimensions_and_original_aspect():
    image = Image.new("RGB", (900, 600), "red")
    classic = render(image, EditSettings(border="classic", caption="Chicago"))
    assert classic.size == (966, 753)
    assert classic.getpixel((33, 33)) == (255, 0, 0)
    square = render(image, EditSettings(border="square"))
    assert square.size == (666, 753)
    assert classic.getpixel((0, 0)) == (244, 240, 231)


def test_export_unique_full_resolution_and_orientation(tmp_path):
    source = tmp_path / "source.jpg"
    exif = Image.Exif()
    exif[274] = 6
    exif[271] = "RICOH"
    exif[34665] = {36867: "2026:10:23 12:00:00", 40962: 900, 40963: 600}
    Image.new("RGB", (900, 600), "#812b33").save(source, exif=exif)
    original = source.read_bytes()
    first = export_image(source, EditSettings(), tmp_path)
    second = export_image(source, EditSettings(), tmp_path)
    assert first != second
    assert source.read_bytes() == original
    with Image.open(first) as image:
        image.load()
        assert image.size == (600, 900)
        assert image.info["icc_profile"]
        assert image.getexif()[274] == 1
        assert image.getexif()[271] == "RICOH"
        assert image.getexif().get_ifd(34665)[40962] == 600
        assert image.getexif().get_ifd(34665)[36867] == "2026:10:23 12:00:00"


def test_preview_bounded_and_raw_rejected(tmp_path):
    assert (
        max(render(Image.new("RGB", (3000, 2000)), EditSettings(), preview=True).size)
        == 1600
    )
    with pytest.raises(ValueError, match="RAW"):
        load_image(tmp_path / "image.DNG")


def test_exposure_and_saturation_are_meaningful():
    image = Image.new("RGB", (100, 100), (100, 60, 30))
    brighter = render(image, EditSettings(exposure=1))
    assert all(a > b for a, b in zip(brighter.getpixel((0, 0)), image.getpixel((0, 0))))
    gray = render(image, EditSettings(saturation=-100)).getpixel((0, 0))
    assert gray[0] == gray[1] == gray[2]


@pytest.mark.parametrize("orientation", [1, 5, 6, 7, 8])
@pytest.mark.parametrize("bounds", [200, (120, 200), (200, 120)])
def test_jpeg_draft_preserves_orientation_and_target_size(
    tmp_path, orientation, bounds, monkeypatch
):
    from PIL import JpegImagePlugin

    source = tmp_path / "oriented.jpg"
    fixture = Image.new("RGB", (1600, 1200), "white")
    draw = ImageDraw.Draw(fixture)
    draw.rectangle((0, 0, 799, 599), fill="red")
    draw.rectangle((800, 0, 1599, 599), fill="green")
    draw.rectangle((0, 600, 799, 1199), fill="blue")
    exif = Image.Exif()
    exif[274] = orientation
    fixture.save(source, quality=98, exif=exif)
    reference = load_image(source)
    reference.thumbnail(
        (bounds, bounds) if isinstance(bounds, int) else bounds,
        Image.Resampling.LANCZOS,
    )
    calls = []
    original_draft = JpegImagePlugin.JpegImageFile.draft

    def record_draft(self, *args, **kwargs):
        before = self.size
        result = original_draft(self, *args, **kwargs)
        calls.append((before, self.size))
        return result

    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", record_draft)
    preview = load_image(source, max_size=bounds)
    assert calls and calls[0][1][0] < calls[0][0][0]
    assert preview.size == reference.size
    for x, y in [
        (preview.width // 4, preview.height // 4),
        (preview.width * 3 // 4, preview.height // 4),
        (preview.width // 4, preview.height * 3 // 4),
    ]:
        assert (
            np.max(
                np.abs(
                    np.array(preview.getpixel((x, y)), dtype=int)
                    - np.array(reference.getpixel((x, y)), dtype=int)
                )
            )
            <= 3
        )


def test_strip_processing_matches_full_array_reference():
    rng = np.random.default_rng(11)
    pixels = rng.integers(0, 256, (530, 320, 3), dtype=np.uint8)
    settings = EditSettings(
        exposure=0.6, highlights=-25, shadows=30, contrast=17, saturation=14, warmth=-8
    )
    data = pixels.astype(np.float32) / 255
    data = np.where(data <= 0.04045, data / 12.92, ((data + 0.055) / 1.055) ** 2.4)
    data *= 2**settings.exposure
    np.clip(data, 0, 1, out=data)
    data = np.where(data <= 0.0031308, data * 12.92, 1.055 * data ** (1 / 2.4) - 0.055)
    luminance = data[..., 0] * 0.2126 + data[..., 1] * 0.7152 + data[..., 2] * 0.0722
    data += (-0.25 * 0.3 * luminance**3 + 0.30 * 0.3 * (1 - luminance) ** 3)[..., None]
    data -= 0.5
    data *= 1 + 0.17 * 0.8
    data += 0.5
    gray = data[..., 0] * 0.2126 + data[..., 1] * 0.7152 + data[..., 2] * 0.0722
    data = gray[..., None] + (data - gray[..., None]) * 1.14
    data[..., 0] += -0.08 * 0.08
    data[..., 2] -= -0.08 * 0.08
    expected = np.rint(np.clip(data, 0, 1) * 255).astype(np.uint8)
    actual = np.asarray(render(Image.fromarray(pixels), settings))
    assert np.array_equal(actual, expected)
