from dataclasses import replace
import numpy as np
import pytest
from PIL import Image, ImageDraw
from gr_studio.geometry import (
    IDENTITY,
    guided_matrix,
    project,
    auto_geometry,
    checked_matrix,
)
from gr_studio.imaging import EditSettings, render
from gr_studio.state import Library


def guides_for(matrix, size=(1000, 800), both=False):
    width, height = size
    short = min(size)
    guides = []
    for kind, points in [
        ("vertical", [(-0.35, -0.35), (-0.35, 0.35)]),
        ("vertical", [(0.35, -0.35), (0.35, 0.35)]),
        ("horizontal", [(-0.35, -0.35), (0.35, -0.35)]),
        ("horizontal", [(-0.35, 0.35), (0.35, 0.35)]),
    ]:
        if kind == "horizontal" and not both:
            continue
        mapped = project(matrix, points) * short / np.array(size) + 0.5
        guides.append((kind, tuple(mapped[0]), tuple(mapped[1])))
    return guides


@pytest.mark.parametrize("both", [False, True])
def test_guides_rectify_converging_lines(both):
    distortion = np.array(
        [[1, 0.045, 0], [-0.025, 1, 0], [0.12 if both else 0, 0.3, 1]]
    )
    size = (1000, 800)
    guides = guides_for(distortion, size, both)
    correction = np.array(guided_matrix(guides, size)).reshape(3, 3)
    for kind, start, end in guides:
        original = (np.array([start, end]) - 0.5) * np.array(size) / min(size)
        fixed = project(correction, original)
        axis = 0 if kind == "vertical" else 1
        assert abs(fixed[0, axis] - fixed[1, axis]) < 1e-8


def test_horizontal_guides_only():
    distortion = np.array([[1, 0, 0], [0.03, 1, 0], [0.25, 0, 1]])
    guides = [g for g in guides_for(distortion, both=True) if g[0] == "horizontal"]
    correction = np.array(guided_matrix(guides, (1000, 800))).reshape(3, 3)
    for _, start, end in guides:
        fixed = project(correction, (np.array([start, end]) - 0.5) * [1.25, 1])
        assert abs(fixed[0, 1] - fixed[1, 1]) < 1e-8


@pytest.mark.parametrize(
    "guides",
    [
        [],
        [("vertical", (0.2, 0.1), (0.2, 0.9))],
        [("vertical", (0.2, 0.1), (0.2, 0.9)), ("vertical", (0.21, 0.1), (0.21, 0.9))],
        [("vertical", (0.2, 0.1), (0.8, 0.1)), ("vertical", (0.2, 0.9), (0.8, 0.9))],
    ],
)
def test_bad_guides_rejected(guides):
    with pytest.raises(ValueError):
        guided_matrix(guides, (1000, 800))


def test_perspective_crop_no_empty_edges_and_preserves_source():
    image = Image.new("RGB", (1000, 800), (230, 230, 230))
    before = image.tobytes()
    output = render(image, EditSettings(vertical=30, horizontal=-12, aspect=8, angle=2))
    assert np.asarray(output).min() > 220
    assert image.tobytes() == before
    assert render(image, EditSettings()).tobytes() == before


def test_aspect_changes_proportions():
    image = Image.new("RGB", (600, 400), "white")
    wide = render(image, EditSettings(aspect=40))
    narrow = render(image, EditSettings(aspect=-40))
    assert wide.width / wide.height > 1.8
    assert narrow.width / narrow.height < 1.2


def building():
    image = Image.new("RGB", (1000, 800), "#dddddd")
    draw = ImageDraw.Draw(image)
    for x in (140, 280, 420, 580, 720, 860):
        draw.line((x, 100, x, 700), fill="#222222", width=5)
    for y in (140, 280, 420, 580, 660):
        draw.line((100, y, 900, y), fill="#222222", width=5)
    return image


@pytest.mark.parametrize("mode", ["vertical", "auto", "full"])
def test_auto_rectifies_synthetic_building(mode):
    skew = render(
        building(), EditSettings(geometry=(1, 0.04, 0, -0.02, 1, 0, 0.08, 0.3, 1))
    )
    correction = auto_geometry(skew, mode)
    fixed = render(skew, EditSettings(geometry=correction))
    residual = checked_matrix(auto_geometry(fixed, "vertical"))
    assert abs(residual[2, 1]) < 0.035
    assert abs(residual[0, 1]) < 0.015


def test_auto_abstains_without_edges():
    with pytest.raises(ValueError, match="Guided"):
        auto_geometry(Image.new("RGB", (600, 400), "gray"), "vertical")


def test_geometry_session_roundtrip_and_invalid_matrix(tmp_path):
    library = Library(tmp_path)
    settings = replace(
        EditSettings(),
        geometry=(1, 0.05, 0, -0.03, 1, 0, 0.1, 0.25, 1),
        geometry_mode="guided",
        aspect=10,
    )
    library.save_edit("photo", settings)
    assert Library(tmp_path).settings("photo") == settings
    library.edits["bad"] = {"geometry": [0] * 9}
    assert library.settings("bad").geometry == IDENTITY


def test_auto_handles_building_in_lower_part_of_photo():
    image = Image.new("RGB", (1000, 800), "#dddddd")
    draw = ImageDraw.Draw(image)
    for x in (140, 280, 420, 580, 720, 860):
        draw.line((x, 360, x, 600), fill="#222222", width=5)
    skew = render(image, EditSettings(geometry=(1, 0.02, 0, 0, 1, 0, 0, 0.22, 1)))
    fixed = render(skew, EditSettings(geometry=auto_geometry(skew, "vertical")))
    residual = checked_matrix(auto_geometry(fixed, "vertical"))
    assert abs(residual[2, 1]) < 0.035


def test_geometry_preview_and_export_scale_consistency():
    settings = EditSettings(
        geometry=(1, 0.035, 0, -0.02, 1, 0, 0.08, 0.18, 1), aspect=12
    )
    small = render(Image.new("RGB", (1000, 800), "white"), settings)
    large = render(Image.new("RGB", (4000, 3200), "white"), settings)
    assert abs(small.width / small.height - large.width / large.height) < 0.003
    assert np.asarray(large).min() == 255
