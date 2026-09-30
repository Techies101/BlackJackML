"""Capture-area picker: a see-through 640 × 640 outline dragged over the game."""
from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from core import config
from ui import theme as t
from ui.widgets import Button, dashed_rect, hbox, label


def screen_scale():
    return QGuiApplication.primaryScreen().devicePixelRatio()


class RegionPicker(QWidget):
    """Drag to move, arrow keys to nudge (Shift = 10 px), Enter / Apply to use it, Esc / Cancel to keep the old one.

    Emits the new top-left corner in physical screen pixels (what dxcam / mss capture).
    """

    applied = Signal(int, int)

    def __init__(self):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.zone = config.ZONE
        self._press = None

        self.coords = label("", 13, 700, t.TEXT)
        apply_button = Button("Apply", "primary", height=28)
        apply_button.clicked.connect(self._apply)
        cancel = Button("Cancel", height=28)
        cancel.clicked.connect(self.close)
        bar = QWidget(self)
        bar.setObjectName("pickbar")
        bar.setStyleSheet(f"QWidget#pickbar {{ background: {t.CHROME}; border-bottom: 1px solid {t.SELECT}; }}")
        bar.setLayout(hbox(label("CAPTURE AREA", 11, 700, t.SELECT, spacing=0.1), self.coords, "stretch",
                           apply_button, cancel, spacing=10, margins=(10, 0, 6, 0)))
        self.bar = bar

    def open(self, left, top, zone):
        """left/top in physical pixels; zone in feed pixels."""
        scale = screen_scale()
        size = round(config.FRAME_SIZE / scale)
        self.zone = zone
        self.setFixedSize(size, size)
        self.bar.setGeometry(0, 0, size, 40)
        self.move(round(left / scale), round(top / scale))
        self._update_coords()
        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus()

    def _physical(self):
        scale = screen_scale()
        return round(self.x() * scale), round(self.y() * scale)

    def _update_coords(self):
        x, y = self._physical()
        self.coords.setText(f"x {x}, y {y}  ·  drag to move · arrows to nudge · Enter to apply")

    def _move_clamped(self, pos):
        screen = (QGuiApplication.screenAt(pos + QPoint(self.width() // 2, self.height() // 2))
                  or QGuiApplication.primaryScreen()).geometry()
        # The whole area must be on screen: dxcam can only capture inside the monitor
        x = min(max(pos.x(), screen.left()), screen.right() - self.width() + 1)
        y = min(max(pos.y(), screen.top()), screen.bottom() - self.height() + 1)
        self.move(x, y)
        self._update_coords()

    def _apply(self):
        self.applied.emit(*self._physical())
        self.close()

    # ---------- input ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._press is not None:
            self._move_clamped(event.globalPosition().toPoint() - self._press)

    def mouseReleaseEvent(self, event):
        self._press = None

    def keyPressEvent(self, event):
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0),
                 Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if event.key() in moves:
            dx, dy = moves[event.key()]
            self._move_clamped(self.pos() + QPoint(dx, dy))
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._apply()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()

    # ---------- drawing ----------

    def paintEvent(self, event):
        p = QPainter(self)
        w, h = self.width(), self.height()
        scale = w / config.FRAME_SIZE
        p.fillRect(self.rect(), QColor(56, 214, 255, 28))
        p.setPen(QPen(QColor(t.SELECT), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(1.5, 1.5, w - 3, h - 3))

        # Where the counting zone falls inside this area
        x1, y1, x2, y2 = (v * scale for v in self.zone)
        zone = QRectF(x1, y1, x2 - x1, y2 - y1)
        p.fillRect(zone, QColor(255, 255, 0, 40))
        dashed_rect(p, zone, "#FFFF00", dash=(5, 3))
        p.setPen(QColor("#FFFF00"))
        p.setFont(t.font(11, 700))
        p.drawText(QRectF(x1, y1 - 18, 200, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "counting zone")
