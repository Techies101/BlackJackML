"""Bet Spread tab: calculator (player settings, table rules, ramp, estimates) and the Variance Visualizer."""
import math
import random

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedLayout, QVBoxLayout, QWidget

from core import betting
from ui import theme as t
from ui.widgets import Badge, Button, NumberField, Panel, Segmented, Toggle, combo, hbox, label, set_color, vbox

DECK_OPTIONS = [1, 2, 4, 6, 8]
BEHIND_OPTIONS = [1, 1.5, 2, 2.5, 3]
PLAYER_COLORS = ["#38D6FF", "#FFB224", "#A58BFF", "#E8ECF2", "#FF8AD8", "#7DFFB3", "#FFE24A", "#6FA8FF", "#FF9E7A", "#C3CBD8"]


def fmt_num(v):
    return f"{v:g}"


class Collapsible(QFrame):
    """Panel with a clickable green title bar: collapse ▴ / expand ▾."""

    def __init__(self, title):
        super().__init__()
        self.setObjectName("coll")
        self.setStyleSheet(f"QFrame#coll {{ border: 1px solid {t.LINE}; border-radius: 6px; background: {t.PANEL}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)

        header = QPushButton()
        header.setFixedHeight(38)
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        header.setStyleSheet(f"QPushButton {{ background: {t.RAISED}; border: none; border-top-left-radius: 5px; border-top-right-radius: 5px; }}")
        self.state_text = label("collapse ▴", 12, 400, t.TEXT_2)
        header.setLayout(hbox(label(title, 15, 700, t.PLUS), "stretch", self.state_text, margins=(14, 0, 14, 0)))
        header.clicked.connect(self.toggle)
        outer.addWidget(header)

        self.body = QWidget()
        self.body_layout = vbox(spacing=0, margins=(14, 6, 14, 10))
        self.body.setLayout(self.body_layout)
        outer.addWidget(self.body)

    def toggle(self):
        self.body.setVisible(not self.body.isVisible())
        self.state_text.setText("collapse ▴" if self.body.isVisible() else "expand ▾")

    def add_row(self, text, widget):
        row = QWidget()
        row.setFixedHeight(40)
        row.setLayout(hbox(label(text, 14, 400, t.TEXT_BODY), "stretch", widget))
        self.body_layout.addWidget(row)
        return row


def field_block(text, widget):
    return vbox(label(text, 13, 400, t.TEXT_BODY), widget, spacing=4)


class RampRow(QFrame):

    changed = Signal()

    def __init__(self, tc, settings):
        super().__init__()
        self.tc, self.settings = tc, settings
        self.setObjectName("ramp")
        self.setFixedHeight(36)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(12)

        text = "≤−3" if tc == -3 else t.signed(tc)
        index = label(text, 22, 700, t.MINUS if tc < 0 else t.PLUS if tc > 0 else t.TEXT, t.CONDENSED)
        index.setFixedWidth(34)
        index.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.live = QLabel("LIVE")
        self.live.setFont(t.font(9, 700, spacing=0.08))
        self.live.setStyleSheet(f"color: {t.WINDOW}; background: {t.SELECT}; border-radius: 2px; padding: 1px 3px;")
        idx_box = QWidget()
        idx_box.setFixedWidth(70)
        idx_box.setLayout(hbox(index, self.live, "stretch", spacing=6))
        layout.addWidget(idx_box)

        self.bet = NumberField(settings["bets"][tc], "$", "", height=28, size=13)
        self.bet.valueChanged.connect(self._bet_changed)
        layout.addWidget(self.bet, 1)

        self.hand_buttons = {}
        buttons = QWidget()
        buttons.setFixedWidth(110)
        blayout = hbox(spacing=4)
        buttons.setLayout(blayout)
        for n in (1, 2):
            b = QPushButton(f"{n}X")
            b.setFixedHeight(26)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(t.font(12, 700))
            b.clicked.connect(lambda _=False, n=n: self._set_hands(n))
            blayout.addWidget(b)
            self.hand_buttons[n] = b
        layout.addWidget(buttons)
        self.refresh(False)

    def _bet_changed(self, value):
        self.settings["bets"][self.tc] = max(0, value)
        self.changed.emit()

    def _set_hands(self, n):
        self.settings["hands"][self.tc] = n
        self.changed.emit()

    def refresh(self, live):
        unit = float(self.settings["calculator"]["unit"]) or 1
        bet = self.settings["bets"][self.tc]
        self.bet.set_value(bet)
        self.bet.set_suffix(f"{round(bet / unit)}u")
        self.bet.setEnabled(not self.settings["frozen"])
        self.live.setVisible(live)
        self.setStyleSheet(
            f"QFrame#ramp {{ background: {t.SELECT_DARK if live else 'transparent'};"
            f" border: 1px solid {t.SELECT if live else 'transparent'}; border-radius: 4px; }}"
        )
        for n, b in self.hand_buttons.items():
            on = self.settings["hands"][self.tc] == n
            b.setStyleSheet(
                f"QPushButton {{ background: {t.SELECT_DARK if on else 'transparent'}; color: {t.SELECT if on else t.TEXT_3};"
                f" border: 1px solid {t.SELECT if on else t.LINE}; border-radius: 4px; }}"
            )


class VarianceChart(QWidget):

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(420)
        self.data = None

    def set_data(self, ev, sd, hours, bankroll, players, sd_lines, seed):
        hours = int(max(10, min(5000, hours or 10)))
        times, paths = betting.simulate_paths(ev, sd, bankroll, hours, players, seed)
        self.data = dict(ev=ev, sd=sd, hours=hours, bank=bankroll, times=times, paths=paths, sd_lines=sd_lines)
        self.update()

    def paintEvent(self, event):
        if not self.data:
            return
        d = self.data
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        W, H = self.width(), self.height()
        L, R, T, B = 64, 12, 8, 24
        pw, ph = W - L - R, H - T - B
        hours, bank, ev, sd, times = d["hours"], d["bank"], d["ev"], d["sd"], d["times"]

        def envelope(k):
            return [bank + ev * h + k * sd * math.sqrt(h) for h in times]

        lines = {k: envelope(k) for k in (-2, -1, 0, 1, 2)}
        values = [bank] + lines[2] + lines[-2] + lines[0] + [v for path in d["paths"] for v in path]
        lo, hi = min(values), max(values)
        lo = max(lo, -bank * 0.2)
        span = (hi - lo) or 1
        step = next((s for s in (500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000, 100000) if span / s <= 8), 200000)
        lo, hi = math.floor(lo / step) * step, math.ceil(hi / step) * step

        def X(h):
            return L + h / hours * pw

        def Y(v):
            return T + (hi - max(lo, v)) / (hi - lo) * ph

        def poly(vals):
            path = QPainterPath(QPointF(X(times[0]), Y(vals[0])))
            for h, v in zip(times[1:], vals[1:]):
                path.lineTo(X(h), Y(v))
            return path

        def band(upper, lower):
            path = poly(upper)
            for h, v in zip(reversed(times), reversed(lower)):
                path.lineTo(X(h), Y(v))
            path.closeSubpath()
            return path

        if d["sd_lines"]:
            p.fillPath(band(lines[2], lines[-2]), QColor("#111922"))
            p.fillPath(band(lines[1], lines[-1]), QColor("#142330"))

        # Grid + ticks
        p.setFont(t.font(11, 400, t.MONO))
        v = lo
        while v <= hi + 1e-6:
            p.setPen(QPen(QColor("#1C232D"), 1))
            p.drawLine(QPointF(L, Y(v)), QPointF(W - R, Y(v)))
            p.setPen(QColor(t.TEXT_3))
            p.drawText(QRectF(0, Y(v) - 8, 56, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{round(v):,}")
            v += step
        x_step = next((s for s in (10, 25, 50, 100, 200, 250, 500, 1000) if hours / s <= 10), 1000)
        h = 0
        while h <= hours + 1e-6:
            p.setPen(QPen(QColor("#1C232D"), 1))
            p.drawLine(QPointF(X(h), T), QPointF(X(h), T + ph))
            p.setPen(QColor(t.TEXT_3))
            p.drawText(QRectF(X(h) - 30, H - 18, 60, 16), Qt.AlignmentFlag.AlignCenter, str(h))
            h += x_step

        if lo < 0:
            pen = QPen(QColor(t.MINUS), 1)
            pen.setDashPattern([4, 4])
            p.setPen(pen)
            p.drawLine(QPointF(L, Y(0)), QPointF(W - R, Y(0)))

        p.setBrush(Qt.BrushStyle.NoBrush)
        if d["sd_lines"]:
            for k, color in ((2, t.MINUS), (-2, t.MINUS), (1, t.STAND), (-1, t.STAND)):
                p.setPen(QPen(QColor(color), 1.5))
                p.drawPath(poly(lines[k]))
        for i, path in enumerate(d["paths"]):
            p.setPen(QPen(QColor(PLAYER_COLORS[i % len(PLAYER_COLORS)]), 1.5))
            p.drawPath(poly(list(path)))
        p.setPen(QPen(QColor(t.PLUS), 2.5))
        p.drawPath(poly(lines[0]))


class SpreadTab(QWidget):

    changed = Signal()   # settings changed: save, and refresh the Main tab's bet

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.tc_int = 0
        self.seed = 7

        self.stack = QStackedLayout(self)
        self.calc_view = QWidget()
        self.viz_view = QWidget()
        self.stack.addWidget(self.calc_view)
        self.stack.addWidget(self.viz_view)
        self._build_calc()
        self._build_viz()
        self.recompute()

    # ---------- calculator ----------

    def _build_calc(self):
        c = self.settings["calculator"]
        root = vbox(spacing=0)
        self.calc_view.setLayout(root)

        body = hbox(spacing=14, margins=(14, 12, 14, 0))
        root.addLayout(body, 1)

        # Left: settings panels
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(500)
        scroll.viewport().setStyleSheet("background: transparent;")
        left = QWidget()
        left.setObjectName("leftcol")
        left.setStyleSheet(f"QWidget#leftcol {{ background: {t.WINDOW}; }}")
        left_layout = vbox(spacing=12, margins=(0, 0, 6, 12))
        left.setLayout(left_layout)
        scroll.setWidget(left)
        body.addWidget(scroll)

        # Player settings
        player = Collapsible("Player Settings")
        pl = player.body_layout
        pl.setContentsMargins(14, 12, 14, 14)
        pl.setSpacing(10)
        self.mode = Segmented([("Career", "Career"), ("Trip", "Trip")], height=34, size=14, active_bg=t.PLUS)
        self.mode.select(c["mode"])
        self.mode.changed.connect(lambda v: self._set_calc("mode", v))
        pl.addWidget(self.mode)

        self.bankroll = NumberField(c["bankroll"], "$")
        self.bankroll.valueChanged.connect(lambda v: self._set_calc("bankroll", v))
        pl.addLayout(field_block("Available bankroll", self.bankroll))
        self.rph = NumberField(c["rounds_per_hour"])
        self.rph.valueChanged.connect(lambda v: self._set_calc("rounds_per_hour", v))
        pl.addLayout(field_block("Rounds per hour", self.rph))

        self.trip_hours = NumberField(c["trip_hours"])
        self.trip_hours.valueChanged.connect(lambda v: self._set_calc("trip_hours", v))
        self.trip_block = QWidget()
        self.trip_block.setLayout(field_block("Trip length (hours)", self.trip_hours))
        pl.addWidget(self.trip_block)

        self.unit = NumberField(c["unit"], "$")
        self.unit.valueChanged.connect(self._set_unit)
        self.units = NumberField(0)
        self.units.valueChanged.connect(lambda v: self._set_calc("bankroll", v * (float(c["unit"]) or 1)))
        self.spread = combo(betting.SPREAD_PRESETS, c["spread"], height=34)
        self.spread.currentTextChanged.connect(self._set_spread)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        for i, (text, w, stretch) in enumerate((("Unit amount", self.unit, 10), ("# of units", self.units, 10), ("Spread preset", self.spread, 13))):
            grid.addLayout(field_block(text, w), 0, i)
            grid.setColumnStretch(i, stretch)
        pl.addLayout(grid)

        self.devs = combo(["Standard", "None"], c["deviations"], width=150)
        self.devs.currentTextChanged.connect(lambda v: self._set_calc("deviations", v))
        pl.addLayout(hbox(label("Deviations", 14, 400, t.TEXT_BODY), "stretch", self.devs))
        left_layout.addWidget(player)

        # Table rules
        rules = Collapsible("Table Rules")
        self.decks = combo([], None, width=220)
        self.decks.currentIndexChanged.connect(self._decks_from_combo)
        rules.add_row("Number of decks", self.decks)
        self.pen = combo([], None, width=220)
        self.pen.currentIndexChanged.connect(self._pen_from_combo)
        rules.add_row("Penetration", self.pen)
        self.toggles = {}
        for text, key in (("Dealer hits soft 17", "h17"), ("Double after splitting", "das")):
            toggle = Toggle(c[key])
            toggle.toggled.connect(lambda on, k=key: self._set_calc(k, on))
            rules.add_row(text, toggle)
            self.toggles[key] = toggle
        for text, key, opts in (("Resplitting aces", "rsa", ["No re-split aces", "Re-split to 2 hands", "Re-split to 4 hands"]),
                                ("Splitting", "splitting", ["Max 2 hands", "Max 3 hands", "Max 4 hands"]),
                                ("Surrender", "surrender", ["Late surrender", "None"])):
            box = combo(opts, c[key], width=220)
            box.currentTextChanged.connect(lambda v, k=key: self._set_calc(k, v))
            rules.add_row(text, box)
        left_layout.addWidget(rules)

        # Additional settings
        extra = Collapsible("Additional Settings")
        enhc = Toggle(c["enhc"])
        enhc.toggled.connect(lambda on: self._set_calc("enhc", on))
        extra.add_row("ENHC (European no hole card)", enhc)
        for text, key, opts in (("Double rule", "double_rule", ["Any first 2 cards", "9–11 only", "10–11 only"]),
                                ("Blackjack payout", "payout", ["3:2", "6:5", "1:1"])):
            box = combo(opts, c[key], width=220)
            box.currentTextChanged.connect(lambda v, k=key: self._set_calc(k, v))
            extra.add_row(text, box)
        left_layout.addWidget(extra)
        left_layout.addStretch(1)

        # Right: bet spread ramp
        right = vbox(spacing=10, margins=(0, 0, 0, 12))
        ramp_panel = QFrame()
        ramp_panel.setObjectName("rp")
        ramp_panel.setStyleSheet(f"QFrame#rp {{ border: 1px solid {t.LINE}; border-radius: 6px; background: {t.PANEL}; }}")
        ramp_layout = vbox(spacing=0, margins=(1, 1, 1, 1))
        ramp_panel.setLayout(ramp_layout)

        header = QFrame()
        header.setFixedHeight(38)
        header.setStyleSheet(f"background: {t.RAISED}; border: none; border-top-left-radius: 5px; border-top-right-radius: 5px;")
        self.freeze = Toggle(self.settings["frozen"])
        self.freeze.toggled.connect(self._set_frozen)
        header.setLayout(hbox(label("Bet Spread", 15, 700, t.PLUS), "stretch", label("Freeze bets", 13, 400, t.TEXT_BODY),
                              self.freeze, spacing=10, margins=(14, 0, 14, 0)))
        ramp_layout.addWidget(header)

        rows = QWidget()
        rows_layout = vbox(spacing=0, margins=(14, 6, 14, 8))
        rows.setLayout(rows_layout)
        reset = QPushButton("Reset")
        reset.setFixedHeight(24)
        reset.setCursor(Qt.CursorShape.PointingHandCursor)
        reset.setFont(t.font(12, 600))
        reset.setStyleSheet(f"QPushButton {{ color: {t.MINUS}; border: 1px solid {t.MINUS}; border-radius: 4px; padding: 0 9px; background: transparent; }}")
        reset.clicked.connect(self._reset_ramp)
        head = QWidget()
        head.setFixedHeight(36)
        head.setObjectName("rh")
        head.setStyleSheet(f"QWidget#rh {{ border-bottom: 1px solid {t.LINE}; }}")
        c1, c2, c3 = (label(s, 12, 600, t.TEXT_2, spacing=0.06) for s in ("INDEX", "BET PER HAND", "HANDS"))
        c1.setFixedWidth(70)
        hands_box = QWidget()
        hands_box.setFixedWidth(110)
        hands_box.setLayout(hbox(c3, "stretch", reset))
        head.setLayout(hbox(c1, c2, "stretch", hands_box, spacing=12, margins=(6, 0, 6, 0)))
        rows_layout.addWidget(head)

        self.ramp_rows = []
        for tc in betting.TC_INDEXES:
            row = RampRow(tc, self.settings)
            row.changed.connect(self._ramp_changed)
            rows_layout.addWidget(row)
            self.ramp_rows.append(row)
        ramp_layout.addWidget(rows)
        right.addWidget(ramp_panel)

        viz_button = Button("Variance Visualizer", "primary", height=40, size=15)
        viz_button.clicked.connect(self._open_viz)
        right.addWidget(viz_button)
        right.addStretch(1)
        body.addLayout(right, 1)

        # Results bar
        results = QFrame()
        results.setFixedHeight(68)
        results.setObjectName("res")
        results.setStyleSheet(f"QFrame#res {{ background: {t.CHROME}; border-top: 1px solid {t.LINE_STRONG}; }}")
        res_layout = QHBoxLayout(results)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_layout.setSpacing(0)
        self.result_values = []
        for i, text in enumerate(("Expected value", "1 standard deviation", "Risk of ruin", "Hours ’til N-0")):
            cell = QFrame()
            cell.setObjectName("rc")
            if i:
                cell.setStyleSheet(f"QFrame#rc {{ border-left: 1px solid {t.LINE_SOFT}; }}")
            est = Badge("EST.", t.TEXT_3, "transparent", t.LINE_STRONG, height=14, size=10, spacing=0.06)
            est.setStyleSheet(est.styleSheet().replace("padding: 0 7px", "padding: 0 3px").replace("border-radius: 3px", "border-radius: 2px"))
            value = label("", 28, 700, t.TEXT, t.CONDENSED)
            top = hbox("stretch", label(text, 12, 400, t.TEXT_2), est, "stretch", spacing=6)
            cell.setLayout(vbox("stretch", top, hbox("stretch", value, "stretch"), "stretch", spacing=1))
            res_layout.addWidget(cell, 1)
            self.result_values.append(value)
        root.addWidget(results)

        self._fill_rule_combos()
        self._refresh_player_fields()

    def _fill_rule_combos(self):
        decks, behind = self.settings["shoe_decks"], self.settings["behind_cut"]
        deck_opts = sorted(set(DECK_OPTIONS + [int(decks)]))
        self.decks.blockSignals(True)
        self.decks.clear()
        for n in deck_opts:
            self.decks.addItem(f"{n} deck{'s' if n > 1 else ''}", n)
        self.decks.setCurrentIndex(deck_opts.index(int(decks)))
        self.decks.blockSignals(False)

        behind_opts = sorted(set([b for b in BEHIND_OPTIONS if b < decks] + [behind]))
        self.pen.blockSignals(True)
        self.pen.clear()
        for b in behind_opts:
            dealt = decks - b
            self.pen.addItem(f"{fmt_num(dealt)} decks ({int(dealt * 52)} cards · {round(dealt / decks * 100)}%)", b)
        self.pen.setCurrentIndex(behind_opts.index(behind))
        self.pen.blockSignals(False)

    def _refresh_player_fields(self):
        c = self.settings["calculator"]
        self.bankroll.set_value(c["bankroll"])
        self.units.set_value(round(float(c["bankroll"]) / (float(c["unit"]) or 1)))
        self.trip_block.setVisible(c["mode"] == "Trip")

    def _set_calc(self, key, value):
        self.settings["calculator"][key] = value
        self._refresh_player_fields()
        self.recompute()
        self.changed.emit()

    def _set_unit(self, value):
        c = self.settings["calculator"]
        c["unit"] = max(1, value)
        if not self.settings["frozen"]:
            self.settings["bets"], self.settings["hands"] = betting.preset_ramp(c["spread"], c["unit"])
        self._refresh_player_fields()
        self._ramp_changed()

    def _set_spread(self, spread):
        c = self.settings["calculator"]
        c["spread"] = spread
        if not self.settings["frozen"]:
            self.settings["bets"], self.settings["hands"] = betting.preset_ramp(spread, c["unit"])
        self._ramp_changed()

    def _set_frozen(self, on):
        self.settings["frozen"] = on
        self._ramp_changed()

    def _reset_ramp(self):
        c = self.settings["calculator"]
        self.settings["bets"], self.settings["hands"] = betting.preset_ramp(c["spread"], c["unit"])
        self._ramp_changed()

    def _ramp_changed(self):
        self.refresh_live(self.tc_int)
        self.recompute()
        self.changed.emit()

    def _decks_from_combo(self):
        decks = self.decks.currentData()
        self.settings["shoe_decks"] = decks
        self.settings["behind_cut"] = min(self.settings["behind_cut"], decks - 0.5)
        self._fill_rule_combos()
        self.recompute()
        self.changed.emit()

    def _pen_from_combo(self):
        self.settings["behind_cut"] = self.pen.currentData()
        self.recompute()
        self.changed.emit()

    def shoe_updated(self):
        """Decks / behind cut changed on the Main tab."""
        self._fill_rule_combos()
        self.recompute()

    def refresh_live(self, tc_int):
        self.tc_int = tc_int
        live = max(betting.TC_INDEXES[0], min(betting.TC_INDEXES[-1], tc_int))
        for row in self.ramp_rows:
            row.refresh(row.tc == live)

    def estimate(self):
        c = self.settings["calculator"]
        rules = dict(c, decks=self.settings["shoe_decks"], behind_cut=self.settings["behind_cut"])
        return betting.estimate(self.settings["bets"], self.settings["hands"], rules, float(c["bankroll"]),
                                c["rounds_per_hour"], c["mode"], float(c["trip_hours"]))

    def recompute(self):
        r = self.estimate()
        ev, sd, ror, n0 = r["ev_hour"], r["sd_hour"], r["ror"], r["n0_hours"]
        texts = [
            (f"{'−' if ev < 0 else ''}{t.money(abs(ev), 2)}/hr", t.PLUS if ev > 0 else t.MINUS),
            (f"± {t.money(sd, 2)}/hr", t.TEXT),
            (f"{ror * 100:.2f}%", t.MINUS if ror > 0.2 else t.WARNING if ror > 0.05 else t.PLUS),
            (f"{n0:,.1f} hrs" if math.isfinite(n0) else "∞", t.TEXT),
        ]
        for widget, (text, color) in zip(self.result_values, texts):
            widget.setText(text)
            set_color(widget, color)

    # ---------- variance visualizer ----------

    def _build_viz(self):
        root = vbox(spacing=10, margins=(14, 12, 14, 14))
        self.viz_view.setLayout(root)

        self.viz_fields = {}
        row = hbox(spacing=10)
        for key, text, prefix in (("ev", "EV ($/hr)", "$"), ("sd", "Std. deviation", "$"), ("hours", "Hours", ""), ("bank", "Bankroll", "$")):
            field = NumberField(0, prefix, height=32, size=13, decimals=2 if key in ("ev", "sd") else 0)
            field.setFixedWidth(128)
            field.valueChanged.connect(lambda _: self._draw_chart())
            self.viz_fields[key] = field
            row.addLayout(vbox(label(text, 12, 400, t.TEXT_BODY), field, spacing=4))

        self.players = combo(["1 player", "3 players", "5 players", "10 players"], "1 player", width=120, height=32, size=13)
        self.players.currentTextChanged.connect(lambda _: self._draw_chart())
        row.addLayout(vbox(label("Players simulated", 12, 400, t.TEXT_BODY), self.players, spacing=4))
        self.sd_toggle = Toggle(True)
        self.sd_toggle.toggled.connect(lambda _: self._draw_chart())
        sd_holder = QWidget()
        sd_holder.setFixedHeight(32)
        sd_holder.setLayout(hbox(self.sd_toggle, "stretch"))
        row.addLayout(vbox(label("SD lines", 12, 400, t.TEXT_BODY), sd_holder, spacing=4))
        row.addStretch(1)
        run = Button("Run sim", "primary", height=34, width=110, size=14)
        run.clicked.connect(self._run_sim)
        back = Button("Return", "outline", height=34, width=110, size=14, color=t.PLUS)
        back.clicked.connect(lambda: self.stack.setCurrentWidget(self.calc_view))
        row.addWidget(run, 0, Qt.AlignmentFlag.AlignBottom)
        row.addWidget(back, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(row)

        chart_panel = Panel(background=t.CHROME)
        self.legend = hbox("stretch", spacing=16)
        self.chart = VarianceChart()
        chart_layout = vbox(self.legend, spacing=4, margins=(10, 8, 10, 6))
        chart_layout.addWidget(self.chart, 1)
        chart_panel.setLayout(chart_layout)
        root.addWidget(chart_panel, 1)

    def _open_viz(self):
        r = self.estimate()
        values = {"ev": round(r["ev_hour"], 2), "sd": round(r["sd_hour"], 2), "hours": 500,
                  "bank": float(self.settings["calculator"]["bankroll"])}
        for key, field in self.viz_fields.items():
            field.set_value(values[key])
        self.stack.setCurrentWidget(self.viz_view)
        self._draw_chart()

    def _run_sim(self):
        self.seed = random.randrange(1_000_000_000)
        self._draw_chart()

    def _draw_chart(self):
        f = {k: w.value() for k, w in self.viz_fields.items()}
        players = int(self.players.currentText().split()[0])
        sd_on = self.sd_toggle.is_on()

        while self.legend.count():
            item = self.legend.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        items = [("EV", t.PLUS)] + ([("±1 SD", t.STAND), ("±2 SD", t.MINUS)] if sd_on else []) + \
                [(f"Player {i + 1}", PLAYER_COLORS[i]) for i in range(min(players, 3))]
        self.legend.addStretch(1)
        for text, color in items:
            swatch = QFrame()
            swatch.setFixedSize(14, 3)
            swatch.setStyleSheet(f"background: {color};")
            self.legend.addWidget(swatch)
            self.legend.addWidget(label(text, 12, 400, t.TEXT_BODY))
        self.legend.addStretch(1)

        self.chart.set_data(f["ev"], f["sd"], f["hours"], f["bank"], players, sd_on, self.seed)
