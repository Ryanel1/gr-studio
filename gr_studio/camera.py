"""Read-only USB imports through libmtp's command-line tools.

The GR IV reports as an unknown USB ID in libmtp 1.1.23 but still supports
standard MTP operations. Warnings alone are not treated as transfer failures.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading


class CameraError(RuntimeError):
    """An actionable error while reading the camera."""


@dataclass(frozen=True)
class CameraFile:
    id: int
    name: str
    size: int
    storage: str


_USB_LOCK = threading.RLock()
_STORAGE_NAMES = {0x00010001: "SD", 0x00080001: "Internal memory"}


def _executable(name: str) -> str:
    path = shutil.which(name)
    if not path and sys.platform == "darwin":
        for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
            candidate = Path(prefix) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                path = str(candidate)
                break
    if not path:
        hint = (
            "brew install libmtp"
            if sys.platform == "darwin"
            else "sudo pacman -S libmtp"
        )
        raise CameraError(
            f"USB import requires {name}. Install libmtp ({hint}), then try again."
        )
    return path


def _run(name: str, *args: str, timeout: int = 120) -> str:
    try:
        result = subprocess.run(
            [_executable(name), *args],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CameraError(
            "The camera did not respond in time. Reconnect USB-C and try again."
        ) from exc
    except OSError as exc:
        raise CameraError(f"Could not start the camera importer: {exc}") from exc
    output = result.stdout + "\n" + result.stderr
    lower = output.lower()
    if any(
        text in lower
        for text in ("no raw devices found", "no devices found", "no mtp devices")
    ):
        raise CameraError(
            "No camera found. Connect the GR IV with a USB data cable and try again."
        )
    if any(
        text in lower
        for text in (
            "could not open raw device",
            "unable to open raw device",
            "unable to open device",
        )
    ):
        raise CameraError(
            "Cannot open the camera. Close other photo or file-transfer apps, reconnect USB-C, and try again."
        )
    if result.returncode != 0:
        details = [
            line.strip()
            for line in output.splitlines()
            if any(
                word in line.lower()
                for word in ("error", "failed", "cannot", "could not")
            )
        ]
        detail = (
            details[-1][:220]
            if details
            else f"libmtp exited with status {result.returncode}."
        )
        raise CameraError(
            f"Camera transfer failed. {detail} Reconnect USB-C and try again."
        )
    return output


def parse_files(output: str) -> list[CameraFile]:
    """Parse mtp-files output, preserving storage and raw-file identities."""
    files = []
    for block in re.split(r"(?m)^File ID:\s*", output)[1:]:
        identifier = re.match(r"(\d+)", block)
        name = re.search(r"(?m)^\s*Filename:\s*(.+)$", block)
        size = re.search(r"(?m)^\s*File size\s+(\d+)", block)
        storage = re.search(r"(?m)^\s*Storage ID:\s*(0x[0-9a-fA-F]+|\d+)", block)
        if not all((identifier, name, size, storage)):
            continue
        filename = name.group(1).strip()
        if Path(filename).suffix.lower() not in (".jpg", ".jpeg", ".dng"):
            continue
        storage_id = int(storage.group(1), 0)
        files.append(
            CameraFile(
                int(identifier.group(1)),
                filename,
                int(size.group(1)),
                _STORAGE_NAMES.get(storage_id, f"Storage {storage_id:#x}"),
            )
        )
    return files


def list_files() -> list[CameraFile]:
    """List camera JPEG/DNG files. An empty connected camera returns []."""
    with _USB_LOCK:
        _check_device()
        output = _run("mtp-files")
        if (
            "Successfully connected" not in output
            and "Listing File Information" not in output
        ):
            raise CameraError(
                "The camera could not be read. Close other import apps and reconnect USB-C."
            )
        return parse_files(output)


def _safe_filename(name: str) -> str:
    # Cameras can send arbitrary metadata. Treat both path separators as separators.
    clean = name.replace("\\", "/").rsplit("/", 1)[-1]
    clean = re.sub(r'[\x00-\x1f<>:"|?*]', "_", clean).strip(" .")
    if not clean or clean in (".", ".."):
        raise CameraError("The camera supplied an invalid filename.")
    return clean


def _publish_unique(partial: Path, folder: Path, name: str) -> Path:
    """Hard-link atomically: an existing file is never replaced, including races."""
    stem, suffix = Path(name).stem, Path(name).suffix
    for index in range(10000):
        destination = folder / (name if index == 0 else f"{stem}-{index}{suffix}")
        try:
            os.link(partial, destination)
        except FileExistsError:
            continue
        except OSError as exc:
            raise CameraError(
                f"Could not save the imported photo in {folder}: {exc}"
            ) from exc
        return destination
    raise CameraError(
        "Too many duplicate filenames in this folder. Choose a different import folder."
    )


def download(file: CameraFile, folder: str | Path) -> Path:
    """Download an original with length verification and atomic, unique naming."""
    destination_folder = Path(folder).expanduser()
    destination_folder.mkdir(parents=True, exist_ok=True)
    name = _safe_filename(file.name)
    if file.id <= 0 or file.size <= 0:
        raise CameraError(
            "This camera file has invalid transfer metadata. Refresh the camera list."
        )
    with _USB_LOCK:
        _check_device()
        fd, temporary = tempfile.mkstemp(
            prefix=".gr-import-", suffix=".partial", dir=destination_folder
        )
        os.close(fd)
        partial = Path(temporary)
        try:
            _run("mtp-getfile", str(file.id), str(partial), timeout=300)
            if partial.stat().st_size != file.size:
                raise CameraError(
                    "The download was incomplete. Reconnect the camera and import the photo again."
                )
            return _publish_unique(partial, destination_folder, name)
        finally:
            partial.unlink(missing_ok=True)


def thumbnail(file: CameraFile, cache_dir: str | Path) -> Path | None:
    """Read a camera thumbnail when available; failure leaves a generic tile."""
    from PIL import Image

    cache = Path(cache_dir).expanduser()
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(
        f"{file.storage}:{file.id}:{file.name}:{file.size}".encode()
    ).hexdigest()[:24]
    target = cache / f"{key}.jpg"
    with _USB_LOCK:
        if target.is_file():
            try:
                with Image.open(target) as image:
                    image.verify()
                return target
            except (OSError, ValueError):
                target.unlink(missing_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".gr-thumb-", suffix=".jpg", dir=cache)
        os.close(fd)
        partial = Path(temporary)
        try:
            # mtp-thumb is an upload command. Use the read-only API in a bounded
            # subprocess so a USB stall cannot leave a UI worker stuck forever.
            result = subprocess.run(
                _helper_command("--read-thumbnail", str(file.id), str(partial)),
                capture_output=True,
                timeout=35,
                check=False,
            )
            if result.returncode:
                return None
            with Image.open(partial) as image:
                image.verify()
            os.replace(partial, target)
            return target
        except (CameraError, OSError, ValueError, subprocess.TimeoutExpired):
            return None
        finally:
            partial.unlink(missing_ok=True)


def _helper_command(*args):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--camera-helper", *args]
    return [sys.executable, str(Path(__file__).resolve()), *args]


def _check_device() -> None:
    """Require one GR IV so legacy CLI tools cannot select a different device."""
    _executable("mtp-files")
    try:
        result = subprocess.run(
            _helper_command("--check-device"),
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CameraError(
            "Could not identify the camera. Reconnect USB-C and try again."
        ) from exc
    if result.returncode:
        raise CameraError(
            "Connect one RICOH GR IV and disconnect other MTP devices, then try again."
        )


def _native_library():
    import ctypes
    import ctypes.util

    library_path = ctypes.util.find_library("mtp")
    if not library_path:
        for prefix in ("/opt/homebrew/lib", "/usr/local/lib"):
            candidate = Path(prefix) / "libmtp.dylib"
            if candidate.is_file():
                library_path = str(candidate)
                break
    if not library_path:
        raise OSError("libmtp is not installed")
    lib = ctypes.CDLL(library_path)
    lib.LIBMTP_Init.argtypes = []
    lib.LIBMTP_Init.restype = None
    lib.LIBMTP_Init()
    return lib


def _single_ricoh(lib, *, open_device=False):
    import ctypes as c
    import ctypes.util

    class Entry(c.Structure):
        _fields_ = [
            ("vendor", c.c_char_p),
            ("vendor_id", c.c_uint16),
            ("product", c.c_char_p),
            ("product_id", c.c_uint16),
            ("flags", c.c_uint32),
        ]

    class Raw(c.Structure):
        _fields_ = [("entry", Entry), ("bus", c.c_uint32), ("number", c.c_uint8)]

    lib.LIBMTP_Detect_Raw_Devices.argtypes = [
        c.POINTER(c.POINTER(Raw)),
        c.POINTER(c.c_int),
    ]
    lib.LIBMTP_Detect_Raw_Devices.restype = c.c_int
    raw, count = c.POINTER(Raw)(), c.c_int()
    code = lib.LIBMTP_Detect_Raw_Devices(c.byref(raw), c.byref(count))
    try:
        matches = (
            code == 0
            and count.value == 1
            and raw
            and raw[0].entry.vendor_id == 0x25FB
            and raw[0].entry.product_id == 0x2123
        )
        if not matches:
            return None if open_device else False
        if not open_device:
            return True
        # Opening a cached device enumerates every camera object. For a known
        # object ID, open directly and request only its embedded thumbnail.
        lib.LIBMTP_Open_Raw_Device_Uncached.argtypes = [c.POINTER(Raw)]
        lib.LIBMTP_Open_Raw_Device_Uncached.restype = c.c_void_p
        return lib.LIBMTP_Open_Raw_Device_Uncached(raw)

    finally:
        if raw:
            libc = c.CDLL(ctypes.util.find_library("c") or None)
            libc.free.argtypes = [c.c_void_p]
            libc.free.restype = None
            libc.free(raw)


def _read_thumbnail_native(identifier: int, destination: Path) -> int:
    """Child-process entry: only libmtp Get operations are exposed."""
    import ctypes
    import ctypes.util

    lib = _native_library()
    lib.LIBMTP_Release_Device.argtypes = [ctypes.c_void_p]
    lib.LIBMTP_Release_Device.restype = None
    lib.LIBMTP_Get_Thumbnail.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint),
    ]
    lib.LIBMTP_Get_Thumbnail.restype = ctypes.c_int
    libc = ctypes.CDLL(ctypes.util.find_library("c") or None)
    libc.free.argtypes = [ctypes.c_void_p]
    libc.free.restype = None
    device = _single_ricoh(lib, open_device=True)
    if not device:
        return 1
    data = ctypes.c_void_p()
    size = ctypes.c_uint()
    try:
        status = lib.LIBMTP_Get_Thumbnail(
            device, identifier, ctypes.byref(data), ctypes.byref(size)
        )
        if status != 0 or not data.value or not size.value:
            return 1
        destination.write_bytes(ctypes.string_at(data, size.value))
        return 0
    finally:
        if data.value:
            libc.free(data)
        lib.LIBMTP_Release_Device(device)


def helper_main():
    if len(sys.argv) == 2 and sys.argv[1] == "--check-device":
        raise SystemExit(0 if _single_ricoh(_native_library()) else 1)
    if len(sys.argv) == 4 and sys.argv[1] == "--read-thumbnail":
        raise SystemExit(_read_thumbnail_native(int(sys.argv[2]), Path(sys.argv[3])))
    raise SystemExit("This module is used by GR Studio.")


if __name__ == "__main__":
    helper_main()
