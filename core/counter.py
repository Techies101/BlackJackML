"""
Running count, cards dealt, burned cards and their history for the current shoe.

Shared between the capture thread (adds cards) and the UI (undo, ±1 corrections,
burns, new shoe), so every access goes through a lock.

Burned cards: face-down burns are unknown, so they only reduce the cards left in the
shoe (true count and penetration); face-up burns are counted like dealt cards.
"""
import itertools
import threading

from core.strategy import true_count_int
from utilities.rank_verifier import HILO_VALUE


def decks_remaining(decks_in_shoe, cards_gone):
    # Never below a quarter deck, so the true count stays finite at the end of a shoe
    return max(0.25, (decks_in_shoe * 52 - cards_gone) / 52)


class ShoeCounter:

    def __init__(self):
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self.running_count = 0
        self.cards_dealt = 0
        self.burned_down = 0
        self.burned_up = []          # [{"id": int, "rank": str}]
        self.last_burned_down = 0    # suggestion for the next shoe
        self._history = []           # {"kind": "card"|"adjust"|"burn_down"|"burn_up", ...}

    def add_card(self, rank, text):
        value = HILO_VALUE.get(rank, 0)
        with self._lock:
            self.running_count += value
            self.cards_dealt += 1
            self._history.append({"kind": "card", "delta": value, "text": text})

    def adjust(self, delta):
        with self._lock:
            self.running_count += delta
            self._history.append({"kind": "adjust", "delta": delta, "text": f"Manual {delta:+d}"})

    def set_burned_down(self, count):
        count = max(0, int(count))
        with self._lock:
            if count == self.burned_down:
                return
            self._history.append({"kind": "burn_down", "previous": self.burned_down,
                                  "text": f"Face-down burn {self.burned_down} -> {count}"})
            self.burned_down = count
            if count:
                self.last_burned_down = count

    def add_burned_up(self, rank):
        value = HILO_VALUE.get(rank, 0)
        with self._lock:
            entry_id = next(self._ids)
            self.burned_up.append({"id": entry_id, "rank": rank})
            self.running_count += value
            self._history.append({"kind": "burn_up", "id": entry_id, "delta": value,
                                  "text": f"Face-up burn {rank} ({value:+d})"})

    def remove_burned_up(self, entry_id):
        with self._lock:
            entry = next((b for b in self.burned_up if b["id"] == entry_id), None)
            if entry is None:
                return
            self.burned_up.remove(entry)
            self.running_count -= HILO_VALUE.get(entry["rank"], 0)
            self._history = [h for h in self._history if not (h["kind"] == "burn_up" and h["id"] == entry_id)]

    def undo(self):
        """Take back the last card, correction or burn entry. Returns what was undone, or None."""
        with self._lock:
            if not self._history:
                return None
            last = self._history.pop()
            if last["kind"] == "burn_down":
                self.burned_down = last["previous"]
            elif last["kind"] == "burn_up":
                self.running_count -= last["delta"]
                self.burned_up = [b for b in self.burned_up if b["id"] != last["id"]]
            else:
                self.running_count -= last["delta"]
                if last["kind"] == "card":
                    self.cards_dealt -= 1
            return last

    def new_shoe(self):
        with self._lock:
            self.running_count = 0
            self.cards_dealt = 0
            self.burned_down = 0
            self.burned_up = []
            self._history.clear()

    def snapshot(self, decks_in_shoe):
        with self._lock:
            rc, dealt = self.running_count, self.cards_dealt
            burned_down, burned_up = self.burned_down, list(self.burned_up)
            last = next((h["text"] for h in reversed(self._history) if h["kind"] == "card"), None)

        burned = burned_down + len(burned_up)
        decks_left = decks_remaining(decks_in_shoe, dealt + burned)
        tc = rc / decks_left
        return {
            "running_count": rc,
            "cards_dealt": dealt,
            "burned_down": burned_down,
            "burned_up": burned_up,
            "burned": burned,
            "cards_gone": dealt + burned,
            "decks_left": decks_left,
            "true_count": tc,
            "tc_int": true_count_int(tc),
            "last_card": last,
        }
