#!/usr/bin/env bash
# Build a double-clickable macOS app at dist/GR-Studio.app (unsigned, for this Mac).
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [ ! -x .venv/bin/python ]; then
  echo "Run ./run.sh once first so the .venv exists." >&2
  exit 1
fi
.venv/bin/python -m pip install -q pyinstaller
mkdir -p work

# Render icon.svg onto a dark rounded square and pack it as an .icns.
QT_QPA_PLATFORM=offscreen .venv/bin/python - <<'PY'
import shutil
import subprocess
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication([])
size = 1024
image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
image.fill(Qt.GlobalColor.transparent)
painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
inset = 100  # macOS icons leave a margin around the rounded square
path = QPainterPath()
path.addRoundedRect(QRectF(inset, inset, size - 2 * inset, size - 2 * inset), 185, 185)
painter.fillPath(path, QColor("#1e1e20"))
margin = inset + 110
QSvgRenderer("icon.svg").render(painter, QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
painter.end()
iconset = Path("work/GR-Studio.iconset")
shutil.rmtree(iconset, ignore_errors=True)
iconset.mkdir(parents=True)
for px in (16, 32, 128, 256, 512):
    for scale, suffix in ((1, ""), (2, "@2x")):
        scaled = image.scaled(px * scale, px * scale, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        scaled.save(str(iconset / f"icon_{px}x{px}{suffix}.png"))
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", "work/GR-Studio.icns"], check=True)
print("icon: work/GR-Studio.icns")
PY

.venv/bin/python -m PyInstaller --noconfirm --clean --onedir --windowed \
  --name GR-Studio --paths . --distpath dist \
  --workpath work/build --specpath work \
  --icon "$PWD/work/GR-Studio.icns" \
  --osx-bundle-identifier com.ryanel1.gr-studio \
  --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick \
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets \
  --exclude-module PySide6.QtPdf --exclude-module tkinter \
  --exclude-module pytest --exclude-module setuptools launch.py
echo "Built dist/GR-Studio.app"
