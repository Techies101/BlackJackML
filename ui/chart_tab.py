"""Basic Strategy and Deviations tabs: the four BJA charts stacked vertically."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from ui import theme as t
from ui.widgets import Panel, hbox, label, vbox

WIDTH = 860
LABEL_W = 80
GAP = 2
HEAD_H, ROW_H = 24, 28

TABLE_KEYS = {
    "pair": [("Y", "Split the pair"), ("Y/N", "Split if Double After Split is offered, otherwise don’t"), ("N", "Don’t split the pair")],
    "soft": [("H", "Hit"), ("S", "Stand"), ("D", "Double if allowed, otherwise hit"), ("Ds", "Double if allowed, otherwise stand")],
    "hard": [("H", "Hit"), ("S", "Stand"), ("D", "Double if allowed, otherwise hit")],
    "surrender": [("SUR", "Surrender")],
}
TITLES = {"pair": "PAIR SPLITTING", "soft": "SOFT TOTALS", "hard": "HARD TOTALS", "surrender": "LATE SURRENDER"}


class StrategyTable(QWidget):

    def __init__(self, strategy, kind, with_deviations):
        super().__init__()
        self.strategy, self.kind, self.with_dev = strategy, kind, with_deviations
        self.rows = [r for r in strategy.tables[kind] if with_deviations or kind != "surrender" or r != "17"]
        self.position, self.tc_int, self.rc = None, 0, 0
        self._key_layout = self._layout_key()
        self.setFixedSize(WIDTH, self._height())

    def _layout_key(self):
        """Flow the colour key items into lines: [(x, y, code, desc, chip_w)]."""
        chip_font, text_font = QFontMetrics(t.font(13, 700)), QFontMetrics(t.font(13))
        items, x, y = [], 12, 9
        for code, desc in TABLE_KEYS[self.kind]:
            chip_w = max(38, chip_font.horizontalAdvance(code) + 12)
            w = chip_w + 8 + text_font.horizontalAdvance(desc)
            if x > 12 and x + w > WIDTH - 12:
                x, y = 12, y + 28
            items.append((x, y, code, desc, chip_w))
            x += w + 18
        self._key_h = y + 22 + 9
        return items

    def _height(self):
        return 34 + 22 + GAP * 2 + HEAD_H + len(self.rows) * (ROW_H + GAP) + 1 + self._key_h

    def set_state(self, position, tc_int, rc):
        self.position, self.tc_int, self.rc = position, tc_int, rc
        self.update()

    def _highlight_row(self):
        p = self.position
        if not p:
            return None
        if p["kind"] == self.kind:
            return p["row"]
        if self.kind == "surrender" and p["kind"] == "hard" and p["row"] in ("15", "16"):
            return p["row"]
        return None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = WIDTH
        cols = self.strategy.columns
        col_w = (w - GAP * 2 - LABEL_W - GAP * len(cols)) / len(cols)
        hl_row = self._highlight_row()
        hl_col = self.position["col"] if self.position else None

        # Frame
        p.setPen(QPen(QColor(t.LINE), 1))
        p.setBrush(QColor(t.CHROME))
        p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, self.height() - 1), 6, 6)
        p.setClipRect(QRectF(1, 1, w - 2, self.height() - 2))

        # Title + "DEALER UPCARD"
        p.fillRect(QRectF(1, 1, w - 2, 33), QColor(t.RAISED))
        p.setPen(QColor(t.TEXT))
        p.setFont(t.font(15, 700, spacing=0.14))
        p.drawText(QRectF(0, 0, w, 34), Qt.AlignmentFlag.AlignCenter, TITLES[self.kind])
        p.setPen(QColor(t.TEXT_2))
        p.setFont(t.font(11, 600, spacing=0.2))
        p.drawText(QRectF(0, 34, w, 22), Qt.AlignmentFlag.AlignCenter, "DEALER UPCARD")
        p.fillRect(QRectF(1, 55, w - 2, 1), QColor(t.LINE))

        # Grid
        top = 56
        grid_h = GAP * 2 + HEAD_H + len(self.rows) * (ROW_H + GAP)
        p.fillRect(QRectF(1, top, w - 2, grid_h), QColor(t.WINDOW))
        y = top + GAP

        def x_of(i):
            return GAP + LABEL_W + GAP + i * (col_w + GAP)

        p.setFont(t.font(13, 700))
        for i, c in enumerate(cols):
            on = c == hl_col
            rect = QRectF(x_of(i), y, col_w, HEAD_H)
            p.fillRect(rect, QColor(t.TEXT if on else t.RAISED))
            p.setPen(QColor(t.WINDOW if on else t.TEXT_BODY))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, c)
        y += HEAD_H + GAP

        for row in self.rows:
            on_row = row == hl_row
            rect = QRectF(GAP, y, LABEL_W, ROW_H)
            p.fillRect(rect, QColor(t.TEXT if on_row else t.RAISED))
            p.setPen(QColor(t.WINDOW if on_row else t.TEXT_BODY))
            p.setFont(t.font(14, 700))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, row)

            for i, c in enumerate(cols):
                code = self.strategy.tables[self.kind][row][i]
                bg, fg = t.CELL_STYLE.get(code, t.CELL_NEUTRAL)
                rect = QRectF(x_of(i), y, col_w, ROW_H)
                p.fillRect(rect, QColor(bg))

                deviation = self.strategy.deviations.get((self.kind, row, c)) if self.with_dev else None
                if deviation:
                    active = deviation.active(self.tc_int, self.rc)
                    p.setFont(t.font(13, 700))
                    text_w = QFontMetrics(p.font()).horizontalAdvance(deviation.label)
                    bw = max(32, text_w + 10)
                    badge = QRectF(rect.center().x() - bw / 2, rect.center().y() - 10, bw, 20)
                    p.setPen(QPen(QColor(t.DEVIATION), 1.5))
                    p.setBrush(QColor(t.DEVIATION if active else t.WINDOW))
                    p.drawRoundedRect(badge, 3, 3)
                    p.setPen(QColor(t.WINDOW if active else t.DEVIATION))
                    p.drawText(badge, Qt.AlignmentFlag.AlignCenter, deviation.label)
                elif code != "-":
                    p.setPen(QColor(fg))
                    p.setFont(t.font(14, 600))
                    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, code)

                if on_row and c == hl_col:
                    p.setPen(QPen(QColor("#FFFFFF"), 2))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRect(rect.adjusted(1, 1, -1, -1))
            y += ROW_H + GAP

        # Colour key
        key_top = top + grid_h
        p.fillRect(QRectF(1, key_top, w - 2, 1), QColor(t.LINE))
        p.fillRect(QRectF(1, key_top + 1, w - 2, self._key_h), QColor(t.PANEL))
        for x, ky, code, desc, chip_w in self._key_layout:
            bg, fg = t.CELL_STYLE.get(code, t.CELL_NEUTRAL)
            chip = QRectF(x, key_top + 1 + ky, chip_w, 22)
            p.setPen(QPen(QColor(t.LINE), 1))
            p.setBrush(QColor(bg))
            p.drawRoundedRect(chip, 3, 3)
            p.setPen(QColor(fg))
            p.setFont(t.font(13, 700))
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, code)
            p.setPen(QColor(t.TEXT_BODY))
            p.setFont(t.font(13))
            p.drawText(QRectF(x + chip_w + 8, key_top + 1 + ky, 600, 22),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, desc)


class ChartTab(QWidget):

    def __init__(self, strategy, deviations):
        super().__init__()
        self.strategy, self.deviations = strategy, deviations

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        content = QWidget()
        content.setStyleSheet(f"background: {t.WINDOW};")
        scroll.setWidget(content)
        column = QVBoxLayout()
        column.setSpacing(14)
        column.setContentsMargins(0, 16, 0, 24)
        centered = QHBoxLayout(content)
        centered.setContentsMargins(0, 0, 0, 0)
        centered.addStretch(1)
        holder = QWidget()
        holder.setFixedWidth(WIDTH)
        holder.setLayout(column)
        centered.addWidget(holder)
        centered.addStretch(1)

        # Header
        title = label("S17 Deviations" if deviations else "Basic Strategy", 28, 700, t.TEXT, t.CONDENSED, spacing=0.04)
        caption = " · ".join(part.strip() for part in strategy.rules.split(",")).replace("late surrender", "Late surrender")
        rules = label(caption, 13, 400, t.TEXT_2)
        self.hand_chip = QLabel("none")
        self.hand_chip.setFont(t.font(12, 700))
        self.hand_chip.setFixedHeight(24)
        self.hand_chip.setStyleSheet(f"color: {t.TEXT}; border: 2px solid #FFFFFF; border-radius: 4px; padding: 0 10px;")
        self.tc_label = label("", 12, 400, t.TEXT_2)
        self.tc_label.setTextFormat(Qt.TextFormat.RichText)
        column.addLayout(hbox(
            vbox(title, rules, spacing=2), "stretch", label("Current hand", 12, 400, t.TEXT_2), self.hand_chip, self.tc_label,
            spacing=8,
        ))

        if deviations:
            column.addWidget(self._legend())

        self.tables = [StrategyTable(strategy, kind, deviations) for kind in ("pair", "soft", "hard", "surrender")]
        for table in self.tables:
            column.addWidget(table)

        self.footer = QLabel()
        self.footer.setFixedHeight(40)
        self.footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.footer.setFont(t.font(15, 700, spacing=0.12))
        column.addWidget(self.footer)
        column.addStretch(1)

    def _legend(self):
        panel = Panel()
        m = t.DEVIATION
        lines = [
            f'<span style="color:{m};font-weight:700">Magenta</span> numbers are the true-count index at which to deviate from basic strategy.',
            f'<b style="color:{m}">+</b> after the index: deviate at that true count and above.',
            f'<b style="color:{m}">−</b> after the index: deviate at that true count and below.',
            f'<b style="color:{m}">0+ / 0−</b>: any positive / negative running count.',
        ]
        text = QVBoxLayout()
        text.setSpacing(3)
        for line in lines:
            item = label(line, 13, 400, t.TEXT_BODY)
            item.setTextFormat(Qt.TextFormat.RichText)
            text.addWidget(item)

        def sample(txt, active, desc):
            chip = QLabel(txt)
            chip.setFont(t.font(12, 700))
            chip.setFixedSize(30, 20)
            chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chip.setStyleSheet(
                f"background: {m if active else t.WINDOW}; color: {t.WINDOW if active else m};"
                f" border: 1.5px solid {m}; border-radius: 3px;"
            )
            return hbox(chip, label(desc, 13, 400, t.TEXT_BODY), spacing=8)

        samples = vbox("stretch", sample("2+", True, "Active at current TC"), sample("4+", False, "Not met yet"), "stretch", spacing=8)
        panel.setLayout(hbox(text, "stretch", samples, spacing=24, margins=(14, 10, 14, 10)))
        return panel

    def refresh(self, position, tc_int, rc):
        self.hand_chip.setText(position["text"] if position else "none")
        self.tc_label.setText(f'TC <b style="color:{t.count_color(tc_int)}">{t.signed(tc_int)}</b>')
        for table in self.tables:
            table.set_state(position, tc_int, rc)

        if not self.deviations:
            fg, bg, border, text = t.TEXT, t.RAISED, t.LINE_STRONG, "INSURANCE OR EVEN MONEY: DON’T TAKE"
        elif self.strategy.take_insurance(tc_int):
            fg, bg, border, text = t.WINDOW, t.DEVIATION, t.DEVIATION, "INSURANCE OR EVEN MONEY: TAKE AT +3  ·  ACTIVE"
        else:
            fg, bg, border, text = t.DEVIATION, t.PANEL, t.DEVIATION, "INSURANCE OR EVEN MONEY: TAKE AT +3"
        self.footer.setText(text)
        self.footer.setStyleSheet(f"color: {fg}; background: {bg}; border: 1px solid {border}; border-radius: 6px;")
