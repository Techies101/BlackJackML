"""Reusable widgets styled after the Claude Design components."""
from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDoubleValidator, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import theme as t


def label(text="", size=13, weight=400, color=t.TEXT, family=t.UI, spacing=0.0):
    w = QLabel(text)
    w.setFont(t.font(size, weight, family, spacing))
    w.setStyleSheet(f"color: {color}; background: transparent;")
    return w


def section_label(text, color=t.TEXT_2):
    return label(text, 11, 600, color, spacing=0.1)


def set_color(widget, color):
    widget.setStyleSheet(f"color: {color}; background: transparent;")


def hbox(*items, spacing=6, margins=(0, 0, 0, 0)):
    layout = QHBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    for item in items:
        if item == "stretch":
            layout.addStretch(1)
        elif isinstance(item, QWidget):
            layout.addWidget(item)
        else:
            layout.addLayout(item)
    return layout


def vbox(*items, spacing=6, margins=(0, 0, 0, 0)):
    layout = QVBoxLayout()
    layout.setSpacing(spacing)
    layout.setContentsMargins(*margins)
    for item in items:
        if item == "stretch":
            layout.addStretch(1)
        elif isinstance(item, QWidget):
            layout.addWidget(item)
        else:
            layout.addLayout(item)
    return layout


class Panel(QFrame):
    """Card surface: panel fill, 1 px line border, radius 6."""

    def __init__(self, border=t.LINE, background=t.PANEL, radius=6, border_width=1):
        super().__init__()
        self.setObjectName("panel")
        self.set_border(border, border_width, background, radius)

    def set_border(self, color, width=1, background=t.PANEL, radius=6):
        self.setStyleSheet(
            f"QFrame#panel {{ background: {background}; border: {width}px solid {color}; border-radius: {radius}px; }}"
        )


class Button(QPushButton):
    """Primary / secondary / destructive / custom-colour buttons (32 px high, radius 4)."""

    def __init__(self, text, kind="secondary", height=32, width=None, size=13, family=t.UI, color=None):
        super().__init__(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(height)
        if width:
            self.setFixedWidth(width)
        self._padding = 0 if width and width < 50 else 12   # narrow buttons (−1, +1, −, +) need the room
        self.setFont(t.font(size, 700 if kind != "secondary" else 600, family))
        self.set_kind(kind, color)

    def set_kind(self, kind, color=None):
        if kind == "primary":
            css = f"background: {t.PLUS}; color: {t.WINDOW}; border: 1px solid {t.PLUS};"
            hover = "background: #7DFFB3;"
        elif kind == "destructive":
            css = f"background: {t.RAISED}; color: {t.MINUS}; border: 1px solid {t.MINUS};"
            hover = f"border-color: {t.MINUS};"
        elif kind == "outline":
            css = f"background: transparent; color: {color}; border: 1px solid {color};"
            hover = f"background: {t.PLUS_DARK};"
        else:
            css = f"background: {t.RAISED}; color: {color or t.TEXT}; border: 1px solid {t.LINE_STRONG};"
            hover = f"border-color: {color or t.TEXT_2};"
        self.setStyleSheet(
            f"QPushButton {{ {css} border-radius: 4px; padding: 0 {self._padding}px; }}"
            f"QPushButton:hover {{ {hover} }}"
            f"QPushButton:disabled {{ background: {t.RAISED}; color: {t.TEXT_3}; border-color: {t.LINE}; }}"
        )


class ChoiceButton(QPushButton):
    """Card / value button: idle raised, hover cyan border, selected solid cyan with ink text."""

    def __init__(self, text, height=34, size=19):
        super().__init__(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFont(t.font(size, 700, t.CONDENSED))
        self.setStyleSheet(
            f"QPushButton {{ background: {t.RAISED}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px; }}"
            f"QPushButton:hover {{ border-color: {t.SELECT}; }}"
            f"QPushButton:checked {{ background: {t.SELECT}; color: {t.WINDOW}; border-color: {t.SELECT}; }}"
        )


class ChoiceGrid(QWidget):
    """Grid of ChoiceButtons where at most one is selected."""

    changed = Signal(object)

    def __init__(self, columns=7, height=34, size=19):
        super().__init__()
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(4)
        self._columns, self._height, self._size = columns, height, size
        self._buttons = {}

    def set_options(self, options, columns=None):
        """options: list of (value, label)."""
        for button in self._buttons.values():
            button.deleteLater()
        self._buttons = {}
        columns = columns or self._columns

        for c in range(max(self._grid.columnCount(), columns)):
            self._grid.setColumnStretch(c, 1 if c < columns else 0)

        for i, (value, text) in enumerate(options):
            button = ChoiceButton(text, self._height, self._size)
            button.clicked.connect(lambda _=False, v=value: self._clicked(v))
            self._grid.addWidget(button, i // columns, i % columns)
            self._buttons[value] = button

    def _clicked(self, value):
        self.select(value)
        self.changed.emit(value)

    def select(self, value):
        for v, button in self._buttons.items():
            button.setChecked(v == value)


class Segmented(QFrame):
    """Segmented control (Hard · Soft · Pair, Career · Trip)."""

    changed = Signal(str)

    def __init__(self, options, height=28, size=13, active_bg=t.SELECT):
        super().__init__()
        self.setObjectName("seg")
        self.setFixedHeight(height)
        self.setStyleSheet(f"QFrame#seg {{ border: 1px solid {t.LINE_STRONG}; border-radius: 4px; background: {t.RAISED}; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self._buttons = {}

        for key, text in options:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFont(t.font(size, 600))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            button.setStyleSheet(
                f"QPushButton {{ background: {t.RAISED}; color: {t.TEXT_BODY}; border: none; border-radius: 0; }}"
                f"QPushButton:checked {{ background: {active_bg}; color: {t.WINDOW}; }}"
            )
            button.clicked.connect(lambda _=False, k=key: self._clicked(k))
            layout.addWidget(button)
            self._buttons[key] = button

    def _clicked(self, key):
        self.select(key)
        self.changed.emit(key)

    def select(self, key):
        for k, button in self._buttons.items():
            button.setChecked(k == key)


class Toggle(QWidget):
    """Switch (38 × 22, or 30 × 16 small): on = neon green with ink knob, off = line with muted knob."""

    toggled = Signal(bool)

    def __init__(self, on=False, small=False):
        super().__init__()
        self.setFixedSize(*((30, 16) if small else (38, 22)))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._on = on

    def is_on(self):
        return self._on

    def set_on(self, on):
        self._on = on
        self.update()

    def mousePressEvent(self, event):
        self._on = not self._on
        self.update()
        self.toggled.emit(self._on)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()
        pad = 2 if h < 20 else 3
        knob = h - 2 * pad
        p.setBrush(QColor(t.PLUS if self._on else t.LINE))
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        p.setBrush(QColor(t.WINDOW if self._on else t.TEXT_3))
        p.drawEllipse(QRectF(w - pad - knob if self._on else pad, pad, knob, knob))


class NumberField(QFrame):
    """Input box with an optional "$" prefix and a units suffix; emits the parsed number."""

    valueChanged = Signal(float)

    def __init__(self, value=0, prefix="", suffix="", height=34, size=14, decimals=0):
        super().__init__()
        self.setObjectName("field")
        self.setFixedHeight(height)
        self._decimals = decimals
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 8, 0)
        layout.setSpacing(4)

        if prefix:
            layout.addWidget(label(prefix, 13, 400, t.TEXT_3))

        self.edit = QLineEdit()
        self.edit.setProperty("bare", True)
        self.edit.setFont(t.font(size, 400, t.MONO))
        self.edit.setValidator(QDoubleValidator(-1e9, 1e9, decimals))
        self.edit.editingFinished.connect(self._emit)
        layout.addWidget(self.edit, 1)

        self.suffix = label(suffix, 11, 400, t.TEXT_3)
        layout.addWidget(self.suffix)
        self.suffix.setVisible(bool(suffix))
        self._set_style(True)
        self.set_value(value)

    def _set_style(self, enabled):
        self.setStyleSheet(
            f"QFrame#field {{ background: {t.INPUT}; border: 1px solid {t.LINE}; border-radius: 4px; }}"
            f"QLineEdit {{ background: transparent; border: none; padding: 0; color: {t.TEXT if enabled else t.TEXT_3}; }}"
        )

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self._set_style(enabled)

    def value(self):
        try:
            return float(self.edit.text().replace(",", ""))
        except ValueError:
            return 0.0

    def set_value(self, value):
        text = f"{value:.{self._decimals}f}" if self._decimals else f"{int(round(value))}"
        if self.edit.text() != text:
            self.edit.setText(text)

    def set_suffix(self, text):
        self.suffix.setText(text)

    def _emit(self):
        self.valueChanged.emit(self.value())


def combo(options, value, width=None, height=30, size=14):
    box = QComboBox()
    box.setFont(t.font(size))
    box.addItems(options)
    if value in options:
        box.setCurrentText(value)
    box.setFixedHeight(height)
    if width:
        box.setFixedWidth(width)
    box.setCursor(Qt.CursorShape.PointingHandCursor)
    return box


class Badge(QLabel):
    """Small caps badge: filled or outlined."""

    def __init__(self, text="", fg=t.TEXT_BODY, bg="transparent", border=t.TEXT_3, height=20, size=11, spacing=0.1):
        super().__init__(text)
        self.setFixedHeight(height)
        self.setFont(t.font(size, 700, spacing=spacing))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_style(fg, bg, border)

    def set_style(self, fg, bg, border):
        self.setStyleSheet(f"color: {fg}; background: {bg}; border: 1px solid {border}; border-radius: 3px; padding: 0 7px;")


class Dot(QWidget):
    def __init__(self, color, size=7, square=False):
        super().__init__()
        self.setFixedSize(size, size)
        self._color, self._square = QColor(color), square

    def set_color(self, color, square=None):
        self._color = QColor(color)
        if square is not None:
            self._square = square
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color)
        r = QRectF(0, 0, self.width(), self.height())
        p.drawRoundedRect(r, 1, 1) if self._square else p.drawEllipse(r)


class Pill(QFrame):
    """LIVE / STOPPED status pill."""

    def __init__(self):
        super().__init__()
        self.setObjectName("pill")
        self.setFixedHeight(22)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(6)
        self.dot = Dot(t.TEXT_3)
        self.text = label("", 11, 700, t.TEXT_3, spacing=0.08)
        layout.addWidget(self.dot)
        layout.addWidget(self.text)

    def set_state(self, text, fg, border):
        self.text.setText(text)
        set_color(self.text, fg)
        self.dot.set_color(fg)
        self.setStyleSheet(f"QFrame#pill {{ border: 1px solid {border}; border-radius: 11px; background: transparent; }}")


class TitleBar(QFrame):
    """Custom title bar for the frameless, always-on-top windows (drag to move)."""

    def __init__(self, window, title, subtitle="", height=32, show_on_top=True, button_width=46):
        super().__init__()
        self._window = window
        self.setObjectName("titlebar")
        self.setFixedHeight(height)
        self.setStyleSheet(f"QFrame#titlebar {{ background: {t.CHROME}; border-bottom: 1px solid {t.LINE_SOFT}; }}")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12 if height > 28 else 10, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(label(title, 13 if height > 28 else 12, 700, spacing=0.02))
        if subtitle:
            layout.addWidget(label(subtitle, 12, 400, t.TEXT_3))
        layout.addStretch(1)
        if show_on_top:
            on_top = label("ALWAYS ON TOP", 11, 400, t.TEXT_3, spacing=0.06)
            on_top.setContentsMargins(0, 0, 12, 0)
            layout.addWidget(on_top)

        for glyph, action, hover in (("–", window.showMinimized, t.LINE), ("✕", window.close, "#C42B1C")):
            button = QPushButton(glyph)
            button.setFixedSize(button_width, height)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFont(t.font(13 if height > 28 else 12))
            button.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {t.TEXT_2}; border: none; }}"
                f"QPushButton:hover {{ background: {hover}; color: #FFFFFF; }}"
            )
            button.clicked.connect(action)
            layout.addWidget(button)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._window.windowHandle():
            self._window.windowHandle().startSystemMove()


def keep_on_screen(window, grip=160):
    """Pull a frameless window back so its title bar is reachable.

    The title bar is the only drag handle, so it must stay below the top edge and at
    least `grip` px of the window must stay on screen horizontally. Running off the
    right edge is allowed (the main window is meant to sit partly off-screen).
    """
    geo = window.frameGeometry()
    screen = (QGuiApplication.screenAt(geo.center()) or QGuiApplication.screenAt(geo.topLeft())
              or QGuiApplication.primaryScreen())
    area = screen.availableGeometry()
    x = min(max(geo.x(), area.left() - geo.width() + grip), area.right() - grip)
    y = min(max(geo.y(), area.top()), area.bottom() - 60)
    if (x, y) != (geo.x(), geo.y()):
        window.move(x, y)


def install_screen_guard(window):
    """Re-check the position shortly after the user stops dragging (Windows owns the drag itself)."""
    timer = QTimer(window, singleShot=True, interval=300)
    timer.timeout.connect(lambda: keep_on_screen(window))
    return timer


def dashed_rect(painter, rect, color, dash=(4, 3)):
    pen = QPen(QColor(color))
    pen.setDashPattern(list(dash))
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(rect)


__all__ = [
    "label", "section_label", "set_color", "hbox", "vbox", "Panel", "Button", "ChoiceButton", "ChoiceGrid",
    "Segmented", "Toggle", "NumberField", "combo", "Badge", "Dot", "Pill", "TitleBar", "dashed_rect",
    "keep_on_screen", "install_screen_guard",
]
