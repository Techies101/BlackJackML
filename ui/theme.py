"""Dark + neon theme from the Claude Design style sheet: colour tokens, fonts and base QSS."""
import glob
import os

from PySide6.QtGui import QFont, QFontDatabase

# Surfaces & text
WINDOW = "#07090C"
CHROME = "#0B0E13"
PANEL = "#0E1117"
RAISED = "#151A22"
INPUT = "#0A0D12"
LINE = "#232A35"
LINE_STRONG = "#323B49"
LINE_SOFT = "#1A2029"
TEXT = "#E8ECF2"
TEXT_BODY = "#C3CBD8"
TEXT_2 = "#9AA4B5"
TEXT_3 = "#5F6979"

# Neon, one meaning each
PLUS = "#3DFF8F"        # positive count, bet-up, live capture, primary action, good EV
MINUS = "#FF4D6D"       # negative count/index, stop, destructive, ±2 SD, error
DEVIATION = "#FF3DD0"   # deviation badge, advice outline, chart indices
WARNING = "#FFB224"     # near cut card, overlap banner, WARNING logs
SELECT = "#38D6FF"      # selected buttons & tabs, live TC row, SYSTEM logs
STAND = "#FFE24A"       # stand cells & STAND action; ±1 SD line

WARNING_TEXT = "#FFD68A"
WARNING_BG = "#2B1E05"
SELECT_DARK = "#0E2A36"
PLUS_DARK = "#0E3A25"
PLUS_BORDER = "#1D6B45"

# Strategy cells: (background, text)
CELL_GREEN = ("#0E3A25", "#5CFFA3")   # split / double / surrender
CELL_TEAL = ("#0B3533", "#3DF2D6")    # Ds / split if DAS
CELL_YELLOW = ("#3A3310", "#FFE24A")  # stand
CELL_NEUTRAL = ("#171C24", "#C3CBD8")  # hit / no split
CELL_EMPTY = ("#0E1117", "#5F6979")

CELL_STYLE = {
    "Y": CELL_GREEN, "D": CELL_GREEN, "SUR": CELL_GREEN,
    "Y/N": CELL_TEAL, "Ds": CELL_TEAL,
    "S": CELL_YELLOW,
    "H": CELL_NEUTRAL, "N": CELL_NEUTRAL,
    "-": CELL_EMPTY,
}

ACTION_COLOR = {
    "Y": "#5CFFA3", "Y/N": "#3DF2D6", "D": "#5CFFA3", "Ds": "#3DF2D6",
    "S": STAND, "H": TEXT, "SUR": "#5CFFA3", "N": TEXT,
}

UI = "Barlow"
CONDENSED = "Barlow Condensed"
MONO = "JetBrains Mono"


def load_fonts():
    folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    for path in glob.glob(os.path.join(folder, "*.ttf")):
        QFontDatabase.addApplicationFont(path)


def font(size, weight=400, family=UI, spacing=0.0):
    """Font by pixel size and CSS weight; `spacing` is letter spacing in em (0.1 = +10%)."""
    f = QFont(family)
    f.setPixelSize(size)
    f.setWeight(QFont.Weight(weight))
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + spacing * 100)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def count_color(n):
    return PLUS if n > 0 else MINUS if n < 0 else TEXT


def signed(n):
    return f"+{n}" if n > 0 else f"−{abs(n)}" if n < 0 else "0"


def money(n, decimals=0):
    return f"${n:,.{decimals}f}"


STYLESHEET = f"""
QWidget {{ color: {TEXT}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {LINE_STRONG}; padding: 4px; }}

QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {INPUT}; border: 1px solid {LINE}; border-radius: 4px; color: {TEXT};
    padding: 0 6px; selection-background-color: {SELECT}; selection-color: {WINDOW};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {SELECT}; }}
QLineEdit:disabled {{ color: {TEXT_3}; }}
QLineEdit[bare="true"] {{ background: transparent; border: none; padding: 0; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{
    width: 12px; background: {RAISED}; border: none;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ width: 6px; height: 6px; }}

QComboBox {{
    background: {INPUT}; border: 1px solid {LINE}; border-radius: 4px; color: {TEXT};
    padding: 0 8px; min-height: 28px;
}}
QComboBox:focus, QComboBox:on {{ border-color: {SELECT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; width: 0; }}
QComboBox QAbstractItemView {{
    background: {RAISED}; border: 1px solid {LINE_STRONG}; color: {TEXT};
    selection-background-color: {SELECT}; selection-color: {WINDOW}; outline: none;
}}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: {CHROME}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #2A323E; border-radius: 4px; min-height: 30px; margin: 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QScrollBar:horizontal {{ height: 0; }}
"""
