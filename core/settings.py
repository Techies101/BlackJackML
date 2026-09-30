"""User settings saved between sessions in settings.json (shoe setup, bet calculator, ramp)."""
import copy
import json

from core import config
from core.betting import preset_ramp

DEFAULTS = {
    "shoe_decks": 8,
    "behind_cut": 2.0,
    "calculator": {
        "mode": "Career", "bankroll": 10000, "rounds_per_hour": 100, "trip_hours": 50,
        "unit": 10, "spread": "1–12", "deviations": "Standard",
        "h17": False, "das": True, "rsa": "No re-split aces", "splitting": "Max 4 hands",
        "surrender": "Late surrender", "enhc": False, "double_rule": "Any first 2 cards", "payout": "3:2",
    },
    "capture_region": [config.CAPTURE_REGION["left"], config.CAPTURE_REGION["top"]],
    "zone": list(config.ZONE),
    "frozen": False,
    "bets": None,     # filled from the spread preset
    "hands": None,
}


def load():
    settings = copy.deepcopy(DEFAULTS)

    try:
        with open(config.SETTINGS_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        settings.update({k: v for k, v in saved.items() if k != "calculator"})
        settings["calculator"].update(saved.get("calculator", {}))
    except (OSError, ValueError):
        pass

    if not settings["bets"] or not settings["hands"]:
        bets, hands = preset_ramp(settings["calculator"]["spread"], settings["calculator"]["unit"])
        settings["bets"], settings["hands"] = bets, hands

    # JSON keys are strings; the ramp is keyed by true count
    settings["bets"] = {int(k): v for k, v in settings["bets"].items()}
    settings["hands"] = {int(k): v for k, v in settings["hands"].items()}
    return settings


def save(settings):
    try:
        with open(config.SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
