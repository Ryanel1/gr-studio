import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import time

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from gr_studio.state import Library
from gr_studio.theme import STYLE
from gr_studio.window import Studio


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    return app


def settle(app, window, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if not window.jobs and not window.preview_timer.isActive():
            return
        time.sleep(0.01)
    pytest.fail("UI worker timed out")


def test_workspace_edit_export_restore(app, tmp_path):
    photo = tmp_path / "original.jpg"
    Image.new("RGB", (640, 480), "#63869a").save(photo)
    original = photo.read_bytes()
    window = Studio(tmp_path / "state")
    window.show()
    window.add_photos([photo])
    settle(app, window)
    window.controls["exposure"].spin.setValue(0.4)
    window.border.setCurrentIndex(1)
    window.caption.setText("A quiet afternoon")
    settle(app, window)
    assert window.settings.exposure == 0.4
    window.export_to(tmp_path / "export")
    settle(app, window)
    assert window.last_export.is_file()
    with Image.open(window.last_export) as image:
        assert image.width > 640 and image.height > 480
        image.load()
    assert photo.read_bytes() == original
    window.close()
    app.processEvents()
    restored = Studio(tmp_path / "state")
    restored.show()
    settle(app, restored)
    assert restored.settings.caption == "A quiet afternoon"
    assert restored.settings.exposure == 0.4
    restored.close()


def test_rapid_switch_and_reset(app, tmp_path):
    paths = []
    for name, color in [("red", "red"), ("blue", "blue")]:
        path = tmp_path / f"{name}.jpg"
        Image.new("RGB", (400, 300), color).save(path)
        paths.append(path)
    window = Studio(tmp_path / "state")
    window.show()
    window.add_photos(paths)
    window.filmstrip.setCurrentRow(1)
    settle(app, window)
    assert window.path == str(paths[1])
    assert window.source.getpixel((10, 10))[2] > 200
    window.controls["exposure"].spin.setValue(0.8)
    window.reset_edits()
    settle(app, window)
    assert window.settings.exposure == 0
    window.close()


@pytest.mark.parametrize("value", [[], None, {"photos": [5]}, {"edits": []}])
def test_invalid_session_recovers(tmp_path, value):
    (tmp_path / "session.json").write_text(json.dumps(value))
    library = Library(tmp_path)
    assert library.error


def test_invalid_edit_values_are_ignored(tmp_path):
    library = Library(tmp_path)
    library.edits = {
        "photo": {
            "exposure": "wrong",
            "angle": float("nan"),
            "caption": None,
            "border": "bad",
            "border_color": "bad",
        }
    }
    edits = library.settings("photo")
    assert edits.exposure == 0 and edits.angle == 0 and edits.border == "none"
    library.edits = {"photo": []}
    assert library.settings("photo").angle == 0


def test_uncertain_auto_straighten_preserves_manual_angle(app, tmp_path):
    photo = tmp_path / "plain.jpg"
    Image.new("RGB", (400, 300), "white").save(photo)
    window = Studio(tmp_path / "state")
    window.show()
    window.add_photos([photo])
    settle(app, window)
    window.controls["angle"].spin.setValue(2.5)
    settle(app, window)
    window.straighten()
    settle(app, window)
    assert window.settings.angle == 2.5
    window.close()


def test_auto_adjust_updates_sliders_preserves_frame_and_is_repeatable(app, tmp_path):
    import numpy as np

    photo = tmp_path / "dark.jpg"
    row = np.linspace(10, 140, 400).astype(np.uint8)
    Image.fromarray(np.repeat(np.tile(row, (300, 1))[..., None], 3, axis=2)).save(photo)
    window = Studio(tmp_path / "state")
    window.show()
    window.add_photos([photo])
    settle(app, window)
    window.border.setCurrentIndex(1)
    window.caption.setText("Keep this")
    window.controls["angle"].spin.setValue(2.5)
    settle(app, window)
    window.auto_adjust_button.click()
    settle(app, window)
    settings = window.settings
    assert settings.exposure > 0
    assert window.controls["exposure"].spin.value() == settings.exposure
    assert settings.border == "classic" and settings.caption == "Keep this"
    assert settings.angle == 2.5
    window.auto_adjust_button.click()
    settle(app, window)
    assert settings == window.settings
    assert window.library.settings(photo) == settings
    window.close()


def test_batch_adjust_border_and_export_selection(app, tmp_path):
    from dataclasses import replace

    import numpy as np

    from gr_studio.imaging import EditSettings

    paths = []
    for index, (lo, hi) in enumerate([(10, 140), (90, 250), (30, 170)]):
        path = tmp_path / f"photo{index}.jpg"
        row = np.linspace(lo, hi, 400).astype(np.uint8)
        Image.fromarray(np.repeat(np.tile(row, (300, 1))[..., None], 3, axis=2)).save(
            path
        )
        paths.append(path)
    originals = [p.read_bytes() for p in paths]
    window = Studio(tmp_path / "state")
    window.show()
    window.add_photos(paths)
    settle(app, window)
    window.library.save_edit(
        paths[1], replace(EditSettings(), angle=1.5, caption="Second")
    )
    window.filmstrip.item(1).setSelected(True)
    assert len(window.selected_paths()) == 2
    window.apply_auto_adjust()
    assert window.batch_busy and not window.filmstrip.isEnabled()
    settle(app, window)
    first, second = [window.library.settings(p) for p in paths[:2]]
    assert first.exposure != second.exposure
    assert second.angle == 1.5 and second.caption == "Second"
    assert window.library.settings(paths[2]) == EditSettings()
    window.border.setCurrentIndex(1)
    window.paper.setCurrentIndex(2)
    window.apply_frame_button.click()
    settle(app, window)
    assert window.library.settings(paths[1]).border == "classic"
    assert window.library.settings(paths[1]).border_color == "#e9dfc8"
    assert window.library.settings(paths[1]).caption == "Second"
    assert window.library.settings(paths[1]).exposure == second.exposure
    assert window.library.settings(paths[2]) == EditSettings()
    window.export_to(tmp_path / "exports")
    settle(app, window)
    exports = list((tmp_path / "exports").glob("*.jpg"))
    assert len(exports) == 2
    assert all(Image.open(p).height > 300 for p in exports)
    assert [p.read_bytes() for p in paths] == originals
    window.export_to(tmp_path / "exports")
    settle(app, window)
    assert len(list((tmp_path / "exports").glob("*.jpg"))) == 4
    window.close()


def test_batch_export_continues_after_missing_photo(app, tmp_path):
    paths = [tmp_path / f"{i}.jpg" for i in range(3)]
    for p in paths:
        Image.new("RGB", (400, 300), "blue").save(p)
    window = Studio(tmp_path / "state")
    window.add_photos(paths)
    settle(app, window)
    window.filmstrip.selectAll()
    paths[1].unlink()
    window.export_to(tmp_path / "exports")
    settle(app, window)
    assert len(list((tmp_path / "exports").glob("*.jpg"))) == 2
    assert "1 failed" in window.status.text()
    assert "1.jpg" in window.status.text()
    assert not window.batch_busy and window.export_button.isEnabled()
    window.close()


def test_new_frame_controls_copy_all_settings_and_restore(app, tmp_path):
    paths = [tmp_path / f"{i}.jpg" for i in range(2)]
    for path in paths:
        Image.new("RGB", (600, 400), "#56789a").save(path)
    window = Studio(tmp_path / "state")
    window.show()
    window.add_photos(paths)
    settle(app, window)
    window.tabs.setCurrentIndex(1)
    window.filmstrip.selectAll()
    panel = window.frame_panel
    panel.border.setCurrentIndex(panel.border.findData("canvas"))
    panel.ratio.setCurrentIndex(panel.ratio.findData("4:5"))
    panel.width.spin.setValue(12)
    panel.radius.spin.setValue(8)
    panel.background.setCurrentIndex(panel.background.findData("blur"))
    window.apply_frame_button.click()
    settle(app, window)
    second = window.library.settings(paths[1])
    assert second.border == "canvas" and second.border_ratio == "4:5"
    assert second.border_width == 12 and second.border_radius == 8
    assert second.border_background == "blur"
    assert panel.groups["border_ratio"].isVisible()
    assert not panel.groups["border_color"].isVisible()
    window.export_to(tmp_path / "exports")
    settle(app, window)
    for path in (tmp_path / "exports").glob("*.jpg"):
        with Image.open(path) as output:
            assert output.width * 5 == output.height * 4
    window.close()
    restored = Studio(tmp_path / "state")
    settle(app, restored)
    assert restored.settings.border_ratio == "4:5"
    assert restored.frame_panel.width.spin.value() == 12
    restored.close()


def test_guided_mouse_apply_export_and_cancel(app, tmp_path):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from gr_studio.geometry import IDENTITY

    photo = tmp_path / "building.jpg"
    Image.new("RGB", (1000, 800), "#aabbcc").save(photo)
    window = Studio(tmp_path / "state")
    window.show()
    window.add_photos([photo])
    settle(app, window)
    window.border.setCurrentIndex(1)
    settle(app, window)
    window.tabs.setCurrentIndex(2)
    panel = window.geometry_panel
    panel.mode.setCurrentIndex(panel.mode.findData("guided"))
    app.processEvents()
    assert window.view.guiding
    assert not window.export_button.isEnabled()
    assert window.view.image.width() == window.source.width
    rect = window.view.image_rect()

    def point(x, y):
        return QPoint(
            round(rect.x() + rect.width() * x), round(rect.y() + rect.height() * y)
        )

    for start, end in [((0.3, 0.15), (0.2, 0.85)), ((0.7, 0.15), (0.8, 0.85))]:
        QTest.mousePress(window.view, Qt.MouseButton.LeftButton, pos=point(*start))
        QTest.mouseMove(window.view, point(*end))
        QTest.mouseRelease(window.view, Qt.MouseButton.LeftButton, pos=point(*end))
    assert len(window.view.guides) == 2
    assert panel.apply.isEnabled()
    panel.apply.click()
    settle(app, window)
    assert not window.view.guiding
    assert window.settings.geometry != IDENTITY
    assert window.settings.geometry_mode == "guided"
    assert window.settings.border == "classic"
    assert window.export_button.isEnabled()
    saved = window.settings
    panel.apply.click()  # Redraw guides for an already-applied Guided correction.
    assert window.view.guiding
    window.cancel_guides()
    settle(app, window)
    assert window.settings == saved
    window.export_to(tmp_path / "export")
    settle(app, window)
    assert window.last_export.is_file()
    window.close()
    restored = Studio(tmp_path / "state")
    settle(app, restored)
    assert restored.settings == saved
    restored.reset_geometry()
    settle(app, restored)
    assert restored.settings.geometry == IDENTITY
    assert restored.settings.border == "classic"
    restored.close()


def test_auto_vertical_failure_keeps_previous_geometry(app, tmp_path):
    from dataclasses import replace

    photo = tmp_path / "plain.jpg"
    Image.new("RGB", (600, 400), "gray").save(photo)
    window = Studio(tmp_path / "state")
    window.add_photos([photo])
    settle(app, window)
    window.settings = replace(window.settings, vertical=12, angle=1.5)
    previous = window.settings
    window.run_upright("vertical")
    settle(app, window)
    assert window.settings == previous
    assert "Guided" in window.status.text()
    assert not window.geometry_busy
    window.close()


def test_archive_numeric_entry_and_locked_menu_actions(app, tmp_path):
    """Styled spinbox text must remain editable; menus obey batch/guide locks."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from gr_studio.theme import apply_theme

    apply_theme(app)
    photo = tmp_path / "photo.jpg"
    Image.new("RGB", (400, 300), "gray").save(photo)
    window = Studio(tmp_path / "state")
    window.show()
    window.add_photos([photo])
    settle(app, window)
    spin = window.controls["exposure"].spin
    assert spin.lineEdit().width() >= 40
    assert spin.lineEdit().height() >= spin.fontMetrics().height()
    spin.setFocus()
    spin.selectAll()
    QTest.keyClicks(spin, "-1.2")
    QTest.keyClick(spin, Qt.Key.Key_Return)
    settle(app, window)
    assert window.settings.exposure == -1.2
    window._sync_menus()
    open_action = window.menus["File"].actions()[0]
    assert open_action.isEnabled()
    window.batch_busy = True
    window.update_enabled()
    window._sync_menus()
    assert not open_action.isEnabled()
    assert not window.menu_buttons["View"].isEnabled()
    window.batch_busy = False
    window.update_enabled()
    window.close()


def test_tuning_controls_persist_per_photo_export_and_reset(app, tmp_path):
    from dataclasses import asdict

    import numpy as np

    paths = [tmp_path / f"tuning-{i}.png" for i in range(2)]
    ramp = np.tile(np.arange(256, dtype=np.uint8), (160, 1))
    pixels = np.stack(
        (ramp, np.roll(ramp, 70, axis=1), np.roll(ramp, 140, axis=1)), axis=2
    )
    for path in paths:
        Image.fromarray(pixels).save(path)
    window = Studio(tmp_path / "state")
    window.show()
    window.add_photos(paths)
    settle(app, window)
    panel = window.tuning_panel
    assert panel.sections["Light"].toggle.isChecked()
    assert all(
        not section.toggle.isChecked()
        for title, section in panel.sections.items()
        if title != "Light"
    )
    values = {
        "whites": 15,
        "blacks": -12,
        "tint": 8,
        "vibrance": 22,
        "texture": 17,
        "clarity": 11,
        "dehaze": 9,
        "grain": 13,
        "vignette": -18,
        "sharpening": 20,
        "noise_reduction": 7,
    }
    for key, value in values.items():
        window.controls[key].spin.setValue(value)
    panel.curve.setCurrentText("Faded shadows")
    panel.mixer_controls["hue"].spin.setValue(24)
    old_settings = window.settings
    panel.mixer_controls["saturation"].spin.setValue(-28)
    assert old_settings.mixer["red"]["saturation"] == 0
    panel.band.setCurrentText("Blue")
    assert panel.mixer_controls["hue"].spin.value() == 0
    panel.mixer_controls["luminance"].spin.setValue(31)
    panel.band.setCurrentText("Red")
    assert panel.mixer_controls["hue"].spin.value() == 24
    assert panel.mixer_controls["saturation"].spin.value() == -28
    settle(app, window)
    edited = window.settings
    assert all(getattr(edited, key) == value for key, value in values.items())
    window.filmstrip.setCurrentRow(1)
    settle(app, window)
    assert window.settings.mixer == {} and window.settings.curve == "Linear"
    assert all(window.controls[key].spin.value() == 0 for key in values)
    window.filmstrip.setCurrentRow(0)
    settle(app, window)
    assert window.settings == edited
    assert panel.curve_preview.preset == "Faded shadows"
    window.export_to(tmp_path / "exports")
    settle(app, window)
    with Image.open(window.last_export) as output:
        assert output.size == (256, 160)
        assert not np.array_equal(np.asarray(output), pixels)
    window.close()
    restored = Studio(tmp_path / "state")
    restored.show()
    settle(app, restored)
    assert asdict(restored.settings) == asdict(edited)
    assert restored.tuning_panel.mixer_controls["hue"].spin.value() == 24
    restored.reset_edits()
    settle(app, restored)
    assert restored.settings.mixer == {}
    assert restored.tuning_panel.curve.currentText() == "Linear"
    assert restored.tuning_panel.mixer_controls["hue"].spin.value() == 0
    assert all(restored.controls[key].spin.value() == 0 for key in values)
    restored.close()


def test_tuning_sections_scroll_at_minimum_window_size(app, tmp_path):
    from PySide6.QtWidgets import QScrollArea

    photo = tmp_path / "photo.png"
    Image.new("RGB", (300, 200), "gray").save(photo)
    window = Studio(tmp_path / "state")
    window.resize(940, 680)
    window.show()
    window.add_photos([photo])
    settle(app, window)
    for section in window.tuning_panel.sections.values():
        section.toggle.setChecked(True)
    app.processEvents()
    scroll = window.findChild(QScrollArea)
    last = window.controls["noise_reduction"]
    scroll.ensureWidgetVisible(last)
    app.processEvents()
    assert scroll.verticalScrollBar().maximum() > 0
    position = last.mapTo(scroll.viewport(), last.rect().center())
    assert scroll.viewport().rect().contains(position)
    assert window.export_button.isVisible()
    assert window.export_button.isEnabled()
    assert window.size().width() == 940
    window.close()
