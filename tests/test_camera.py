from pathlib import Path
import pytest
from gr_studio import camera


@pytest.fixture(autouse=True)
def no_hardware_probe(monkeypatch):
    monkeypatch.setattr(camera, "_check_device", lambda: None)


LISTING = """libmtp version: 1.1.23
mtp-files: Successfully connected
File ID: 152633345
   Filename: R0000001.JPG
   File size 6 (0x0000000000000006) bytes
   Parent ID: 85524480
   Storage ID: 0x00010001
   Filetype: JPEG file
File ID: 286884015
   Filename: R0000175.DNG
   File size 34323360 (0x00000000020BBBA0) bytes
   Parent ID: 85557248
   Storage ID: 0x00080001
   Filetype: Undefined filetype
File ID: 12
   Filename: DCIM
   File size 0 bytes
   Storage ID: 0x00010001
   Filetype: Folder
File ID: 13
   Filename: broken.JPG
Device 0 is UNKNOWN in libmtp v1.1.23.
OK.
"""


def test_parser_handles_unknown_device_warning_and_raw():
    result = camera.parse_files(LISTING)
    assert result == [
        camera.CameraFile(152633345, "R0000001.JPG", 6, "SD"),
        camera.CameraFile(286884015, "R0000175.DNG", 34323360, "Internal memory"),
    ]


def test_download_is_non_overwriting_and_sanitized(tmp_path, monkeypatch):
    photo = camera.CameraFile(1, "../../original.JPG", 6, "SD")
    original = tmp_path / "original.JPG"
    original.write_bytes(b"existing")

    def run(name, identifier, path, **kwargs):
        assert name == "mtp-getfile"
        Path(path).write_bytes(b"camera")

    monkeypatch.setattr(camera, "_run", run)
    result = camera.download(photo, tmp_path)
    assert result == tmp_path / "original-1.JPG"
    assert result.read_bytes() == b"camera"
    assert original.read_bytes() == b"existing"
    assert not list(tmp_path.glob("*.partial"))
    assert not list(tmp_path.glob(".gr-import-*"))


def test_failed_transfer_cleans_partial(tmp_path, monkeypatch):
    def run(name, identifier, path, **kwargs):
        Path(path).write_bytes(b"bad")

    monkeypatch.setattr(camera, "_run", run)
    with pytest.raises(camera.CameraError, match="incomplete"):
        camera.download(camera.CameraFile(1, "photo.JPG", 500, "SD"), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_camera_absent_is_actionable(monkeypatch):
    monkeypatch.setattr(camera, "_executable", lambda name: name)
    monkeypatch.setattr(
        camera.subprocess,
        "run",
        lambda *args, **kwargs: camera.subprocess.CompletedProcess(
            args, 0, "No raw devices found.", ""
        ),
    )
    with pytest.raises(camera.CameraError, match="No camera found"):
        camera.list_files()


def test_empty_camera_is_not_error(monkeypatch):
    monkeypatch.setattr(
        camera, "_run", lambda *args, **kwargs: "mtp-files: Successfully connected\nOK."
    )
    assert camera.list_files() == []


def test_duplicate_publish_race_never_overwrites(tmp_path):
    part = tmp_path / ".partial"
    part.write_bytes(b"new")
    (tmp_path / "photo.JPG").write_bytes(b"old")
    (tmp_path / "photo-1.JPG").write_bytes(b"older")
    assert camera._publish_unique(part, tmp_path, "photo.JPG").name == "photo-2.JPG"
    assert (tmp_path / "photo.JPG").read_bytes() == b"old"


def test_direct_camera_open_skips_object_enumeration(monkeypatch):
    import ctypes as c

    calls = []
    keepalive = []

    class Function:
        def __init__(self, fn):
            self.fn = fn

        def __call__(self, *args):
            return self.fn(*args)

    def detect(raw_out, count_out):
        raw_type = raw_out._obj._type_
        devices = (raw_type * 1)()
        devices[0].entry.vendor_id = 0x25FB
        devices[0].entry.product_id = 0x2123
        keepalive.append(devices)
        c.cast(raw_out, c.POINTER(c.POINTER(raw_type)))[0] = c.cast(
            devices, c.POINTER(raw_type)
        )
        count_out._obj.value = 1
        return 0

    class Library:
        LIBMTP_Detect_Raw_Devices = Function(detect)
        LIBMTP_Open_Raw_Device_Uncached = Function(
            lambda raw: calls.append("uncached") or 123
        )

    class LibC:
        free = Function(lambda raw: calls.append("free"))

    monkeypatch.setattr(c, "CDLL", lambda _: LibC())
    assert camera._single_ricoh(Library(), open_device=True) == 123
    assert calls == ["uncached", "free"]


def test_thumbnail_cache_skips_camera_connection(tmp_path, monkeypatch):
    from PIL import Image

    file = camera.CameraFile(123, "photo.JPG", 200, "SD")
    calls = []

    def run(command, **kwargs):
        from types import SimpleNamespace

        calls.append(command)
        Image.new("RGB", (160, 120), "blue").save(command[-1], format="JPEG")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(camera.subprocess, "run", run)
    first = camera.thumbnail(file, tmp_path)
    second = camera.thumbnail(file, tmp_path)
    assert first == second and first.is_file()
    assert len(calls) == 1
