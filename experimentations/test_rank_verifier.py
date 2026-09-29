import os
import sys
import cv2
import numpy as np


# ============================================================
# CONFIGURATION
# ============================================================
#
# Offline test of the straightened-card rank verifier
# (utilities/rank_verifier.py, the same code main.py uses).
#
# Reads every card in card_templates/ and writes per-step debug images
# to rank_verifier_results/. Files still marked "unverified" are read
# but not scored.
# ============================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from utilities.rank_verifier import (
    HILO_GROUP,
    VALID_RANKS,
    classify_glyph,
    get_expected_rank,
    read_both_corners,
    straighten_card,
)

# Verified, labelled cards (the same templates main.py uses)
TEST_FOLDER = os.path.join(PROJECT_ROOT, "card_templates")
OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, "rank_verifier_results")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def evaluate(cards, templates, title, make_skip):

    print()
    print("=" * 70)
    print(f" {title}")
    print("=" * 70)

    exact_hits = group_hits = scored = 0

    for name, expected, corners in cards:

        print()
        print(f"--- {name}  (expected: {expected or 'UNKNOWN'}) ---")

        votes = []

        for corner, (glyph, _) in corners.items():

            if glyph is None:
                print(f"  {corner:12s} -> no glyph found")
                continue

            rank, score, margin = classify_glyph(
                glyph, templates, make_skip(name, corner)
            )
            votes.append((rank, score))

            print(
                f"  {corner:12s} -> {str(rank):3s} "
                f"score {score:.2f}  margin {margin:.2f}"
            )

        # Both corners should agree; if not, trust the stronger match
        final = max(votes, key=lambda v: v[1])[0] if votes else None
        agree = len(votes) == 2 and votes[0][0] == votes[1][0]

        print(f"  FINAL        -> {final}  ({'corners agree' if agree else 'corners DISAGREE'})")

        if not (expected and final):
            continue

        # Skip ranks that have no allowed template to match against
        if not any(
            t[0] == expected and not make_skip(name, c)(t[1], t[2])
            for t in templates for c in corners
        ):
            print(f"  [SKIP] No other labelled '{expected}' to compare with")
            continue

        scored += 1
        rank_ok = final == expected
        group_ok = HILO_GROUP.get(final) == HILO_GROUP[expected]
        exact_hits += rank_ok
        group_hits += group_ok

        print(
            f"  RESULT       -> rank {'PASS' if rank_ok else 'FAIL'}, "
            f"Hi-Lo group {'PASS' if group_ok else 'FAIL'}"
        )

    print()

    if scored:
        print(f"  Exact rank accuracy : {exact_hits}/{scored}")
        print(f"  Hi-Lo group accuracy: {group_hits}/{scored}")
    else:
        print("  Nothing to score.")


# ============================================================
# MAIN
# ============================================================

def main():

    paths = sorted(
        os.path.join(TEST_FOLDER, f)
        for f in os.listdir(TEST_FOLDER)
        if f.lower().endswith((".png", ".jpg", ".jpeg", ".bmp"))
    )

    if not paths:
        print(f"[ERROR] No images in {TEST_FOLDER}")
        return

    print()
    print("=" * 70)
    print("             STRAIGHTENED-CARD RANK VERIFIER")
    print("=" * 70)

    # ---- Pass 1: straighten every card and cut its glyphs ----

    cards = []
    templates = []

    for path in paths:

        name = os.path.splitext(os.path.basename(path))[0]
        image = cv2.imread(path)

        if image is None:
            print(f"[ERROR] Could not load {path}")
            continue

        result = straighten_card(image)

        if result is None:
            print(f"[ERROR] No card outline found in {name}")
            continue

        card, quad = result
        corners = read_both_corners(card)
        expected = get_expected_rank(path)

        # Debug images: outline on the input, straightened card, corner crops
        outline = image.copy()
        cv2.polylines(outline, [quad.astype(np.int32)], True, (0, 0, 255), 2)
        cv2.circle(outline, tuple(quad[0].astype(int)), 5, (0, 255, 0), -1)
        cv2.imwrite(os.path.join(OUTPUT_FOLDER, f"{name}_0_outline.png"), outline)
        cv2.imwrite(os.path.join(OUTPUT_FOLDER, f"{name}_1_straight.png"), card)

        for corner, (glyph, roi) in corners.items():

            tag = corner.lower().replace("-", "_")
            cv2.imwrite(os.path.join(OUTPUT_FOLDER, f"{name}_2_{tag}_roi.png"), roi)

            if glyph is not None:
                cv2.imwrite(os.path.join(OUTPUT_FOLDER, f"{name}_3_{tag}_glyph.png"), glyph)

                if expected:
                    templates.append((expected, name, corner, glyph))

        cards.append((name, expected, corners))

    known_ranks = sorted({t[0] for t in templates}, key=VALID_RANKS.index)

    print()
    print(f"[SYSTEM] Cards read     : {len(cards)}")
    print(f"[SYSTEM] Template ranks : {', '.join(known_ranks) or 'none'}")

    # ---- Pass 2: never match a card against itself (honest, but
    #      only ranks with 2+ labelled cards can be scored) ----

    evaluate(
        cards, templates,
        "TEST 1: LEAVE-ONE-CARD-OUT (realistic)",
        lambda name, corner: lambda src, crn: src == name
    )

    # ---- Pass 3: a corner may match the OTHER corner of the same
    #      card (optimistic: checks glyph extraction consistency) ----

    evaluate(
        cards, templates,
        "TEST 2: CROSS-CORNER (optimistic - may match the same card's other corner)",
        lambda name, corner: lambda src, crn: src == name and crn == corner
    )

    print()
    print("=" * 70)
    print(f"Debug images        : {OUTPUT_FOLDER}")
    print("=" * 70)
    print()


if __name__ == "__main__":

    main()
