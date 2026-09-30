"""Program Logs window: small, always on top, resizable, level filters, auto-scroll and Clear."""
import html

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QStackedLayout, QTextEdit, QVBoxLayout, QWidget

from ui import theme as t
from ui.widgets import Toggle, TitleBar, hbox, install_screen_guard, label

LEVEL_COLOR = {"SYSTEM": t.SELECT, "DECISION": t.PLUS, "WARNING": t.WARNING, "ERROR": t.MINUS}
MAX_LINES = 2000
DEFAULT_SIZE = (520, 260)
MIN_SIZE = (380, 140)


class ResizeGrip(QWidget):
    """Bottom-right corner grip: asks the OS to resize the frameless window (dotted, like a native grip)."""

    def __init__(self, window):
        super().__init__(window)
        self._window = window
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("Drag to resize")

    def mousePressEvent(self, event):
        handle = self._window.windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle:
            handle.startSystemResize(Qt.Edge.RightEdge | Qt.Edge.BottomEdge)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.TEXT_3))
        for x, y in ((11, 11), (7, 11), (11, 7), (3, 11), (7, 7), (11, 3)):
            p.drawRect(QRectF(x, y, 2, 2))


class LogsWindow(QWidget):

    def __init__(self):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setWindowTitle("Program Logs")
        self.setMinimumSize(*MIN_SIZE)
        self.resize(*DEFAULT_SIZE)
        self.entries = []
        self.hidden = set()

        frame = QFrame(self)
        frame.setObjectName("logframe")
        frame.setStyleSheet(f"QFrame#logframe {{ background: {t.WINDOW}; border: 1px solid {t.LINE_STRONG}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        root = QVBoxLayout(frame)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)
        root.addWidget(TitleBar(self, "Program Logs", height=28, show_on_top=False, button_width=40))

        # Filters · auto-scroll · clear
        bar = QFrame()
        bar.setObjectName("logbar")
        bar.setFixedHeight(30)
        bar.setStyleSheet(f"QFrame#logbar {{ border-bottom: 1px solid {t.LINE_SOFT}; }}")
        items = []
        self.filters = {}
        for level in LEVEL_COLOR:
            chip = QPushButton(level)
            chip.setFixedHeight(18)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFont(t.font(10, 700, t.MONO))
            chip.clicked.connect(lambda _=False, lv=level: self._toggle_level(lv))
            self.filters[level] = chip
            items.append(chip)
        self.auto = Toggle(True, small=True)
        clear = QPushButton("Clear")
        clear.setFixedHeight(20)
        clear.setCursor(Qt.CursorShape.PointingHandCursor)
        clear.setFont(t.font(11, 600))
        clear.setStyleSheet(
            f"QPushButton {{ color: {t.TEXT_BODY}; border: 1px solid {t.LINE_STRONG}; border-radius: 3px; padding: 0 8px; background: transparent; }}"
            f"QPushButton:hover {{ border-color: {t.TEXT_2}; }}"
        )
        clear.clicked.connect(self.clear)
        bar.setLayout(hbox(*items, "stretch", label("Auto-scroll", 11, 400, t.TEXT_2), self.auto, clear,
                           spacing=8, margins=(10, 0, 10, 0)))
        root.addWidget(bar)
        self._style_filters()

        # Log text
        holder = QWidget()
        stack = QStackedLayout(holder)
        stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.text.setFont(t.font(11, 400, t.MONO))
        self.text.setStyleSheet(f"QTextEdit {{ background: {t.WINDOW}; border: none; padding: 6px 10px; color: {t.TEXT_BODY}; }}")
        self.empty = QLabel("Log cleared · new lines appear here")
        self.empty.setFont(t.font(12))
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet(f"color: {t.TEXT_3}; background: transparent;")
        self.empty.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        stack.addWidget(self.text)
        stack.addWidget(self.empty)
        root.addWidget(holder, 1)

        # Frameless windows have no resize border: drag this corner grip to resize
        self.grip = ResizeGrip(self)
        self._render()
        self._screen_guard = install_screen_guard(self)

    def moveEvent(self, event):
        self._screen_guard.start()

    def resizeEvent(self, event):
        self.grip.move(self.width() - self.grip.width(), self.height() - self.grip.height())
        self.grip.raise_()

    def _style_filters(self):
        for level, chip in self.filters.items():
            off = level in self.hidden
            color = t.TEXT_3 if off else LEVEL_COLOR[level]
            chip.setStyleSheet(
                f"QPushButton {{ color: {color}; border: 1px solid {t.LINE if off else color}; border-radius: 3px;"
                f" padding: 0 6px; background: transparent; }}"
            )

    def _toggle_level(self, level):
        self.hidden ^= {level}
        self._style_filters()
        self._render()

    @staticmethod
    def _line(stamp, level, message):
        color = LEVEL_COLOR.get(level, t.TEXT_BODY)
        text_color = t.WARNING_TEXT if level == "WARNING" else t.TEXT_BODY
        tag = html.escape(f"[{level}]").ljust(10).replace(" ", "&nbsp;")
        return (f'<span style="color:{t.TEXT_3}">{stamp}</span>&nbsp;&nbsp;'
                f'<span style="color:{color};font-weight:700">{tag}</span>&nbsp;'
                f'<span style="color:{text_color}">{html.escape(message)}</span>')

    def _render(self):
        lines = [self._line(*e) for e in self.entries if e[1] not in self.hidden]
        self.text.clear()
        for line in lines:          # same path as live lines, so spacing is identical
            self.text.append(line)
        self.empty.setVisible(not lines)
        self._scroll()

    def _scroll(self):
        if self.auto.is_on():
            bar = self.text.verticalScrollBar()
            bar.setValue(bar.maximum())

    def append(self, stamp, level, message):
        self.entries.append((stamp, level, message))
        if len(self.entries) > MAX_LINES:
            self.entries = self.entries[-MAX_LINES:]
            self._render()
            return
        if level not in self.hidden:
            self.text.append(self._line(stamp, level, message))
            self.empty.hide()
            self._scroll()

    def clear(self):
        self.entries = []
        self._render()
