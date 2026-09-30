"""
Basic strategy + Hi-Lo deviations (8 decks, S17, DAS, late surrender).

Data comes from strategy/basic_strategy.json and strategy/deviations.json.
The player's hand is entered as a total + type:
    hard: 5..21     soft: 13..20 (A,2..A,9)     pair: "2".."10", "A"
"""
import json
import math
import os
from dataclasses import dataclass, field

STRATEGY_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "strategy")

UPCARDS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
TABLE_KINDS = ["pair", "soft", "hard", "surrender"]

ACTION_WORD = {
    "Y": "SPLIT", "Y/N": "SPLIT", "N": "NO SPLIT", "D": "DOUBLE", "Ds": "DOUBLE",
    "S": "STAND", "H": "HIT", "SUR": "SURRENDER",
}
ACTION_FALLBACK = {
    "Y/N": "Split (Double After Split is offered here)",
    "D": "Double (if not allowed: Hit)",
    "Ds": "Double (if not allowed: Stand)",
}
SHORT_WORD = {"H": "Hit", "S": "Stand", "D": "Double", "Ds": "Double", "SUR": "Surrender", "Y": "Split", "-": "No surrender"}


def true_count_int(true_count):
    """Whole-number true count used for bets and deviations: the displayed value (0.1) rounded to the
    nearest whole number, halves away from zero (−1.2 → −1, −1.5 → −2, +1.5 → +2)."""
    shown = round(true_count, 1)
    return int(math.copysign(math.floor(abs(shown) + 0.5), shown))


def signed(n):
    return f"+{n}" if n > 0 else f"−{abs(n)}" if n < 0 else "0"


@dataclass
class Deviation:
    table: str
    row: str
    dealer: str
    condition: str   # "tc>=", "tc<=", "rc>0", "rc<0"
    index: int
    action: str

    def active(self, tc_int, running_count):
        if self.condition == "rc>0":
            return running_count > 0
        if self.condition == "rc<0":
            return running_count < 0
        if self.condition == "tc>=":
            return tc_int >= self.index
        return tc_int <= self.index

    @property
    def label(self):
        """Index as printed on the chart: 2+, −1−, 0+, 0−."""
        if self.condition == "rc>0":
            return "0+"
        if self.condition == "rc<0":
            return "0−"
        number = f"−{abs(self.index)}" if self.index < 0 else str(self.index)
        return number + ("+" if self.condition == "tc>=" else "−")

    @property
    def condition_text(self):
        if self.condition == "rc>0":
            return "RC > 0"
        if self.condition == "rc<0":
            return "RC < 0"
        return f"TC {'≥' if self.condition == 'tc>=' else '≤'} {signed(self.index)}"


@dataclass
class Cell:
    """One chart cell for the current count: basic action, deviation (if any) and the action to play."""
    kind: str
    row: str
    col: str
    base: str
    deviation: Deviation = None
    active: bool = False

    @property
    def action(self):
        return self.deviation.action if self.deviation and self.active else self.base


@dataclass
class Advice:
    word: str                 # STAND, HIT, DOUBLE, ...
    action: str               # chart code of the played action (S, H, D, Ds, Y, SUR, ...)
    fallback: str             # "Double (if not allowed: Hit)" etc., or ""
    is_deviation: bool
    detail: str               # "12 vs 3 · TC ≥ +2" for deviations, else ""
    hand_text: str            # "Hard 12 vs 3"
    watch: dict = None        # nearby deviation not met yet: {"label": "4+", "text": "..."}
    position: dict = field(default_factory=dict)   # chart cell to highlight: kind/row/col


class Strategy:

    def __init__(self, folder=STRATEGY_FOLDER):
        with open(os.path.join(folder, "basic_strategy.json"), encoding="utf-8") as f:
            basic = json.load(f)
        with open(os.path.join(folder, "deviations.json"), encoding="utf-8") as f:
            devs = json.load(f)

        self.columns = basic["dealer_columns"]
        self.tables = basic["tables"]
        self.rules = basic["rules"]
        self.deviations = {(d["table"], d["row"], d["dealer"]): Deviation(**d) for d in devs["plays"]}
        self.insurance_index = devs["insurance"]["index"]

    # ---------- chart access ----------

    def cell(self, kind, row, col, tc_int, running_count):
        base = self.tables[kind][row][self.columns.index(col)]
        deviation = self.deviations.get((kind, row, col))
        active = bool(deviation and deviation.active(tc_int, running_count))
        return Cell(kind, row, col, base, deviation, active)

    def take_insurance(self, tc_int):
        return tc_int >= self.insurance_index

    # ---------- advice ----------

    @staticmethod
    def column_for(upcard):
        return "10" if upcard in ("J", "Q", "K") else upcard

    @staticmethod
    def position(hand_type, value, upcard):
        """Chart row/column for a hand, plus its display text."""
        col = Strategy.column_for(upcard)

        if hand_type == "soft":
            row, text = f"A,{value - 11}", f"Soft {value} (A,{value - 11})"
        elif hand_type == "pair":
            row = "A,A" if value == "A" else "T,T" if value == "10" else f"{value},{value}"
            text = f"Pair {value},{value}"
        else:
            row, text = str(value), f"Hard {value}"

        return {"kind": hand_type, "row": row, "col": col, "text": f"{text} vs {upcard}"}

    def _hard(self, total, col, tc_int, rc):
        if total >= 18:
            return Cell("hard", str(total), col, "S")
        if total < 8:
            return Cell("hard", str(total), col, "H")
        return self.cell("hard", str(total), col, tc_int, rc)

    def advise(self, hand_type, value, upcard, tc_int, running_count, das=True):
        if upcard is None or value is None:
            return None

        pos = self.position(hand_type, value, upcard)
        col, row = pos["col"], pos["row"]
        watch_cells = []
        fallback = None

        if hand_type == "pair":
            cell = self.cell("pair", row, col, tc_int, running_count)
            watch_cells.append(cell)
            if cell.action == "Y" or (cell.action == "Y/N" and das):
                main = cell
            else:
                # Not splitting: play the pair as its hard total
                hard_total = 20 if row == "T,T" else 12 if row == "A,A" else int(row.split(",")[0]) * 2
                main = self._hard(hard_total, col, tc_int, running_count)
                watch_cells.append(main)
                fallback = f"Don't split · play as hard {hard_total}"
                if main.action in ACTION_FALLBACK:
                    fallback += f" · {ACTION_FALLBACK[main.action]}"

        elif hand_type == "soft":
            main = self.cell("soft", row, col, tc_int, running_count)
            watch_cells.append(main)

        else:
            hard = self._hard(value, col, tc_int, running_count)
            surrender = self.cell("surrender", str(value), col, tc_int, running_count) if value in (15, 16) else None

            if surrender and surrender.action == "SUR":
                # Surrender first; the fallback is what the (deviation-adjusted) hard chart says
                main = surrender
                fallback = f"Surrender (if not allowed: {SHORT_WORD[hard.action]})"
                watch_cells.append(hard)
            elif surrender and surrender.deviation and surrender.active:
                # A deviation turned basic-strategy surrender off: play the hard chart, credit the deviation
                main = Cell("surrender", str(value), col, hard.action, surrender.deviation, True)
            else:
                main = hard
                watch_cells.append(hard)
                if surrender:
                    watch_cells.append(surrender)

        word = ACTION_WORD.get(main.action, "HIT")
        if fallback is None:
            fallback = ACTION_FALLBACK.get(main.action, "")

        is_deviation = bool(main.deviation and main.active)
        row_text = "10,10" if main.row == "T,T" else main.row
        detail = f"{row_text} vs {col} · {main.deviation.condition_text}" if is_deviation else ""

        watch = None
        for c in watch_cells:
            if c is not main and c.deviation and not c.active:
                what = "Surrender" if c.kind == "surrender" and c.deviation.action == "SUR" else SHORT_WORD.get(c.deviation.action, "Deviate")
                watch = {"label": c.deviation.label, "text": f"{what} at {c.deviation.condition_text} (not met)"}
                break
        if watch is None and main.deviation and not main.active:
            what = SHORT_WORD.get(main.deviation.action, "Deviate")
            watch = {"label": main.deviation.label, "text": f"{what} at {main.deviation.condition_text} (not met)"}

        return Advice(
            word=word, action=main.action, fallback=fallback, is_deviation=is_deviation,
            detail=detail, hand_text=pos["text"], watch=watch, position=pos,
        )
