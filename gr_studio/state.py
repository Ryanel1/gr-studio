"""Persist edits separately from originals, with atomic session writes."""

import json
import math
import os
from dataclasses import asdict, fields
from pathlib import Path
from .imaging import EditSettings


_SIGNED_TUNING = {
    "whites", "blacks", "tint", "vibrance", "texture", "clarity", "dehaze", "vignette"
}
_UNSIGNED_TUNING = {"grain", "sharpening", "noise_reduction"}
_CURVES = {"Linear", "Soft contrast", "Faded shadows", "Strong contrast"}
_MIXER_COLORS = {"red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta"}


def _tuning_number(value, minimum=-100.0):
    """Restore JSON numbers only, clipping finite values to the control range."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    # Comparing integers before conversion also handles arbitrarily large JSON ints.
    if isinstance(value, float) and not math.isfinite(value):
        return 0.0
    return float(max(minimum, min(100.0, value)))


def _restore_mixer(value):
    if not isinstance(value, dict):
        return {}
    return {
        color: {
            channel: _tuning_number(adjustments.get(channel, 0.0))
            for channel in ("hue", "saturation", "luminance")
        }
        for color, adjustments in value.items()
        if color in _MIXER_COLORS and isinstance(adjustments, dict)
    }


class Library:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder / "session.json"
        self.photos = []
        self.edits = {}
        self.import_folder = str(Path.home() / "Pictures" / "GR Imports")
        self.export_folder = str(Path.home() / "Pictures" / "GR Exports")
        self.error = None
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text())
                if not isinstance(data, dict):
                    raise ValueError("Session must be an object")
                if not isinstance(data.get("photos", []), list) or not all(
                    isinstance(p, str) for p in data.get("photos", [])
                ):
                    raise ValueError("Invalid photo list")
                if not isinstance(data.get("edits", {}), dict):
                    raise ValueError("Invalid edit settings")
                self.photos = [p for p in data.get("photos", []) if Path(p).is_file()]
                self.edits = data.get("edits", {})
                self.import_folder = data.get("import_folder", self.import_folder)
                self.export_folder = data.get("export_folder", self.export_folder)
        except (OSError, ValueError, TypeError) as exc:
            self.error = f"Previous session could not be restored: {exc}"

    def settings(self, path):
        allowed = {f.name for f in fields(EditSettings)}
        values = self.edits.get(str(path), {})
        if not isinstance(values, dict):
            return EditSettings()
        defaults = EditSettings()
        valid = {}
        for key, value in values.items():
            if key not in allowed:
                continue
            default = getattr(defaults, key)
            if key in _SIGNED_TUNING | _UNSIGNED_TUNING:
                value = _tuning_number(value, 0.0 if key in _UNSIGNED_TUNING else -100.0)
            elif key == "mixer":
                value = _restore_mixer(value)
            elif key == "geometry":
                from .geometry import checked_matrix

                try:
                    value = tuple(checked_matrix(value).ravel())
                except (ValueError, TypeError):
                    continue
            elif isinstance(default, float):
                if not isinstance(value, (int, float)) or not math.isfinite(value):
                    continue
            elif not isinstance(value, str):
                continue
            if key == "curve" and value not in _CURVES:
                continue
            if key == "geometry_mode" and value not in {
                "off",
                "level",
                "vertical",
                "auto",
                "full",
                "guided",
            }:
                continue
            if key == "border" and value not in (
                "none",
                "classic",
                "square",
                "even",
                "canvas",
            ):
                continue
            if key == "border_ratio" and value not in {
                "1:1",
                "4:5",
                "9:16",
                "3:2",
                "2:3",
                "16:9",
            }:
                continue
            if key == "border_background" and value not in {"solid", "photo", "blur"}:
                continue
            if key == "border_color":
                from PIL import ImageColor

                try:
                    ImageColor.getrgb(value)
                except (ValueError, TypeError):
                    continue
            valid[key] = value
        return EditSettings(**valid)

    def save_edit(self, path, settings):
        self.edits[str(path)] = asdict(settings)
        self.save()

    def save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(
                {
                    "photos": self.photos,
                    "edits": self.edits,
                    "import_folder": self.import_folder,
                    "export_folder": self.export_folder,
                },
                indent=2,
            )
        )
        os.replace(temp, self.path)
