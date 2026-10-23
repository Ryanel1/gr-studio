"""Photographic invariants for the shared tuning pipeline."""
import numpy as np
import pytest
from PIL import Image, ImageFilter

from gr_studio.imaging import EditSettings, render
from gr_studio import tuning


def pixels(image, **settings):
    return np.asarray(render(image, EditSettings(**settings))).astype(float)


@pytest.fixture
def ramp():
    return Image.fromarray(np.tile(np.arange(256, dtype=np.uint8)[None, :, None], (48, 1, 3)))


def test_identity_independent_mixer_and_nonmutation(ramp):
    settings = EditSettings()
    settings.mixer['red'] = {'hue': 10}
    assert EditSettings().mixer == {}
    before = ramp.tobytes()
    assert render(ramp, EditSettings()).tobytes() == before
    render(ramp, EditSettings(texture=50, grain=80, whites=30))
    assert ramp.tobytes() == before


@pytest.mark.parametrize('control,region', [('whites', slice(200, 240)), ('blacks', slice(15, 55))])
def test_tone_extremes_direction_and_selectivity(ramp, control, region):
    baseline = np.asarray(ramp).astype(float)
    plus = pixels(ramp, **{control: 70}) - baseline
    minus = pixels(ramp, **{control: -70}) - baseline
    assert plus[:, region].mean() > 5
    assert minus[:, region].mean() < -5
    opposite = slice(15, 55) if control == 'whites' else slice(200, 240)
    assert plus[:, region].mean() > plus[:, opposite].mean() * 5


def test_tint_and_vibrance():
    neutral = Image.new('RGB', (30, 30), (128, 128, 128))
    assert pixels(neutral, tint=70)[0, 0, 0] > pixels(neutral, tint=70)[0, 0, 1]
    assert pixels(neutral, tint=-70)[0, 0, 0] < pixels(neutral, tint=-70)[0, 0, 1]
    assert np.array_equal(pixels(neutral, vibrance=90), np.asarray(neutral))
    muted = Image.new('RGB', (30, 30), (150, 100, 100))
    assert np.ptp(pixels(muted, vibrance=90)[0, 0]) > 50
    assert np.ptp(pixels(muted, vibrance=-90)[0, 0]) < 50


@pytest.mark.parametrize('curve', tuning.CURVES)
def test_curve_matches_graph_monotonic(ramp, curve):
    values = tuning.curve_values(np.linspace(0, 1, 256), curve)
    assert np.all(np.diff(values) > 0)
    assert np.allclose(pixels(ramp, curve=curve)[0, :, 0], np.rint(values*255))
    if curve != 'Linear':
        assert not np.array_equal(pixels(ramp, curve=curve), np.asarray(ramp))


def test_mixer_selective_hue_saturation_luminance_and_wrap():
    colors = np.array([[[200, 40, 45], [200, 45, 40], [30, 40, 200], [100, 100, 100]]], dtype=np.uint8)
    image = Image.fromarray(colors)
    for control in ('hue', 'saturation', 'luminance'):
        result = pixels(image, mixer={'red': {control: 80}})
        assert np.array_equal(result[0, 2:], colors[0, 2:])
        assert not np.array_equal(result[0, :2], colors[0, :2])
        if control == 'saturation':
            assert np.ptp(result[0, 0]) > np.ptp(colors[0, 0])
        if control == 'luminance':
            assert result[0, 0].mean() > colors[0, 0].mean()
        if control == 'hue':
            assert result[0, 0, 1] > colors[0, 0, 1]
    separate = pixels(image, mixer={'red': {'hue': 40}, 'blue': {'luminance': -50}})
    assert separate[0, 2].mean() < colors[0, 2].mean()
    assert np.array_equal(separate[0, 0], pixels(image, mixer={'red': {'hue': 40}})[0, 0])


def test_noise_reduction_reduces_variance_preserves_edge():
    rng = np.random.default_rng(17)
    data = np.full((100, 180, 3), 65., dtype=float)
    data[:, 90:] = 190
    data += rng.normal(0, 12, data.shape)
    image = Image.fromarray(np.clip(data, 0, 255).astype(np.uint8))
    reduced = pixels(image, noise_reduction=100)
    assert reduced[:, 10:80].std() < data[:, 10:80].std() * .65
    assert reduced[:, 90].mean() - reduced[:, 89].mean() > 100


def test_detail_controls_edge_contrast_and_different_scales():
    data = np.full((120, 200, 3), 75, dtype=np.uint8)
    data[:, 100:] = 180
    image = Image.fromarray(data).filter(ImageFilter.GaussianBlur(1.2))
    base = np.asarray(image).astype(float)
    sharp = pixels(image, sharpening=100)
    assert sharp[:, 101].mean()-sharp[:, 98].mean() > base[:, 101].mean()-base[:, 98].mean()
    texture = pixels(image, texture=80)
    clarity = pixels(image, clarity=80)
    assert not np.array_equal(texture, clarity)
    assert np.abs(clarity[:, 94]-base[:, 94]).mean() > np.abs(texture[:, 94]-base[:, 94]).mean()
    assert pixels(image, texture=-80)[:, 101].mean()-pixels(image, texture=-80)[:, 98].mean() < base[:, 101].mean()-base[:, 98].mean()


def test_dehaze_changes_neutral_contrast(ramp):
    positive = pixels(ramp, dehaze=80)
    negative = pixels(ramp, dehaze=-80)
    assert positive[:, 190].mean()-positive[:, 80].mean() > 110
    assert negative[:, 190].mean()-negative[:, 80].mean() < 110
    assert np.array_equal(positive[..., 0], positive[..., 1])


def test_grain_vignette_and_frame():
    image = Image.new('RGB', (220, 180), (128, 128, 128))
    grain = pixels(image, grain=80)
    assert grain.std() > 5
    assert np.array_equal(grain, pixels(image, grain=80))
    for amount in (-80, 80):
        result = pixels(image, vignette=amount)
        assert np.sign(result[0, 0].mean()-result[90, 110].mean()) == np.sign(amount)
    framed = render(image, EditSettings(border='classic', grain=100, tint=80, vignette=-100))
    assert framed.getpixel((0, 0)) == (244, 240, 231)


def test_combined_strip_seams_preview_agreement_and_dimensions(monkeypatch):
    rng = np.random.default_rng(4)
    image = Image.fromarray(rng.integers(20, 235, (273, 157, 3), dtype=np.uint8))
    settings = EditSettings(whites=12, blacks=-10, tint=15, vibrance=40, texture=25,
                            clarity=20, dehaze=10, grain=30, vignette=-25, sharpening=30,
                            noise_reduction=60, curve='Soft contrast', mixer={'blue': {'hue': 20}})
    expected = render(image, settings)
    assert expected.size == image.size
    assert expected.tobytes() == render(image, settings, preview=True).tobytes()
    monkeypatch.setattr(tuning, 'STRIP_HEIGHT', 37)
    assert render(image, settings).tobytes() == expected.tobytes()


@pytest.mark.parametrize('size', [(1, 1), (1, 7), (7, 1)])
def test_tiny_images(size):
    assert render(Image.new('RGB', size, 'gray'), EditSettings(noise_reduction=100, clarity=20)).size == size


def test_validation_and_clamping(ramp):
    with pytest.raises(ValueError, match='finite'):
        render(ramp, EditSettings(tint=float('nan')))
    with pytest.raises(ValueError, match='curve'):
        render(ramp, EditSettings(curve='missing'))
    assert np.array_equal(pixels(ramp, whites=1000), pixels(ramp, whites=100))
    assert np.array_equal(pixels(ramp, noise_reduction=-50), np.asarray(ramp))


@pytest.mark.parametrize('band,degrees', tuning.BANDS.items())
def test_each_mixer_band_changes_its_own_hue(band, degrees):
    import colorsys
    color = tuple(round(channel*255) for channel in colorsys.hsv_to_rgb(degrees/360, .7, .7))
    image = Image.new('RGB', (3, 3), color)
    assert not np.array_equal(pixels(image, mixer={band: {'hue': 70}}), np.asarray(image))


def test_actual_export_uses_finishing_pipeline(tmp_path):
    from gr_studio.imaging import export_image, load_image
    source = tmp_path / 'original.png'
    Image.new('RGB', (120, 90), (145, 110, 80)).save(source)
    settings = EditSettings(tint=15, whites=25, grain=20, vignette=-50,
                            curve='Soft contrast', mixer={'orange': {'saturation': 40}})
    expected = np.asarray(render(load_image(source), settings, preview=True)).astype(float)
    result = np.asarray(load_image(export_image(source, settings, tmp_path, quality=100))).astype(float)
    assert result.shape == expected.shape
    assert np.mean(np.abs(result-expected)) < 1
