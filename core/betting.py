"""
Bet spread calculator: bet ramps and EV / standard deviation / risk-of-ruin ESTIMATES.

The estimates combine
  - how often each true count occurs (simulated shoes for the chosen decks / penetration),
  - an edge per true count: base edge for the rules + ~0.5% per true count,
  - a fixed variance per hand (1.32 units², 3.6 for two spots).
They are close to, but not the same as, a full hand-by-hand simulation.
"""
import math
from functools import lru_cache

import numpy as np

TC_INDEXES = list(range(-3, 8))     # ramp rows: <=-3 ... +7 (+7 means 7 and above)

SPREAD_PRESETS = ["1–5", "1–8", "1–8 (2 spots)", "1–10", "1–10 (2 spots)",
                  "1–12", "1–12 (2 spots)", "1–20", "1–20 (2 spots)"]

CARDS_PER_ROUND = 5          # one player + dealer, roughly
VARIANCE_ONE_HAND = 1.32
VARIANCE_TWO_HANDS = 3.6


def preset_ramp(spread, unit):
    """Bets and hands per true count for a spread preset, e.g. "1–12" with a $10 unit."""
    top = int(spread.split("–")[1].split()[0])
    two_spots = "2 spots" in spread
    bets, hands = {}, {}

    for tc in TC_INDEXES:
        if tc <= 1:
            units = 1
        elif tc == 2:
            units = max(2, round(top / 3))
        elif tc == 3:
            units = round(2 * top / 3)
        else:
            units = top
        bets[tc] = units * unit
        hands[tc] = 2 if two_spots and tc >= 2 else 1

    return bets, hands


def ramp_bet(bets, tc_int):
    return bets[max(TC_INDEXES[0], min(TC_INDEXES[-1], tc_int))]


@lru_cache(maxsize=32)
def true_count_frequencies(decks, decks_behind_cut, shoes=3000, seed=1):
    """For each ramp row (-3..+7): share of rounds played there, and the average exact true count in it.

    Rows use the whole-number true count like the live bet decision (nearest, halves away from zero),
    so row +2 covers 1.5..2.49.
    """
    rng = np.random.default_rng(seed)
    one_deck = np.array([1] * 20 + [0] * 12 + [-1] * 20, dtype=np.int8)   # Hi-Lo values of 52 cards
    shoe = np.tile(one_deck, int(round(decks)))
    total = len(shoe)
    cut = max(CARDS_PER_ROUND, int((decks - decks_behind_cut) * 52))

    starts = np.arange(0, cut, CARDS_PER_ROUND)                        # cards seen when each round starts
    counts = np.zeros(len(TC_INDEXES))
    tc_sums = np.zeros(len(TC_INDEXES))

    for _ in range(shoes // 500):
        batch = np.array([rng.permutation(shoe) for _ in range(500)])
        running = np.concatenate([np.zeros((500, 1), np.int32), np.cumsum(batch, axis=1)], axis=1)[:, starts]
        exact = running / ((total - starts) / 52)
        shown = np.round(exact, 1)
        whole = (np.sign(shown) * np.floor(np.abs(shown) + 0.5)).astype(int)
        rows = np.clip(whole, TC_INDEXES[0], TC_INDEXES[-1]) - TC_INDEXES[0]
        counts += np.bincount(rows.ravel(), minlength=len(TC_INDEXES))
        tc_sums += np.bincount(rows.ravel(), weights=exact.ravel(), minlength=len(TC_INDEXES))

    share = counts / counts.sum()
    mean_tc = np.where(counts > 0, tc_sums / np.maximum(counts, 1), TC_INDEXES)
    return {tc: (float(share[i]), float(mean_tc[i])) for i, tc in enumerate(TC_INDEXES)}


def base_edge(rules):
    """Player edge at true count 0 for the table rules (8-deck S17 DAS LS baseline ~ -0.45%)."""
    edge = -0.0045
    if rules.get("h17"):
        edge -= 0.002
    if not rules.get("das", True):
        edge -= 0.0014
    if rules.get("surrender") == "None":
        edge -= 0.0008
    if rules.get("payout") == "6:5":
        edge -= 0.014
    elif rules.get("payout") == "1:1":
        edge -= 0.023
    if rules.get("enhc"):
        edge -= 0.0011
    if rules.get("rsa", "No re-split aces") != "No re-split aces":
        edge += 0.0008
    edge += (rules.get("decks", 8) - 8) * -0.0002
    return edge


def estimate(bets, hands, rules, bankroll, rounds_per_hour, mode="Career", trip_hours=0):
    """EV/hr, SD/hr, risk of ruin and hours to N-0 for a ramp."""
    freq = true_count_frequencies(rules.get("decks", 8), rules.get("behind_cut", 2))
    slope = 0.0042 if rules.get("deviations") == "None" else 0.005
    edge0 = base_edge(rules)

    ev = var = 0.0   # per round, in dollars
    for tc in TC_INDEXES:
        share, mean_tc = freq[tc]
        bet, h = float(bets.get(tc, 0) or 0), hands.get(tc, 1)
        ev += share * bet * (edge0 + slope * mean_tc) * h
        var += share * bet * bet * (VARIANCE_TWO_HANDS if h == 2 else VARIANCE_ONE_HAND)

    rph = max(1.0, float(rounds_per_hour or 1))
    ev_hour, sd_hour = ev * rph, math.sqrt(var * rph)

    if mode == "Trip" and trip_hours > 0:
        ror = trip_risk_of_ruin(ev_hour, sd_hour, bankroll, trip_hours)
    else:
        ror = math.exp(-2 * ev * bankroll / var) if ev > 0 and var > 0 else 1.0

    n0_hours = var / (ev * ev) / rph if ev > 0 else math.inf
    return {"ev_hour": ev_hour, "sd_hour": sd_hour, "ror": ror, "n0_hours": n0_hours}


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def trip_risk_of_ruin(ev_hour, sd_hour, bankroll, hours):
    """Chance of losing the whole bankroll within `hours` (Brownian motion with drift)."""
    if sd_hour <= 0 or bankroll <= 0:
        return 1.0 if bankroll <= 0 else 0.0
    mu_t, sd_t = ev_hour * hours, sd_hour * math.sqrt(hours)
    first = _phi((-bankroll - mu_t) / sd_t)
    exponent = -2 * ev_hour * bankroll / (sd_hour ** 2)
    second = math.exp(exponent) * _phi((-bankroll + mu_t) / sd_t) if exponent < 700 else 0.0
    return min(1.0, first + second)


def simulate_paths(ev_hour, sd_hour, bankroll, hours, players, seed):
    """Bankroll paths per hour (ruined players stay at 0)."""
    rng = np.random.default_rng(seed)
    hours = int(max(10, min(5000, hours)))
    step = max(1, math.ceil(hours / 400))
    t = np.arange(0, hours + 1, step)
    paths = []

    for _ in range(max(1, players)):
        steps = ev_hour * step + sd_hour * math.sqrt(step) * rng.standard_normal(len(t) - 1)
        values = [float(bankroll)]
        for s in steps:
            values.append(0.0 if values[-1] <= 0 else max(0.0, values[-1] + s))
        paths.append(np.array(values))

    return t, paths
