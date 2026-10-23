"""Compact frame controls with details shown only for the selected style."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .widgets import Adjustment, Section


class FramePanel(QWidget):
    changed = Signal(str, object)
    apply_requested = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 8)
        layout.setSpacing(16)
        self.labels = {}
        self.groups = {}

        def combo(label, key, choices, target=None):
            group = QWidget()
            row = QVBoxLayout(group)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            row.addWidget(QLabel(label))
            widget = QComboBox()
            widget.setAccessibleName(label)
            for text, value in choices:
                widget.addItem(text, value)
            widget.currentIndexChanged.connect(
                lambda: self.changed.emit(key, widget.currentData())
            )
            row.addWidget(widget)
            (target or layout).addWidget(group)
            self.groups[key] = group
            return widget

        self.border = combo(
            "Style",
            "border",
            [
                ("No border", "none"),
                ("Polaroid · original shape", "classic"),
                ("Polaroid · square crop", "square"),
                ("Even border", "even"),
                ("Fit canvas · no crop", "canvas"),
            ],
        )
        self.layout_section = Section("Layout")
        layout.addWidget(self.layout_section)
        dimensions = self.layout_section.content
        self.ratio = combo(
            "Canvas",
            "border_ratio",
            [(r, r) for r in ("1:1", "4:5", "9:16", "3:2", "2:3", "16:9")],
            dimensions,
        )
        self.width = Adjustment("Border width %", 0, 30, 10, 1)
        self.width.changed.connect(
            lambda value: self.changed.emit("border_width", value)
        )
        dimensions.addWidget(self.width)
        self.bottom = Adjustment("Bottom margin %", 0, 50, 10, 1)
        self.bottom.changed.connect(
            lambda value: self.changed.emit("border_bottom", value)
        )
        dimensions.addWidget(self.bottom)
        self.paper_section = Section("Paper", expanded=False)
        layout.addWidget(self.paper_section)
        paper_layout = self.paper_section.content
        self.background = combo(
            "Background",
            "border_background",
            [
                ("Solid color", "solid"),
                ("Color from photo", "photo"),
                ("Blurred photo", "blur"),
            ],
            paper_layout,
        )
        self.paper = combo(
            "Color",
            "border_color",
            [
                ("Warm paper", "#f4f0e7"),
                ("White", "#ffffff"),
                ("Vintage cream", "#e9dfc8"),
                ("Black", "#000000"),
            ],
            paper_layout,
        )
        self.custom_color = QPushButton("Custom color…")
        self.custom_color.clicked.connect(self.choose_color)
        self.groups["border_color"].layout().addWidget(self.custom_color)
        self.radius = Adjustment("Rounded corners %", 0, 50, 10, 1)
        self.radius.changed.connect(
            lambda value: self.changed.emit("border_radius", value)
        )
        dimensions.addWidget(self.radius)
        self.caption_group = QWidget()
        caption_layout = QVBoxLayout(self.caption_group)
        caption_layout.setContentsMargins(0, 0, 0, 0)
        caption_layout.setSpacing(8)
        caption_layout.addWidget(QLabel("Caption"))
        self.caption = QLineEdit()
        self.caption.setAccessibleName("Border caption")
        self.caption.setMaxLength(160)
        self.caption.textChanged.connect(
            lambda text: self.changed.emit("caption", text)
        )
        caption_layout.addWidget(self.caption)
        layout.addWidget(self.caption_group)
        self.caption.setToolTip("Caption for the previewed photo")
        self.apply_button = QPushButton("Apply border to selected")
        self.apply_button.setToolTip(
            "Copy all frame settings. Each photo keeps its own caption and adjustments."
        )
        self.apply_button.clicked.connect(self.apply_requested.emit)
        layout.addWidget(self.apply_button)
        layout.addStretch()

    def choose_color(self):
        color = QColorDialog.getColor(
            QColor(self.paper.currentData()), self, "Border color"
        )
        if color.isValid():
            self.set_color(color.name())
            self.changed.emit("border_color", color.name())

    def set_color(self, value):
        self.paper.blockSignals(True)
        index = self.paper.findData(value)
        if index < 0:
            if self.paper.count() > 4:
                self.paper.removeItem(4)
            self.paper.addItem(value.upper(), value)
            index = self.paper.count() - 1
        self.paper.setCurrentIndex(index)
        self.paper.blockSignals(False)

    def sync(self, settings):
        for widget, value in [
            (self.border, settings.border),
            (self.ratio, settings.border_ratio),
            (self.background, settings.border_background),
        ]:
            widget.blockSignals(True)
            widget.setCurrentIndex(max(0, widget.findData(value)))
            widget.blockSignals(False)
        self.set_color(settings.border_color)
        for widget, value in [
            (self.width, settings.border_width),
            (self.bottom, settings.border_bottom),
            (self.radius, settings.border_radius),
        ]:
            widget.set_value(value)
        self.caption.blockSignals(True)
        self.caption.setText(settings.caption)
        self.caption.blockSignals(False)

    def update_state(self, settings, ready):
        framed = settings.border != "none"
        polaroid = settings.border in {"classic", "square"}
        self.layout_section.setVisible(framed)
        self.paper_section.setVisible(framed)
        self.groups["border_ratio"].setVisible(settings.border == "canvas")
        self.width.setVisible(framed)
        self.bottom.setVisible(polaroid)
        self.groups["border_background"].setVisible(framed)
        self.groups["border_color"].setVisible(
            framed and settings.border_background == "solid"
        )
        self.radius.setVisible(framed)
        self.caption_group.setVisible(polaroid)
        self.caption.setEnabled(ready and polaroid)
