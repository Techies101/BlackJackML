"""Burn popup: face-down burns (quantity only) and face-up burns (ranks, counted)."""
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QPushButton, QSpinBox, QWidget

from core.logbus import log
from core.strategy import UPCARDS
from ui import theme as t
from ui.widgets import Button, hbox, label, section_label, vbox
from utilities.rank_verifier import HILO_VALUE

WIDTH = 372


class BurnPopup(QFrame):

    changed = Signal()

    def __init__(self, counter):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.counter = counter
        self.setObjectName("burn")
        self.setFixedWidth(WIDTH)
        self.setStyleSheet(f"QFrame#burn {{ background: {t.PANEL}; border: 1px solid {t.SELECT}; border-radius: 6px; }}")
        root = vbox(spacing=10, margins=(14, 12, 14, 12))
        self.setLayout(root)

        self.total = label("", 12, 400, t.TEXT_2)
        root.addLayout(hbox(section_label("BURNED CARDS"), "stretch", self.total))

        # Face-down: quantity only
        self.down = QSpinBox()
        self.down.setRange(0, 416)
        self.down.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.down.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.down.setFixedSize(52, 30)
        self.down.setFont(t.font(14, 400, t.MONO))
        self.down.valueChanged.connect(self._down_changed)
        minus = Button("−", width=30, height=30, size=17, family=t.CONDENSED)
        minus.clicked.connect(lambda: self.down.setValue(self.down.value() - 1))
        plus = Button("+", width=30, height=30, size=17, family=t.CONDENSED)
        plus.clicked.connect(lambda: self.down.setValue(self.down.value() + 1))
        self.last_button = QPushButton()
        self.last_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.last_button.setFont(t.font(12, 600))
        self.last_button.setStyleSheet(
            f"QPushButton {{ color: {t.SELECT}; background: transparent; border: 1px solid {t.LINE_STRONG};"
            f" border-radius: 4px; padding: 0 8px; height: 26px; }}"
            f"QPushButton:hover {{ border-color: {t.SELECT}; }}"
        )
        self.last_button.clicked.connect(lambda: self.down.setValue(self.counter.last_burned_down))
        down_label = label("Face-down", 13, 600, t.TEXT_BODY)
        down_label.setFixedWidth(84)
        root.addLayout(hbox(down_label, minus, self.down, plus, "stretch", self.last_button, spacing=6))

        # Face-up: ranks, counted like dealt cards
        up_label = label("Face-up", 13, 600, t.TEXT_BODY)
        root.addLayout(hbox(up_label, label("click each rank shown · counted", 12, 400, t.TEXT_3), "stretch", spacing=8))
        grid = QGridLayout()
        grid.setSpacing(4)
        for i, rank in enumerate(UPCARDS):
            button = QPushButton(rank)
            button.setFixedHeight(30)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFont(t.font(17, 700, t.CONDENSED))
            button.setStyleSheet(
                f"QPushButton {{ background: {t.RAISED}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px; }}"
                f"QPushButton:hover {{ border-color: {t.SELECT}; }}"
                f"QPushButton:pressed {{ background: {t.SELECT}; color: {t.WINDOW}; }}"
            )
            button.clicked.connect(lambda _=False, r=rank: self._add_up(r))
            grid.addWidget(button, i // 7, i % 7)
        root.addLayout(grid)

        self.chips_holder = QWidget()
        self.chips = hbox(spacing=4)
        self.chips_holder.setLayout(self.chips)
        root.addWidget(self.chips_holder)

        note = label("Face-down burns only shorten the shoe (true count, penetration). "
                     "Face-up burns also change the running count.", 11, 400, t.TEXT_3)
        note.setWordWrap(True)
        root.addWidget(note)

        done = Button("Done", "primary", height=30)
        done.clicked.connect(self.close)
        root.addLayout(hbox("stretch", done))

    def open_at(self, button):
        self.refresh()
        self.adjustSize()
        # Open above the button, right-aligned with it
        pos = button.mapToGlobal(QPoint(button.width() - WIDTH, -self.height() - 6))
        self.move(pos)
        self.show()

    def _down_changed(self, value):
        self.counter.set_burned_down(value)
        log("SYSTEM", f"Face-down burned cards: {value}")
        self.refresh()
        self.changed.emit()

    def _add_up(self, rank):
        self.counter.add_burned_up(rank)
        log("SYSTEM", f"Face-up burn: {rank} ({HILO_VALUE.get(rank, 0):+d})")
        self.refresh()
        self.changed.emit()

    def _remove_up(self, entry_id):
        self.counter.remove_burned_up(entry_id)
        log("SYSTEM", "Face-up burn removed")
        self.refresh()
        self.changed.emit()

    def refresh(self):
        snap = self.counter.snapshot(8)
        self.down.blockSignals(True)
        self.down.setValue(snap["burned_down"])
        self.down.blockSignals(False)
        last = self.counter.last_burned_down
        self.last_button.setVisible(bool(last))
        self.last_button.setText(f"Use last: {last}")
        self.total.setText(f"{snap['burned']} total")

        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not snap["burned_up"]:
            self.chips.addWidget(label("No face-up burns yet", 12, 400, t.TEXT_3))
        for entry in snap["burned_up"]:
            value = HILO_VALUE.get(entry["rank"], 0)
            color = t.count_color(value)
            chip = QPushButton(f"{entry['rank']}  ✕")
            chip.setToolTip("Remove this face-up burn")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFixedHeight(24)
            chip.setFont(t.font(13, 700, t.CONDENSED))
            chip.setStyleSheet(
                f"QPushButton {{ color: {color}; background: transparent; border: 1px solid {color};"
                f" border-radius: 12px; padding: 0 10px; }}"
            )
            chip.clicked.connect(lambda _=False, i=entry["id"]: self._remove_up(i))
            self.chips.addWidget(chip)
        self.chips.addStretch(1)
