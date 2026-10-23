"""Archive's native monochrome surfaces, matched to Chrome City / Monochrome."""

CANVAS = "#141416"
PANEL = "#1e1e20"
TEXT = "#dadadc"
SECONDARY = "#aaaaac"

STYLE = """
QWidget { background: #1e1e20; color: #dadadc; font-size: 13px; }
QMainWindow, QDialog { background: #1e1e20; }
QWidget#canvas { background: #141416; }
QWidget#toolbar { border-bottom: 1px solid #363638; }
QWidget#exportFooter { border-top: 1px solid #363638; }
QLabel { background: transparent; }
QLabel#title { font-size: 21px; font-weight: 500; }
QLabel#brand { font-size: 22px; font-weight: 600; }
QLabel#section { font-size: 13px; font-weight: 600; margin-top: 12px; }
QLabel#muted { color: #aaaaac; }
QLabel#status { color: #aaaaac; padding: 6px 24px; border-top: 1px solid #363638; }
QPushButton, QToolButton { background: #2a2a2c; border: 1px solid #414143; border-radius: 5px; padding: 9px 14px; }
QPushButton:hover, QToolButton:hover { background: #353537; border-color: #6e6e70; }
QPushButton:pressed, QToolButton:pressed { background: #414143; }
QPushButton:focus, QToolButton:focus, QComboBox:focus, QLineEdit:focus, QDoubleSpinBox:focus { border: 1px solid #dadadc; }
QPushButton:disabled, QToolButton:disabled { background: #242426; color: #777779; border-color: #303032; }
QPushButton#primary { background: #dadadc; color: #1e1e20; font-weight: 600; border-color: #dadadc; }
QPushButton#primary:hover { background: #eeeeef; }
QPushButton#primary:disabled { background: #39393b; color: #808082; border-color: #39393b; }
QPushButton#quiet, QToolButton#menuButton { background: transparent; border-color: transparent; color: #aaaaac; }
QPushButton#quiet:hover, QToolButton#menuButton:hover { background: #2a2a2c; color: #dadadc; }
QPushButton#quiet:focus, QToolButton#menuButton:focus { border-color: #dadadc; }
QToolButton#menuButton::menu-indicator { image: none; }
QToolButton#sectionToggle { text-align: left; background: transparent; border: none; border-top: 1px solid #363638; border-radius: 0; padding: 17px 0; font-weight: 500; }
QToolButton#sectionToggle:hover { background: #272729; }
QToolButton#sectionToggle:focus { border: 1px solid #dadadc; }
QLineEdit, QComboBox, QDoubleSpinBox { background: #262628; border: 1px solid #414143; border-radius: 4px; padding: 8px; min-height: 20px; selection-background-color: #727274; selection-color: #ffffff; }
QDoubleSpinBox#adjustmentValue { background: transparent; border-color: transparent; color: #aaaaac; padding: 2px 4px; min-height: 20px; }
QDoubleSpinBox#adjustmentValue:hover { background: #262628; border-color: #414143; }
QDoubleSpinBox#adjustmentValue:focus { background: #262628; border-color: #dadadc; color: #dadadc; }
QComboBox { padding-right: 26px; }
QComboBox QAbstractItemView { background: #262628; border: 1px solid #505052; selection-background-color: #414143; selection-color: #eeeeef; padding: 6px; }
QSlider::groove:horizontal { background: #414143; height: 3px; border-radius: 1px; }
QSlider::sub-page:horizontal { background: #777779; }
QSlider::handle:horizontal { background: #dadadc; border: 1px solid #dadadc; width: 10px; margin: -4px 0; border-radius: 5px; }
QSlider:focus { border: 1px solid #aaaaac; }
QListWidget, QTableWidget { background: #1e1e20; border: none; outline: none; }
QListWidget#filmstrip { border-top: 1px solid #363638; padding: 10px 18px; }
QListWidget::item { padding: 6px; border: 1px solid transparent; border-radius: 4px; }
QListWidget::item:selected { background: #39393b; border: 1px solid #dadadc; }
QListWidget::item:hover { background: #2a2a2c; }
QTableWidget { alternate-background-color: #232325; }
QTableWidget::item { padding: 12px; border-bottom: 1px solid #303032; }
QTableWidget::item:selected { background: #39393b; }
QTableWidget::indicator { width: 16px; height: 16px; }
QTableWidget::indicator:unchecked { background: #262628; border: 1px solid #88888a; border-radius: 2px; }
QHeaderView::section { background: #1e1e20; color: #aaaaac; padding: 12px; border: none; border-bottom: 1px solid #414143; }
QScrollArea { border: none; }
QScrollBar:vertical { background: #1e1e20; width: 8px; }
QScrollBar::handle:vertical { background: #505052; min-height: 30px; border-radius: 4px; }
QScrollBar:horizontal { background: #1e1e20; height: 8px; }
QScrollBar::handle:horizontal { background: #505052; min-width: 30px; border-radius: 4px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0px; height: 0px; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QSplitter::handle { background: #363638; width: 1px; }
QProgressBar { border: 1px solid #414143; border-radius: 4px; text-align: center; min-height: 20px; }
QProgressBar::chunk { background: #727274; }
QTabWidget::pane { border: none; }
QTabBar::tab { padding: 14px 16px; color: #aaaaac; background: #1e1e20; border-bottom: 2px solid #363638; }
QTabBar::tab:selected { color: #eeeeef; border-bottom: 2px solid #dadadc; }
QTabBar::tab:hover { background: #2a2a2c; }
QMenu { background: #262628; border: 1px solid #505052; padding: 6px; }
QMenu::item { padding: 10px 30px 10px 14px; border-radius: 3px; }
QMenu::item:selected { background: #414143; }
QMenu::item:disabled { color: #777779; }
QMenu::separator { height: 1px; background: #414143; margin: 6px 10px; }
QToolTip { background: #262628; color: #dadadc; border: 1px solid #6e6e70; padding: 6px; }
"""


def apply_theme(app):
    """Style native controls too, without changing the user's desktop settings."""
    from PySide6.QtGui import QColor, QFont, QPalette

    app.setStyle("Fusion")
    app.setFont(QFont("sans-serif", 10))
    palette = QPalette()
    for role, color in {
        QPalette.ColorRole.Window: PANEL,
        QPalette.ColorRole.WindowText: TEXT,
        QPalette.ColorRole.Base: PANEL,
        QPalette.ColorRole.AlternateBase: "#232325",
        QPalette.ColorRole.Text: TEXT,
        QPalette.ColorRole.Button: "#2a2a2c",
        QPalette.ColorRole.ButtonText: TEXT,
        QPalette.ColorRole.Highlight: "#727274",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.ToolTipBase: "#262628",
        QPalette.ColorRole.ToolTipText: TEXT,
    }.items():
        palette.setColor(role, QColor(color))
    for role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor("#777779"))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)


# Spinboxes contain a QLineEdit: avoid applying the standalone field padding twice.
STYLE += """
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; height: 0; }
QDoubleSpinBox QLineEdit { background: transparent; border: none; padding: 0; min-height: 0; }
"""
