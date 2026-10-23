"""Session compatibility, validation, and isolation for photo tuning controls."""

import json

import pytest

from gr_studio.imaging import EditSettings
from gr_studio.state import Library


SIGNED = ("whites", "blacks", "tint", "vibrance", "texture", "clarity", "dehaze", "vignette")
UNSIGNED = ("grain", "sharpening", "noise_reduction")
COLORS = ("red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta")


@pytest.mark.parametrize("curve", ["Linear", "Soft contrast", "Faded shadows", "Strong contrast"])
def test_all_tuning_fields_roundtrip(tmp_path, curve):
    values = {key: -35.25 for key in SIGNED}
    values.update({key: 47.5 for key in UNSIGNED})
    settings = EditSettings(
        **values,
        curve=curve,
        mixer={color: {"hue": -23.5, "saturation": 42.0, "luminance": 13.25} for color in COLORS},
    )
    Library(tmp_path).save_edit("photo", settings)
    restored = Library(tmp_path)
    assert restored.error is None
    assert restored.settings("photo") == settings


def test_old_sessions_and_unknown_photos_use_neutral_tuning(tmp_path):
    (tmp_path / "session.json").write_text(json.dumps({"edits": {"old": {"exposure": 0.5}}}))
    library = Library(tmp_path)
    for path in ("old", "missing"):
        settings = library.settings(path)
        assert all(getattr(settings, key) == 0.0 for key in SIGNED + UNSIGNED)
        assert settings.curve == "Linear"
        assert settings.mixer == {}
    assert library.settings("old").exposure == 0.5


@pytest.mark.parametrize("bad", [True, False, None, "12", [], {}, float("nan"), float("inf"), -float("inf")])
def test_malformed_numeric_tuning_is_neutral(tmp_path, bad):
    library = Library(tmp_path)
    library.edits["photo"] = dict.fromkeys(SIGNED + UNSIGNED, bad)
    settings = library.settings("photo")
    assert all(getattr(settings, key) == 0.0 for key in SIGNED + UNSIGNED)


@pytest.mark.parametrize("value, signed, unsigned", [(1234, 100.0, 100.0), (-1234, -100.0, 0.0), (10**400, 100.0, 100.0)])
def test_numeric_tuning_is_clipped(tmp_path, value, signed, unsigned):
    library = Library(tmp_path)
    library.edits["photo"] = dict.fromkeys(SIGNED + UNSIGNED, value)
    settings = library.settings("photo")
    assert all(getattr(settings, key) == signed for key in SIGNED)
    assert all(getattr(settings, key) == unsigned for key in UNSIGNED)


@pytest.mark.parametrize("curve", ["unknown", "linear", "", None, [], {}, True, 1])
def test_bad_curves_restore_linear(tmp_path, curve):
    library = Library(tmp_path)
    library.edits["photo"] = {"curve": curve}
    assert library.settings("photo").curve == "Linear"


def test_nested_mixer_sanitization(tmp_path):
    library = Library(tmp_path)
    library.edits["photo"] = {"mixer": {
        "red": {"hue": 200, "saturation": -200, "luminance": 15.5, "bogus": 10},
        "green": {"hue": True, "saturation": float("nan"), "luminance": "8"},
        "blue": {"hue": float("inf"), "saturation": -float("inf")},
        "orange": {}, "yellow": [], "purple": None,
        "unknown": {"hue": 10}, "Red": {"hue": 10},
    }}
    assert library.settings("photo").mixer == {
        "red": {"hue": 100.0, "saturation": -100.0, "luminance": 15.5},
        "green": {"hue": 0.0, "saturation": 0.0, "luminance": 0.0},
        "blue": {"hue": 0.0, "saturation": 0.0, "luminance": 0.0},
        "orange": {"hue": 0.0, "saturation": 0.0, "luminance": 0.0},
    }


@pytest.mark.parametrize("bad", [None, [], "red", 20, True])
def test_nonmapping_mixer_is_empty(tmp_path, bad):
    library = Library(tmp_path)
    library.edits["photo"] = {"mixer": bad}
    assert library.settings("photo").mixer == {}


def test_mixer_settings_are_independent_from_saved_and_other_photos(tmp_path):
    library = Library(tmp_path)
    settings = EditSettings(mixer={"red": {"hue": 12.0, "saturation": 0.0, "luminance": 0.0}})
    library.save_edit("first", settings)
    library.save_edit("second", settings)
    settings.mixer["red"]["hue"] = 99.0
    first = library.settings("first")
    first.mixer["red"]["hue"] = -50.0
    assert library.settings("first").mixer["red"]["hue"] == 12.0
    assert library.settings("second").mixer["red"]["hue"] == 12.0
    assert Library(tmp_path).settings("first").mixer["red"]["hue"] == 12.0
    fresh = EditSettings()
    fresh.mixer["red"] = {"hue": 33.0}
    assert EditSettings().mixer == {}
    missing = library.settings("missing")
    missing.mixer["blue"] = {"hue": 33.0}
    assert library.settings("missing").mixer == {}
