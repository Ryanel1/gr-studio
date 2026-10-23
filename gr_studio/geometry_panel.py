"""Upright modes and a small, collapsible manual geometry section."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .widgets import Adjustment, Section


class GeometryPanel(QWidget):
    apply_requested = Signal()
    mode_changed = Signal(str)
    guide_direction = Signal(str)
    undo_requested = Signal()
    cancel_requested = Signal()
    reset_requested = Signal()
    changed = Signal(str, float)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 8)
        layout.setSpacing(16)
        upright = Section("Upright")
        layout.addWidget(upright)
        upright_layout = upright.content
        self.mode = QComboBox()
        self.mode.setAccessibleName("Upright mode")
        for label, value in [
            ("Off", "off"),
            ("Level", "level"),
            ("Vertical", "vertical"),
            ("Auto", "auto"),
            ("Full", "full"),
            ("Guided", "guided"),
        ]:
            self.mode.addItem(label, value)
        self.mode.currentIndexChanged.connect(
            lambda: self.mode_changed.emit(self.mode.currentData())
        )
        upright_layout.addWidget(self.mode)
        self.apply = QPushButton("Apply")
        self.apply.setObjectName("primary")
        self.apply.clicked.connect(self.apply_requested.emit)
        upright_layout.addWidget(self.apply)
        self.guide_tools = QWidget()
        guides = QVBoxLayout(self.guide_tools)
        guides.setContentsMargins(0, 0, 0, 0)
        guides.setSpacing(12)
        self.direction = QComboBox()
        self.direction.setAccessibleName("Guide direction")
        self.direction.addItem("Vertical guides", "vertical")
        self.direction.addItem("Horizontal guides", "horizontal")
        self.direction.currentIndexChanged.connect(
            lambda: self.guide_direction.emit(self.direction.currentData())
        )
        guides.addWidget(self.direction)
        self.count = QLabel("0 vertical · 0 horizontal")
        guides.addWidget(self.count)
        row = QHBoxLayout()
        self.undo = QPushButton("Undo guide")
        self.undo.clicked.connect(self.undo_requested.emit)
        row.addWidget(self.undo)
        self.cancel = QPushButton("Cancel")
        self.cancel.clicked.connect(self.cancel_requested.emit)
        row.addWidget(self.cancel)
        guides.addLayout(row)
        upright_layout.addWidget(self.guide_tools)
        self.guide_tools.hide()
        manual_section = Section("Manual adjustments", expanded=False)
        layout.addWidget(manual_section)
        self.manual_toggle = manual_section.toggle
        self.manual = manual_section.body
        manual = manual_section.content
        self.controls = {}
        for key, label, lo, hi, scale, decimals in [
            ("vertical", "Vertical", -100, 100, 1, 0),
            ("horizontal", "Horizontal", -100, 100, 1, 0),
            ("aspect", "Aspect", -100, 100, 1, 0),
            ("angle", "Rotate", -15, 15, 10, 1),
        ]:
            control = Adjustment(label, lo, hi, scale, decimals)
            control.changed.connect(
                lambda value, key=key: self.changed.emit(key, value)
            )
            self.controls[key] = control
            manual.addWidget(control)
        self.reset = QPushButton("Reset geometry")
        self.reset.setObjectName("quiet")
        self.reset.clicked.connect(self.reset_requested.emit)
        layout.addWidget(self.reset)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setObjectName("muted")
        self.message.hide()
        layout.addWidget(self.message)
        layout.addStretch()

    def sync(self, settings):
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(max(0, self.mode.findData(settings.geometry_mode)))
        self.mode.blockSignals(False)
        for key, control in self.controls.items():
            control.set_value(getattr(settings, key))

    def guide_state(self, active, guides):
        self.guide_tools.setVisible(active)
        self.manual_toggle.setEnabled(not active)
        self.manual.setEnabled(not active)
        self.reset.setEnabled(not active)
        self.apply.setText(
            "Apply guides"
            if active
            else "Draw guides"
            if self.mode.currentData() == "guided"
            else "Apply"
        )
        v = sum(g[0] == "vertical" for g in guides)
        h = sum(g[0] == "horizontal" for g in guides)
        self.count.setText(f"{v} vertical · {h} horizontal")
        self.undo.setEnabled(bool(guides))
        self.apply.setEnabled(
            not active or (v in (0, 2) and h in (0, 2) and v + h >= 2)
        )
