"""Brand colours, fonts and the app's style sheet. Values come from the brand tokens."""
from pathlib import Path

from PySide6.QtGui import QFontDatabase

ASSETS = Path(__file__).resolve().parents[1] / "assets"

ORANGE = "#FF5A1F"
ORANGE_HOVER = "#FF7240"
ORANGE_PRESSED = "#E04812"
LIME = "#C6F432"
INK_950 = "#0A0B0C"
INK_900 = "#111214"
INK_850 = "#1C1D20"
INK_800 = "#2A2C30"
INK_700 = "#3A3D42"
GRAY_500 = "#6B6F76"
GRAY_400 = "#8C9097"
GRAY_300 = "#B4B7BC"
PAPER_100 = "#E6E5E1"
PAPER_50 = "#F3F2EE"

FONT = "Inter Tight"
MONO = "Cascadia Code"

_fonts_loaded = False


def load_fonts() -> None:
    global _fonts_loaded
    if not _fonts_loaded:
        QFontDatabase.addApplicationFont(str(ASSETS / "InterTight-Variable.ttf"))
        _fonts_loaded = True


STYLE_SHEET = f"""
* {{ font-family: "{FONT}", "Segoe UI"; font-size: 14px; }}
QMainWindow, QWidget#root, QFrame#settings {{ background: {INK_900}; }}
QFrame#card {{ background: {INK_850}; border-radius: 12px; }}
QLabel {{ color: {PAPER_50}; background: transparent; }}
QLabel#heading {{ color: {GRAY_400}; font-size: 13px; font-weight: 600; }}
QLabel#note, QLabel#status {{ color: {GRAY_400}; font-size: 13px; }}
QLabel#value {{ color: {GRAY_300}; font-family: "{MONO}", Consolas; font-size: 13px; }}
QLabel#liveState {{ font-size: 13px; font-weight: 600; }}
QLabel#liveRate {{ font-family: "{MONO}", Consolas; font-size: 20px; font-weight: 600; }}
QLabel#liveSize {{ color: {GRAY_300}; font-family: "{MONO}", Consolas; font-size: 12px; }}
QLabel#stageMessage {{ color: {GRAY_400}; }}
QToolTip {{ background: {INK_800}; color: {PAPER_50}; border: 1px solid {INK_700}; padding: 4px; }}

QPlainTextEdit {{
    background: {INK_800}; color: {PAPER_50}; border: 1px solid {INK_700};
    border-radius: 8px; padding: 6px; selection-background-color: {ORANGE}; selection-color: {INK_900};
}}
QPlainTextEdit:focus {{ border-color: {ORANGE}; }}

QPushButton {{ border: none; font-weight: 600; }}

QFrame#seam {{ background: {PAPER_50}; border-radius: 22px; }}
QFrame#seam QPushButton {{
    background: transparent; color: {INK_900}; border-radius: 17px; padding: 8px 18px; min-height: 18px;
}}
QFrame#seam QPushButton:hover {{ background: {PAPER_100}; }}
QFrame#seam QPushButton:disabled {{ color: {GRAY_400}; }}
QFrame#seam QPushButton#primary {{ background: {ORANGE}; }}
QFrame#seam QPushButton#primary:hover {{ background: {ORANGE_HOVER}; }}
QFrame#seam QPushButton#primary:pressed {{ background: {ORANGE_PRESSED}; }}
QFrame#seam QPushButton#primary:disabled {{ background: {PAPER_100}; }}

QWidget#engine QPushButton {{
    background: transparent; color: {INK_900}; border-radius: 13px; padding: 5px 14px;
}}
QWidget#engine QPushButton:hover {{ background: {PAPER_100}; }}
QWidget#engine QPushButton:checked {{ background: {ORANGE}; }}

QWidget#style QPushButton {{
    background: {INK_800}; color: {PAPER_50}; border-radius: 8px; padding: 7px 8px; font-size: 13px;
}}
QWidget#style QPushButton:hover {{ background: {INK_700}; }}
QWidget#style QPushButton:checked {{ background: {ORANGE}; color: {INK_900}; }}

QCheckBox {{ color: {GRAY_300}; font-size: 13px; spacing: 8px; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border-radius: 4px; background: {INK_800}; border: 1px solid {INK_700};
}}
QCheckBox::indicator:checked {{ background: {ORANGE}; border-color: {ORANGE}; }}

QSlider::groove:horizontal {{ height: 4px; background: {INK_700}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ORANGE}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {PAPER_50}; width: 14px; margin: -5px 0; border-radius: 7px; }}
"""
