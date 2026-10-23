"""Native tonal, color, and detail controls for the Adjust inspector."""

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QComboBox, QVBoxLayout, QWidget

from .theme import CANVAS, TEXT
from .tuning import CURVE_PRESETS, curve_values
from .widgets import Adjustment, Section


class CurvePreview(QWidget):
    """Read-only graph of the same transfer function used by the renderer."""

    def __init__(self):
        super().__init__()
        self.preset = "Linear"
        self.setFixedHeight(150)
        self.setAccessibleName("Tone curve preview: Linear")
        self.setToolTip("Input tones run left to right; output tones run bottom to top")

    def set_preset(self, preset):
        self.preset = preset
        self.setAccessibleName(f"Tone curve preview: {preset}")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        painter.fillRect(rect, QColor(CANVAS))
        painter.setPen(QPen(QColor("#363638"), 1))
        painter.drawRect(rect)
        for fraction in (0.25, 0.5, 0.75):
            x = rect.left() + rect.width() * fraction
            y = rect.top() + rect.height() * fraction
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        painter.setPen(QPen(QColor("#505052"), 1))
        painter.drawLine(rect.bottomLeft(), rect.topRight())
        values = np.linspace(0, 1, 129)
        outputs = curve_values(values, self.preset)
        path = QPainterPath()
        for i, (x, y) in enumerate(zip(values, outputs)):
            point = QPointF(
                rect.left() + float(x) * rect.width(),
                rect.bottom() - float(y) * rect.height(),
            )
            if i == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        painter.setPen(QPen(QColor(TEXT), 2))
        painter.drawPath(path)


class TuningPanel(QWidget):
    changed = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.controls = {}
        self.sections = {}
        self._mixer = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        groups = {
            "Light": (
                "exposure",
                "contrast",
                "highlights",
                "shadows",
                "whites",
                "blacks",
            ),
            "Color": ("warmth", "tint", "vibrance", "saturation"),
            "Effects": ("texture", "clarity", "dehaze", "grain", "vignette"),
            "Detail": ("sharpening", "noise_reduction"),
        }
        for title in ("Light", "Color", "Effects", "Detail", "Curve", "Mixer"):
            section = Section(title, expanded=title == "Light")
            self.sections[title] = section
            layout.addWidget(section)
            if title == "Curve":
                self.curve = QComboBox()
                self.curve.addItems(CURVE_PRESETS)
                self.curve.setAccessibleName("Tone curve preset")
                self.curve_preview = CurvePreview()
                section.content.addWidget(self.curve)
                section.content.addWidget(self.curve_preview)
                self.curve.currentTextChanged.connect(self._curve_changed)
            elif title == "Mixer":
                self.band = QComboBox()
                for band in (
                    "Red",
                    "Orange",
                    "Yellow",
                    "Green",
                    "Aqua",
                    "Blue",
                    "Purple",
                    "Magenta",
                ):
                    self.band.addItem(band, band.lower())
                self.band.setAccessibleName("Color mixer band")
                section.content.addWidget(self.band)
                self.mixer_controls = {}
                for key in ("hue", "saturation", "luminance"):
                    control = Adjustment(key.capitalize(), -100, 100)
                    control.changed.connect(
                        lambda value, key=key: self._mixer_changed(key, value)
                    )
                    self.mixer_controls[key] = control
                    section.content.addWidget(control)
                self.band.currentIndexChanged.connect(self._sync_band)
            else:
                for key in groups[title]:
                    minimum = (
                        0 if key in ("grain", "sharpening", "noise_reduction") else -100
                    )
                    bounds = (
                        (-2, 2, 10, 1) if key == "exposure" else (minimum, 100, 1, 0)
                    )
                    control = Adjustment(key.replace("_", " ").capitalize(), *bounds)
                    if key == "vignette":
                        control.setToolTip(
                            "Negative values darken corners; positive values lighten corners"
                        )
                    control.changed.connect(
                        lambda value, key=key: self.changed.emit(key, value)
                    )
                    self.controls[key] = control
                    section.content.addWidget(control)

    def _curve_changed(self, preset):
        self.curve_preview.set_preset(preset)
        self.changed.emit("curve", preset)

    def _mixer_changed(self, key, value):
        # Render workers and saved edits may retain the previous settings snapshot.
        mixer = {band: values.copy() for band, values in self._mixer.items()}
        band = self.band.currentData()
        values = {"hue": 0.0, "saturation": 0.0, "luminance": 0.0}
        values.update(mixer.get(band, {}))
        values[key] = value
        if any(values.values()):
            mixer[band] = values
        else:
            mixer.pop(band, None)
        self._mixer = mixer
        self.changed.emit(
            "mixer", {band: values.copy() for band, values in mixer.items()}
        )

    def _sync_band(self):
        band = self.band.currentData()
        values = self._mixer.get(band, {})
        for key, control in self.mixer_controls.items():
            control.set_value(values.get(key, 0.0))
            name = f"{self.band.currentText()} {key}"
            control.spin.setAccessibleName(name)
            control.slider.setAccessibleName(name)

    def sync(self, settings):
        for key, control in self.controls.items():
            control.set_value(getattr(settings, key))
        self.curve.blockSignals(True)
        self.curve.setCurrentText(settings.curve)
        self.curve.blockSignals(False)
        self.curve_preview.set_preset(settings.curve)
        self._mixer = {band: values.copy() for band, values in settings.mixer.items()}
        self._sync_band()
