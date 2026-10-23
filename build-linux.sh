#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
.venv/bin/python -m pip install pyinstaller
.venv/bin/python -m PyInstaller --noconfirm --clean --onedir --windowed \
  --name GR-Studio --paths . --distpath dist \
  --workpath work/build --specpath work \
  --exclude-module PySide6.QtQml --exclude-module PySide6.QtQuick \
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets \
  --exclude-module PySide6.QtPdf --exclude-module tkinter \
  --exclude-module pytest --exclude-module setuptools launch.py
