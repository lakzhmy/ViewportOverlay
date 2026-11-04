"""Brand colours, fonts and the app's style sheet. Values come from the brand tokens."""
from pathlib import Path

from PySide6.QtGui import QFontDatabase

ASSETS = Path(__file__).resolve().parents[1] / "assets"

ORANGE = "#FF5A1F"
LIME = "#C6F432"
INK_950 = "#0A0B0C"
INK_900 = "#111214"
INK_800 = "#2A2C30"
INK_700 = "#3A3D42"
STONE = "#524E48"
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
QMainWindow, QWidget#root {{ background: {PAPER_50}; }}
QLabel {{ color: {GRAY_500}; background: transparent; font-size: 13px; }}
QLabel#stageTitle {{ color: {PAPER_50}; font-size: 24px; font-weight: 600; }}
QLabel#stageHint {{ color: {PAPER_100}; font-size: 14px; }}
QLabel#amount {{
    background: {INK_900}; color: {PAPER_50}; border-radius: 8px; padding: 4px 9px;
    font-family: "{MONO}", Consolas; font-size: 12px;
}}
QToolTip {{ background: {INK_800}; color: {PAPER_50}; border: 1px solid {INK_700}; padding: 4px; }}

QFrame#panel {{ background: {PAPER_50}; border-radius: 12px; }}
QPlainTextEdit {{
    background: transparent; color: {INK_900}; border: none; border-bottom: 1px solid {GRAY_300};
    font-size: 15px; selection-background-color: {ORANGE}; selection-color: {INK_900};
}}
QPlainTextEdit:focus {{ border-bottom-color: {ORANGE}; }}
QPlainTextEdit:disabled {{ color: {GRAY_400}; }}
"""
