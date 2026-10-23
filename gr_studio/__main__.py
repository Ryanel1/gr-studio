"""Run with python -m gr_studio [photos...]."""

import sys

from PySide6.QtWidgets import QApplication

from .theme import apply_theme
from .window import Studio


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName("GRStudio")
    app.setApplicationName("GR Studio")
    apply_theme(app)
    window = Studio()
    if len(sys.argv) > 1:
        window.add_photos(sys.argv[1:])
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
