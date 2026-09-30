"""Main tab: counts, shoe, hand input and advice on the left; live feed and controls on the right."""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QHBoxLayout, QMenu, QSpinBox, QStackedLayout, QVBoxLayout, QWidget

from core import config
from core.betting import ramp_bet
from core.strategy import UPCARDS
from ui import theme as t
from ui.widgets import (
    Badge, Button, ChoiceGrid, Panel, Segmented, dashed_rect, hbox, label, section_label, set_color, vbox,
)

HAND_VALUES = {
    "hard": ([(v, str(v)) for v in range(5, 22)], 9),
    "soft": ([(v, f"A,{v - 11}") for v in range(13, 21)], 4),
    "pair": ([(v, "10,10" if v == "10" else f"{v},{v}") for v in ["2", "3", "4", "5", "6", "7", "8", "9", "10", "A"]], 5),
}


class PenBar(QWidget):
    """Shoe progress bar with a white cut-card marker."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(16)
        self._fill, self._cut, self._color = 0.0, 0.75, t.SELECT

    def set_values(self, fill, cut, color):
        self._fill, self._cut, self._color = fill, cut, color
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        w = self.width()
        p.setBrush(QColor("#171C24"))
        p.drawRoundedRect(QRectF(0, 4, w, 8), 4, 4)
        if self._fill > 0:
            p.setBrush(QColor(self._color))
            p.drawRoundedRect(QRectF(0, 4, max(8, w * min(1, self._fill)), 8), 4, 4)
        p.setBrush(QColor(t.TEXT))
        p.drawRect(QRectF(w * self._cut - 1, 0, 2, 16))


class FeedView(QWidget):
    """The 640 × 640 live feed at 1:1 (or a placeholder), with the draggable yellow counting zone.

    Drag inside the zone to move it, drag a corner to resize it, right-click to reset it.
    """

    zone_changed = Signal(tuple)
    HANDLE = 8
    MIN_W, MIN_H = 40, 30

    def __init__(self):
        super().__init__()
        self.setFixedSize(config.FRAME_SIZE, config.FRAME_SIZE)
        self.setMouseTracking(True)
        self._image = None
        self._message = ("CAPTURE STOPPED", "Press Start capture to stream the 640 × 640 region")
        self.zone = tuple(config.ZONE)
        self._drag = None      # ("move" | corner name, press position, zone at press)
        self._hover = False

    def set_zone(self, zone):
        self.zone = tuple(zone)
        self.update()

    # ---------- zone editing ----------

    def _corners(self):
        x1, y1, x2, y2 = self.zone
        return {"tl": (x1, y1), "tr": (x2, y1), "bl": (x1, y2), "br": (x2, y2)}

    def _hit(self, pos):
        for name, (cx, cy) in self._corners().items():
            if abs(pos.x() - cx) <= self.HANDLE and abs(pos.y() - cy) <= self.HANDLE:
                return name
        x1, y1, x2, y2 = self.zone
        return "move" if x1 <= pos.x() <= x2 and y1 <= pos.y() <= y2 else None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            hit = self._hit(event.position())
            if hit:
                self._drag = (hit, event.position(), self.zone)

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag is None:
            hit = self._hit(pos)
            cursors = {"move": Qt.CursorShape.SizeAllCursor, "tl": Qt.CursorShape.SizeFDiagCursor,
                       "br": Qt.CursorShape.SizeFDiagCursor, "tr": Qt.CursorShape.SizeBDiagCursor,
                       "bl": Qt.CursorShape.SizeBDiagCursor}
            self.setCursor(cursors.get(hit, Qt.CursorShape.ArrowCursor))
            if bool(hit) != self._hover:
                self._hover = bool(hit)
                self.update()
            return

        mode, start, (x1, y1, x2, y2) = self._drag
        dx, dy = round(pos.x() - start.x()), round(pos.y() - start.y())
        size = config.FRAME_SIZE - 1

        if mode == "move":
            w, h = x2 - x1, y2 - y1
            nx1, ny1 = min(max(0, x1 + dx), size - w), min(max(0, y1 + dy), size - h)
            self.zone = (nx1, ny1, nx1 + w, ny1 + h)
        else:
            if "l" in mode:
                x1 = min(max(0, x1 + dx), x2 - self.MIN_W)
            if "r" in mode:
                x2 = max(min(size, x2 + dx), x1 + self.MIN_W)
            if "t" in mode:
                y1 = min(max(0, y1 + dy), y2 - self.MIN_H)
            if "b" in mode:
                y2 = max(min(size, y2 + dy), y1 + self.MIN_H)
            self.zone = (x1, y1, x2, y2)
        self.update()

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            moved = self.zone != self._drag[2]
            self._drag = None
            if moved:
                self.zone_changed.emit(self.zone)

    def leaveEvent(self, event):
        if self._hover and self._drag is None:
            self._hover = False
            self.update()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu {{ background: {t.RAISED}; color: {t.TEXT}; border: 1px solid {t.LINE_STRONG}; }}"
                           f"QMenu::item:selected {{ background: {t.SELECT}; color: {t.WINDOW}; }}")
        reset = menu.addAction("Reset counting zone to default")
        if menu.exec(event.globalPos()) == reset:
            self.set_zone(config.ZONE)
            self.zone_changed.emit(self.zone)

    def set_image(self, image: QImage):
        self._image = image
        self.update()

    def set_placeholder(self, title, text):
        self._image = None
        self._message = (title, text)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#030405"))

        zx1, zy1, zx2, zy2 = self.zone
        zone_rect = QRectF(zx1, zy1, zx2 - zx1, zy2 - zy1)
        editing = self._hover or self._drag is not None

        if self._image is not None:
            p.drawImage(0, 0, self._image)
            p.setPen(QPen(QColor("#FFFF00"), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(zone_rect)
        else:
            if editing:
                p.setPen(QPen(QColor("#FFFF00"), 1))
                p.drawRect(zone_rect)
            else:
                dashed_rect(p, zone_rect, "#5F5A1E")
            title, text = self._message
            p.setFont(t.font(13, 700, spacing=0.14))
            p.setPen(QColor(t.TEXT_3))
            p.drawText(QRectF(0, 290, 640, 20), Qt.AlignmentFlag.AlignCenter, title)
            p.setFont(t.font(13))
            p.drawText(QRectF(0, 316, 640, 20), Qt.AlignmentFlag.AlignCenter, text)

        if editing:
            # Corner handles + hint while hovering or dragging the zone
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FFFF00"))
            for cx, cy in self._corners().values():
                p.drawRect(QRectF(cx - 4, cy - 4, 8, 8))
            hint = "drag to move · corners to resize · right-click to reset"
            p.setFont(t.font(11, 600))
            hint_w = p.fontMetrics().horizontalAdvance(hint) + 12
            hx = min(max(0, zx1), 640 - hint_w)
            hy = zy1 - 24 if zy1 > 30 else zy2 + 6
            p.setBrush(QColor(0, 0, 0, 200))
            p.drawRoundedRect(QRectF(hx, hy, hint_w, 18), 3, 3)
            p.setPen(QColor("#FFFF00"))
            p.drawText(QRectF(hx, hy, hint_w, 18), Qt.AlignmentFlag.AlignCenter, hint)

        p.setPen(QColor(t.LINE_SOFT))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(0, 0, 639, 639)


def small_spin(value, minimum, maximum, step, decimals):
    box = QDoubleSpinBox() if decimals else QSpinBox()
    if decimals:
        box.setDecimals(decimals)
    box.setRange(minimum, maximum)
    box.setSingleStep(step)
    box.setValue(value)
    box.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)   # type or scroll the mouse wheel to change
    box.setFixedSize(48 if decimals else 42, 24)
    box.setFont(t.font(12, 400, t.MONO))
    return box


class MainTab(QWidget):

    hand_changed = Signal(dict)          # {"up": str|None, "type": str, "val": int|str|None}
    shoe_changed = Signal(float, float)  # decks in shoe, decks behind cut
    capture_toggled = Signal()
    new_shoe = Signal()
    undo = Signal()
    adjust = Signal(int)
    burn_clicked = Signal()

    def __init__(self, strategy):
        super().__init__()
        self.strategy = strategy
        self.hand = {"up": None, "type": "hard", "val": None}
        self.compact = False

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(12)

        self.left_layout = QVBoxLayout()
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(8)
        self.left_layout.addWidget(self._build_counts())
        self.left_layout.addWidget(self._build_shoe())
        self.left_layout.addWidget(self._build_hand())
        self.left_layout.addWidget(self._build_advice(), 1)
        left_widget = QWidget()
        left_widget.setLayout(self.left_layout)
        left_widget.setFixedWidth(420)
        root.addWidget(left_widget)

        self.right_layout = QVBoxLayout()
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(8)
        self.feed = FeedView()
        self.right_layout.addWidget(self.feed)
        self.right_layout.addWidget(self._build_controls())
        self.right_layout.addStretch(1)
        self.feed_column = QWidget()
        self.feed_column.setLayout(self.right_layout)
        root.addWidget(self.feed_column)
        root.addStretch(1)

    # ---------- building ----------

    def _count_column(self, title, numeral_size):
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(section_label(title))
        value = label("0", numeral_size, 700, t.TEXT, t.CONDENSED)
        value.setFixedHeight(72)
        column.addWidget(value)
        caption = label("", 12, 400, t.TEXT_2)
        caption.setTextFormat(Qt.TextFormat.RichText)
        caption.setWordWrap(True)
        column.addWidget(caption)
        column.addStretch(1)
        return column, value, caption

    def _build_counts(self):
        panel = Panel()
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(0)

        rc_col, self.rc_value, rc_caption = self._count_column("RUNNING", 68)
        rc_caption.setText(f'<span style="color:{t.TEXT_3}">Hi-Lo</span>')
        tc_col, self.tc_value, self.tc_caption = self._count_column("TRUE", 68)
        bet_col, self.bet_value, self.bet_caption = self._count_column("BET", 52)

        for i, (col, stretch) in enumerate(((rc_col, 100), (tc_col, 115), (bet_col, 110))):
            holder = QWidget()
            holder.setLayout(col)
            if i:
                holder.setObjectName("sep")
                holder.setStyleSheet(f"QWidget#sep {{ border-left: 1px solid {t.LINE}; }}")
                col.setContentsMargins(12, 0, 0, 0)
            layout.addWidget(holder, stretch)
        return panel

    def _build_shoe(self):
        panel = Panel()
        layout = vbox(spacing=7, margins=(14, 9, 14, 10))
        panel.setLayout(layout)

        self.shoe_text = label("", 13, 400, t.TEXT_2)
        self.shoe_text.setTextFormat(Qt.TextFormat.RichText)
        layout.addLayout(hbox(section_label("SHOE"), "stretch", self.shoe_text))

        self.pen_bar = PenBar()
        layout.addWidget(self.pen_bar)

        self.pen_text = label("", 12, 400, t.TEXT_2)
        self.pen_text.setTextFormat(Qt.TextFormat.RichText)
        self.new_shoe_badge = Badge("NEW SHOE SOON", t.WARNING, "transparent", t.WARNING, height=18, size=11, spacing=0.06)
        self.new_shoe_badge.hide()

        self.decks_spin = small_spin(8, 1, 8, 1, 0)
        self.behind_spin = small_spin(2.0, 0.5, 4, 0.5, 1)
        self.decks_spin.valueChanged.connect(self._emit_shoe)
        self.behind_spin.valueChanged.connect(self._emit_shoe)

        layout.addLayout(hbox(
            self.pen_text, self.new_shoe_badge, "stretch",
            label("Decks", 12, 400, t.TEXT_2), self.decks_spin,
            label("Behind cut", 12, 400, t.TEXT_2), self.behind_spin, spacing=6,
        ))
        return panel

    def _build_hand(self):
        panel = Panel()
        layout = vbox(spacing=7, margins=(14, 9, 14, 12))
        panel.setLayout(layout)

        clear = Button("Clear", height=22, size=12)
        clear.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {t.TEXT_2}; border: 1px solid {t.LINE_STRONG};"
            f" border-radius: 4px; padding: 0 10px; }}"
            f"QPushButton:hover {{ color: {t.TEXT}; border-color: {t.TEXT_2}; }}"
        )
        clear.clicked.connect(self.clear_hand)
        layout.addLayout(hbox(section_label("DEALER UPCARD"), "stretch", clear))

        self.upcards = ChoiceGrid(columns=7, size=19)
        self.upcards.set_options([(u, u) for u in UPCARDS])
        self.upcards.changed.connect(lambda v: self._set_hand(up=v))
        layout.addWidget(self.upcards)

        your_hand = section_label("YOUR HAND")
        your_hand.setFixedWidth(88)
        self.type_seg = Segmented([("hard", "Hard"), ("soft", "Soft"), ("pair", "Pair")])
        self.type_seg.select("hard")
        self.type_seg.changed.connect(self._set_type)
        row = hbox(your_hand, self.type_seg, spacing=10)
        row.setContentsMargins(0, 3, 0, 0)
        layout.addLayout(row)

        self.values = ChoiceGrid(size=18)
        self.values.changed.connect(lambda v: self._set_hand(val=v))
        layout.addWidget(self.values)
        self._fill_values()
        return panel

    def _build_advice(self):
        self.advice_panel = Panel(border=t.LINE_STRONG)
        outer = vbox(spacing=6, margins=(14, 12, 14, 12))
        self.advice_panel.setLayout(outer)

        # Empty state
        self.empty = QWidget()
        self.empty_hint = label("", 13, 400, t.TEXT_2)
        self.empty_hint.setWordWrap(True)
        self.empty.setLayout(vbox(
            "stretch", section_label("ADVICE", t.TEXT_3),
            label("Waiting for a hand", 30, 600, t.TEXT_3, t.CONDENSED), self.empty_hint, "stretch", spacing=6,
        ))

        # Advice state
        self.advice = QWidget()
        self.badge = Badge("BASIC STRATEGY")
        self.badge_detail = label("", 13, 600, t.DEVIATION)
        self.hand_text = label("", 12, 400, t.TEXT_2)
        self.action_word = label("", 58, 700, t.TEXT, t.CONDENSED, spacing=0.02)
        self.action_word.setFixedHeight(60)
        self.fallback = label("", 14, 400, t.TEXT_BODY)
        self.watch_badge = Badge("", t.DEVIATION, "transparent", t.DEVIATION, height=16, size=10, spacing=0)
        self.watch_text = label("", 12, 400, t.TEXT_2)
        self.watch_row = QWidget()
        self.watch_row.setLayout(hbox(self.watch_badge, self.watch_text, "stretch", spacing=6))
        self.advice.setLayout(vbox(
            hbox(self.badge, self.badge_detail, "stretch", self.hand_text, spacing=8),
            self.action_word, self.fallback, self.watch_row, "stretch", spacing=6,
        ))

        stack_holder = QWidget()
        self.advice_stack = QStackedLayout(stack_holder)
        self.advice_stack.addWidget(self.empty)
        self.advice_stack.addWidget(self.advice)
        outer.addWidget(stack_holder, 1)

        # Insurance line (dealer Ace)
        self.insurance = QFrame()
        self.insurance.setObjectName("ins")
        self.insurance.setFixedHeight(30)
        self.ins_word = label("", 14, 700)
        self.ins_note = label("", 12, 400, t.TEXT_2)
        self.insurance.setLayout(hbox(
            label("INSURANCE", 12, 600, t.TEXT_2, spacing=0.06), self.ins_word, self.ins_note, "stretch",
            spacing=8, margins=(10, 0, 10, 0),
        ))
        outer.addWidget(self.insurance)
        return self.advice_panel

    def _build_controls(self):
        self.run_button = Button("●  Start capture", "primary")
        self.run_button.setMinimumWidth(128)
        self.run_button.clicked.connect(self.capture_toggled.emit)

        new_shoe = Button("New shoe")
        new_shoe.clicked.connect(self.new_shoe.emit)
        self.undo_button = undo = Button("Undo last card")
        undo.clicked.connect(self.undo.emit)
        minus = Button("−1", width=38, size=17, family=t.CONDENSED, color=t.MINUS)
        minus.clicked.connect(lambda: self.adjust.emit(-1))
        plus = Button("+1", width=38, size=17, family=t.CONDENSED, color=t.PLUS)
        plus.clicked.connect(lambda: self.adjust.emit(1))
        self.burn_button = Button("Burn")
        self.burn_button.setToolTip("Burned cards: face-down (shorten the shoe) and face-up (counted)")
        self.burn_button.clicked.connect(self.burn_clicked.emit)

        self.counted_text = label("", 12, 400, t.TEXT_2)
        self.counted_text.setTextFormat(Qt.TextFormat.RichText)
        self.last_text = label("Last: —", 12, 400, t.TEXT_2)
        stats = vbox(self.counted_text, self.last_text, spacing=0)
        stats.setAlignment(self.counted_text, Qt.AlignmentFlag.AlignRight)
        stats.setAlignment(self.last_text, Qt.AlignmentFlag.AlignRight)
        stats_widget = QWidget()
        stats_widget.setLayout(stats)

        # One row under the feed, or two rows under the left panel when the feed is hidden
        self._control_widgets = {"run": self.run_button, "new": new_shoe, "undo": undo, "minus": minus,
                                 "plus": plus, "burn": self.burn_button, "stats": stats_widget}
        self.controls = QWidget()
        self.controls.setLayout(hbox(*(self._control_widgets[k] for k in ("run", "new", "undo", "minus", "plus", "burn")),
                                     "stretch", stats_widget, spacing=6))
        return self.controls

    def set_compact(self, compact):
        """Hide the live feed: the controls move under the left panel (short labels, no stats) so the window can be narrow."""
        self.compact = compact
        self.feed_column.setVisible(not compact)
        if compact:
            self.left_layout.addWidget(self.controls)
        else:
            self.right_layout.insertWidget(1, self.controls)
        self.run_button.setMinimumWidth(0 if compact else 128)
        self.undo_button.setText("Undo" if compact else "Undo last card")
        self._control_widgets["stats"].setVisible(not compact)

    # ---------- hand input ----------

    def _fill_values(self):
        options, columns = HAND_VALUES[self.hand["type"]]
        self.values.set_options(options, columns)
        self.values.select(self.hand["val"])

    def _set_type(self, hand_type):
        self.hand["type"], self.hand["val"] = hand_type, None
        self._fill_values()
        self.hand_changed.emit(dict(self.hand))

    def _set_hand(self, **changes):
        self.hand.update(changes)
        self.hand_changed.emit(dict(self.hand))

    def clear_hand(self):
        self.hand["up"], self.hand["val"] = None, None
        self.upcards.select(None)
        self.values.select(None)
        self.hand_changed.emit(dict(self.hand))

    def _emit_shoe(self):
        self.shoe_changed.emit(float(self.decks_spin.value()), float(self.behind_spin.value()))

    def set_shoe_inputs(self, decks, behind):
        for box, value in ((self.decks_spin, decks), (self.behind_spin, behind)):
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)

    # ---------- updates ----------

    def set_capture_state(self, capturing, ready):
        self.run_button.setEnabled(ready)
        if capturing:
            self.run_button.setText("■  Stop" if self.compact else "■  Stop capture")
            self.run_button.set_kind("destructive")
        else:
            self.run_button.setText(("●  Start" if self.compact else "●  Start capture") if ready
                                    else ("Loading…" if self.compact else "Loading model…"))
            self.run_button.set_kind("primary")

    def refresh(self, snap, settings):
        rc, tc, ti = snap["running_count"], snap["true_count"], snap["tc_int"]
        decks = settings["shoe_decks"]
        unit = float(settings["calculator"]["unit"]) or 10
        dealt, burned, gone = snap["cards_dealt"], snap["burned"], snap["cards_gone"]

        # Counts
        self.rc_value.setText(t.signed(rc))
        set_color(self.rc_value, t.count_color(rc))
        tc_text = ("+" if tc > 0.05 else "−" if tc < -0.05 else "") + f"{abs(tc):.1f}"
        self.tc_value.setText(tc_text)
        set_color(self.tc_value, t.count_color(ti))
        self.tc_caption.setText(f'using <b style="color:{t.count_color(ti)}">{t.signed(ti)}</b>')

        bet = ramp_bet(settings["bets"], ti)
        units = round(bet / unit)
        self.bet_value.setText(t.money(bet))
        set_color(self.bet_value, t.PLUS if bet > unit else t.TEXT)
        self.bet_caption.setText(
            f'<span style="color:{t.TEXT};font-weight:600">{units} unit{"" if units == 1 else "s"}</span>'
            f' · Ramp {settings["calculator"]["spread"]} · base {t.money(unit)}'
        )

        # Shoe
        total = decks * 52
        cut_at = (decks - settings["behind_cut"]) * 52
        pen, cut = gone / total, cut_at / total
        near_cut = gone >= cut_at - 26
        white = f'color:{t.TEXT};font-weight:600'
        burned_text = f' · <span style="color:{t.WARNING};font-weight:600">{burned}</span> burned' if burned else ""
        self.shoe_text.setText(
            f'<span style="{white}">{dealt}</span> dealt{burned_text}'
            f' · <span style="{white}">{max(0, int(total - gone))}</span> left'
            f' · <span style="{white}">{snap["decks_left"]:.1f}</span> decks'
        )
        self.burn_button.setText(f"Burn · {burned}" if burned else "Burn")
        self.pen_bar.set_values(pen, cut, t.WARNING if near_cut else t.SELECT)
        self.pen_text.setText(
            f'<b style="color:{t.WARNING if near_cut else t.TEXT}">{round(pen * 100)}%</b> of {round(cut * 100)}% cut'
        )
        self.new_shoe_badge.setVisible(near_cut)

        # Controls readout
        self.counted_text.setText(f'Cards counted: <span style="{white}">{dealt}</span>')
        self.last_text.setText(f"Last: {snap['last_card'].replace('-', '−') if snap['last_card'] else '—'}")

        self._refresh_advice(rc, ti)

    def _refresh_advice(self, rc, ti):
        hand = self.hand
        advice = self.strategy.advise(hand["type"], hand["val"], hand["up"], ti, rc)

        if advice is None:
            self.advice_stack.setCurrentWidget(self.empty)
            self.empty_hint.setText("Pick the dealer upcard, then your hand type and value."
                                    if not hand["up"] else "Now pick your hand value.")
            self.advice_panel.set_border(t.LINE_STRONG)
        else:
            self.advice_stack.setCurrentWidget(self.advice)
            if advice.is_deviation:
                self.badge.setText("DEVIATION")
                self.badge.set_style(t.WINDOW, t.DEVIATION, t.DEVIATION)
                self.badge_detail.setText(advice.detail)
                self.advice_panel.set_border(t.DEVIATION, 2)
            else:
                self.badge.setText("BASIC STRATEGY")
                self.badge.set_style(t.TEXT_BODY, "transparent", t.TEXT_3)
                self.badge_detail.setText("")
                self.advice_panel.set_border(t.LINE_STRONG)
            self.hand_text.setText(advice.hand_text)
            self.action_word.setText(advice.word)
            set_color(self.action_word, t.ACTION_COLOR.get(advice.action, t.TEXT))
            self.fallback.setText(advice.fallback)
            self.watch_row.setVisible(bool(advice.watch))
            if advice.watch:
                self.watch_badge.setText(advice.watch["label"])
                self.watch_text.setText(advice.watch["text"])

        # Insurance line only when the dealer shows an Ace
        self.insurance.setVisible(hand["up"] == "A")
        if hand["up"] == "A":
            if self.strategy.take_insurance(ti):
                self.ins_word.setText("TAKE")
                set_color(self.ins_word, t.PLUS)
                self.ins_note.setText(f"TC {t.signed(ti)} · take at TC ≥ +3")
                fg, bg = t.PLUS, t.PLUS_DARK
            else:
                self.ins_word.setText("don’t take")
                set_color(self.ins_word, t.TEXT)
                self.ins_note.setText("take only at TC ≥ +3")
                fg, bg = t.LINE_STRONG, t.RAISED
            self.insurance.setStyleSheet(f"QFrame#ins {{ background: {bg}; border: 1px solid {fg}; border-radius: 4px; }}")
