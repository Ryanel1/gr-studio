from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .theme import CANVAS, SECONDARY, TEXT


def pil_image(image):
    rgb = image.convert("RGB")
    return QImage(
        rgb.tobytes(), rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888
    ).copy()


class PhotoView(QWidget):
    guides_changed = Signal()

    def __init__(self):
        super().__init__()
        self.image = None
        self.guiding = False
        self.guides = []
        self.guide_kind = "vertical"
        self.guide_start = None
        self.guide_end = None
        self.setMinimumSize(360, 270)
        self.setAccessibleName("Photo preview")
        self.message = "Your next print starts here."
        self.detail = "Import from your GR IV, or open photos from a folder."

    def set_image(self, image):
        self.image = pil_image(image) if image is not None else None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(CANVAS))
        if self.image is None:
            painter.setPen(QColor(TEXT))
            font = painter.font()
            font.setPointSize(18)
            painter.setFont(font)
            painter.drawText(
                self.rect().adjusted(20, -30, -20, -30),
                Qt.AlignmentFlag.AlignCenter,
                self.message,
            )
            font.setPointSize(11)
            painter.setFont(font)
            painter.setPen(QColor(SECONDARY))
            painter.drawText(
                self.rect().adjusted(20, 35, -20, 35),
                Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                self.detail,
            )
            return
        dest = self.image_rect()
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(dest, self.image)
        if self.guiding:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            guides = list(self.guides)
            if self.guide_start is not None and self.guide_end is not None:
                guides.append((self.guide_kind, self.guide_start, self.guide_end))
            for index, (kind, start, end) in enumerate(guides):
                points = [
                    QPointF(
                        dest.x() + p[0] * dest.width(), dest.y() + p[1] * dest.height()
                    )
                    for p in (start, end)
                ]
                painter.setPen(QPen(QColor(CANVAS), 5))
                painter.drawLine(*points)
                painter.setPen(
                    QPen(
                        QColor("#ffffff"),
                        2,
                        Qt.PenStyle.SolidLine
                        if kind == "vertical"
                        else Qt.PenStyle.DashLine,
                    )
                )
                painter.drawLine(*points)
                for point in points:
                    painter.drawEllipse(point, 4, 4)
                painter.drawText(points[0] + QPointF(8, -8), str(index + 1))

    def image_rect(self):
        if self.image is None:
            return QRectF()
        box = self.rect().adjusted(26, 24, -26, -24)
        size = self.image.size().scaled(box.size(), Qt.AspectRatioMode.KeepAspectRatio)
        return QRectF(
            box.x() + (box.width() - size.width()) / 2,
            box.y() + (box.height() - size.height()) / 2,
            size.width(),
            size.height(),
        )

    def guide_point(self, position, clamp=False):
        rect = self.image_rect()
        if rect.isEmpty() or (not clamp and not rect.contains(position)):
            return None
        return (
            max(0, min(1, (position.x() - rect.x()) / rect.width())),
            max(0, min(1, (position.y() - rect.y()) / rect.height())),
        )

    def start_guides(self, image):
        self.guiding = True
        self.guides = []
        self.guide_start = self.guide_end = None
        self.set_image(image)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.guides_changed.emit()

    def stop_guides(self):
        self.guiding = False
        self.guide_start = self.guide_end = None
        self.unsetCursor()
        self.update()

    def undo_guide(self):
        if self.guides:
            self.guides.pop()
            self.guides_changed.emit()
            self.update()

    def mousePressEvent(self, event):
        if self.guiding and event.button() == Qt.MouseButton.LeftButton:
            if sum(g[0] == self.guide_kind for g in self.guides) >= 2:
                return
            self.guide_start = self.guide_point(event.position())
            self.guide_end = self.guide_start
            self.update()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.guiding and self.guide_start is not None:
            self.guide_end = self.guide_point(event.position(), True)
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            self.guiding
            and self.guide_start is not None
            and event.button() == Qt.MouseButton.LeftButton
        ):
            end = self.guide_point(event.position(), True)
            if (
                end is not None
                and sum((a - b) ** 2 for a, b in zip(self.guide_start, end)) > 0.01
            ):
                self.guides.append((self.guide_kind, self.guide_start, end))
            self.guide_start = self.guide_end = None
            self.guides_changed.emit()
            self.update()
        else:
            super().mouseReleaseEvent(event)


class Adjustment(QWidget):
    changed = Signal(float)

    def __init__(self, title, minimum, maximum, scale=1, decimals=0):
        super().__init__()
        self.scale = scale
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 6)
        layout.setSpacing(2)
        row = QHBoxLayout()
        label = QLabel(title)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setDecimals(decimals)
        self.spin.setSingleStep(1 / scale)
        self.spin.setFixedWidth(64)
        self.spin.setObjectName("adjustmentValue")
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.spin.setAccessibleName(title)
        row.addWidget(label)
        row.addStretch()
        row.addWidget(self.spin)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimumHeight(22)
        self.slider.setRange(int(minimum * scale), int(maximum * scale))
        self.slider.setAccessibleName(title)
        layout.addLayout(row)
        layout.addWidget(self.slider)
        self.slider.valueChanged.connect(self._slide)
        self.spin.valueChanged.connect(self._spin)

    def _slide(self, value):
        self.spin.blockSignals(True)
        self.spin.setValue(value / self.scale)
        self.spin.blockSignals(False)
        self.changed.emit(value / self.scale)

    def _spin(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(round(value * self.scale))
        self.slider.blockSignals(False)
        self.changed.emit(value)

    def set_value(self, value):
        self.spin.blockSignals(True)
        self.slider.blockSignals(True)
        self.spin.setValue(value)
        self.slider.setValue(round(value * self.scale))
        self.spin.blockSignals(False)
        self.slider.blockSignals(False)


class Section(QWidget):
    """Native disclosure shared by the three inspector pages."""

    def __init__(self, title, expanded=True):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.toggle = QToolButton()
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setText(title)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.body = QWidget()
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(0, 4, 0, 18)
        self.content.setSpacing(10)
        layout.addWidget(self.toggle)
        layout.addWidget(self.body)
        self.toggle.toggled.connect(self.set_expanded)
        self.set_expanded(expanded)

    def set_expanded(self, expanded):
        self.body.setVisible(expanded)
        self.toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.toggle.setAccessibleName(
            f"{self.toggle.text()}, {'expanded' if expanded else 'collapsed'}"
        )


class Histogram(QWidget):
    """Luminance distribution from a bounded image, with no polling or dependency."""

    def __init__(self):
        super().__init__()
        self.bins = []
        self.setFixedHeight(64)
        self.setAccessibleName("Source photo luminance histogram")
        self.setToolTip(
            "Source luminance: shadows on the left, highlights on the right"
        )

    def set_image(self, image):
        if image is None:
            self.bins = []
        else:
            sample = image.copy()
            sample.thumbnail((256, 256))
            values = sample.convert("L").histogram()
            self.bins = [sum(values[i : i + 4]) for i in range(0, 256, 4)]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#414143"), 1))
        bottom = self.height() - 5
        painter.drawLine(0, bottom, self.width(), bottom)
        if not self.bins or not max(self.bins):
            return
        peak = max(self.bins)
        path = QPainterPath(QPointF(0, bottom))
        for i, value in enumerate(self.bins):
            path.lineTo(i * self.width() / 63, bottom - value / peak * (bottom - 8))
        path.lineTo(self.width(), bottom)
        path.closeSubpath()
        painter.fillPath(path, QColor("#88888a"))
