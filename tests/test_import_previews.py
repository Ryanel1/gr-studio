import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
from threading import Event
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from gr_studio.import_dialog import ImportDialog
from gr_studio.state import Library
from gr_studio import camera


def wait(app, predicate):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    assert False, "Timed out"


def test_thumbnails_load_automatically_and_selection_remains_available(
    tmp_path, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    thumb = tmp_path / "thumb.jpg"
    Image.new("RGB", (160, 120), "blue").save(thumb)
    seen = []

    def thumbnail(file, cache):
        seen.append(file.id)
        return thumb

    monkeypatch.setattr(camera, "thumbnail", thumbnail)
    files = [camera.CameraFile(i + 1, f"photo{i}.JPG", 100, "SD") for i in range(40)]
    monkeypatch.setattr(camera, "list_files", lambda: files)
    d = ImportDialog(Library(tmp_path / "state"))
    d.show()
    d.scan_camera()
    wait(app, lambda: len(seen) >= 4 and not d.jobs)
    assert not d.table.item(0, 0).icon().isNull()
    assert len(seen) < 40
    d.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert d.start.isEnabled()
    d.table.scrollToItem(d.table.item(30, 0))
    wait(app, lambda: not d.table.item(30, 0).icon().isNull() and not d.jobs)
    assert d.selected() == [files[0]]
    d.close()
    app.processEvents()


def test_import_waits_for_thumbnail_without_blocking_selection(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    release = Event()
    entered = Event()

    def thumbnail(*args):
        entered.set()
        release.wait(3)
        return None

    monkeypatch.setattr(camera, "thumbnail", thumbnail)
    target = tmp_path / "photo.JPG"
    target.write_bytes(b"data")
    downloads = []

    def download(file, folder):
        downloads.append(file.id)
        return target

    monkeypatch.setattr(camera, "download", download)
    d = ImportDialog(Library(tmp_path / "state"))
    d.show()
    d.populate([camera.CameraFile(1, "photo.JPG", 4, "SD")])
    wait(app, entered.is_set)
    assert d.table.isEnabled()
    d.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    d.import_selected()
    assert d.pending_import and not downloads
    release.set()
    wait(app, lambda: downloads and not d.jobs)
    assert downloads == [1]
    d.close()
    app.processEvents()
