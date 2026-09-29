import os
import cv2
import numpy as np


# ============================================================
# STRAIGHTENED-CARD RANK VERIFIER
# ============================================================
#
# Second opinion on a card's rank, independent of YOLO:
#
#   1. Find the card outline and straighten it (perspective warp)
#   2. Crop the rank index from the top-left AND bottom-right corner
#      (the bottom-right one is rotated upright, so 6 and 9 never mix)
#   3. Match each rank glyph against templates cut from labelled cards
#
# Templates come from labelled images named "<RANK>_<suit>_id<N>...png",
# e.g. "10_diamonds_id2.png". Files still marked "unverified" are skipped.
# ============================================================

VALID_RANKS = [
    "2", "3", "4", "5", "6", "7", "8", "9",
    "10", "J", "Q", "K", "A"
]

HILO_VALUE = {
    **{r: +1 for r in ["2", "3", "4", "5", "6"]},
    **{r: 0 for r in ["7", "8", "9"]},
    **{r: -1 for r in ["10", "J", "Q", "K", "A"]},
}

HILO_GROUP = {
    rank: {1: "LOW (+1)", 0: "NEUTRAL (0)", -1: "HIGH (-1)"}[value]
    for rank, value in HILO_VALUE.items()
}

# Straightened card size. The table view shows cards landscape:
#
#       ┌────────────────────┐
#       │  7            ♥    │
#       │                    │
#       │  ♥            L    │
#       └────────────────────┘
#
CARD_W = 280
CARD_H = 200

# Region of the straightened card that holds the rank index,
# as fractions of CARD_W / CARD_H.
RANK_X1 = 0.00
RANK_Y1 = 0.00
RANK_X2 = 0.55
RANK_Y2 = 0.50

# Smallest card outline accepted, as a fraction of the crop area
MIN_CARD_AREA = 0.20

# Pixels painted white around the straightened card to erase the thin
# strip of table that the warp leaves along the edges
EDGE_WIPE = 4

# Every glyph is normalised to this size before matching
GLYPH_W = 40
GLYPH_H = 48

# A match counts only when it is this good AND this far ahead of the
# next-best rank. On the first labelled cards, real matches scored
# 0.78-0.97 while the best WRONG rank never scored above 0.64.
MIN_SCORE = 0.75
MIN_MARGIN = 0.10


# ============================================================
# LABEL FROM FILENAME
# ============================================================

def get_expected_rank(image_path):

    name = os.path.splitext(os.path.basename(image_path))[0].upper()

    # Auto-named by main.py and not yet checked by a human
    if "UNVERIFIED" in name:
        return None

    first = name.split("_")[0]

    if first in VALID_RANKS:
        return first

    return None


# ============================================================
# CARD STRAIGHTENING
# ============================================================

def binarize(image):

    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # White card face on dark table -> card = 255
    _, binary = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    return binary


def find_card_quad(binary):

    # Close the pips/rank holes so the outline is one solid blob
    solid = cv2.morphologyEx(
        binary, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8)
    )

    contours, _ = cv2.findContours(
        solid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    if not contours:
        return None

    card = max(contours, key=cv2.contourArea)

    # A real card fills most of its crop (~70%); anything much smaller is noise
    if cv2.contourArea(card) < MIN_CARD_AREA * binary.size:
        return None

    hull = cv2.convexHull(card)
    perimeter = cv2.arcLength(hull, True)

    # Grow epsilon until the outline collapses to 4 corners
    for factor in np.linspace(0.01, 0.10, 19):

        approx = cv2.approxPolyDP(hull, factor * perimeter, True)

        if len(approx) == 4:
            return approx.reshape(4, 2).astype(np.float32)

    # Fallback: rotated bounding box (ignores perspective skew)
    return cv2.boxPoints(cv2.minAreaRect(card)).astype(np.float32)


def order_corners(quad):

    # Order clockwise starting from the corner nearest the image's
    # top-left: [TL, TR, BR, BL]. Cards are skewed by the table
    # perspective but never turned 90 degrees, so no rotation needed.
    # (A 180-degree turn is harmless: the card looks the same.)
    center = quad.mean(axis=0)
    angles = np.arctan2(quad[:, 1] - center[1], quad[:, 0] - center[0])
    quad = quad[np.argsort(angles)]

    start = np.argmin(quad.sum(axis=1))

    return np.roll(quad, -start, axis=0)


def straighten_card(image):

    binary = binarize(image)
    quad = find_card_quad(binary)

    if quad is None:
        return None

    quad = order_corners(quad)

    target = np.array(
        [[0, 0], [CARD_W - 1, 0], [CARD_W - 1, CARD_H - 1], [0, CARD_H - 1]],
        dtype=np.float32
    )

    matrix = cv2.getPerspectiveTransform(quad, target)

    warped = cv2.warpPerspective(
        binary, matrix, (CARD_W, CARD_H),
        flags=cv2.INTER_NEAREST, borderValue=0
    )

    cv2.rectangle(
        warped, (0, 0), (CARD_W - 1, CARD_H - 1), 255, EDGE_WIPE * 2
    )

    return warped, quad


# ============================================================
# RANK GLYPH EXTRACTION
# ============================================================

def extract_rank_glyph(card):

    h, w = card.shape
    roi = card[
        int(h * RANK_Y1):int(h * RANK_Y2),
        int(w * RANK_X1):int(w * RANK_X2)
    ]

    # Ink = dark pixels on the white card face
    ink = cv2.bitwise_not(roi)

    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink)

    roi_h, roi_w = ink.shape
    keep = np.zeros_like(ink)

    for i in range(1, count):

        x, y, bw, bh, area = stats[i]

        # Drop specks and any leftover table strip along an edge
        if area < 30:
            continue

        if bw > roi_w * 0.85 or bh > roi_h * 0.95:
            continue

        # Suit symbol sits to the right; ignore anything starting there
        if x > roi_w * 0.62:
            continue

        keep[labels == i] = 255

    points = cv2.findNonZero(keep)

    if points is None:
        return None, roi

    x, y, bw, bh = cv2.boundingRect(points)
    glyph = keep[y:y + bh, x:x + bw]

    glyph = cv2.resize(glyph, (GLYPH_W, GLYPH_H), interpolation=cv2.INTER_AREA)

    return glyph, roi


def read_both_corners(card):

    top_left, roi_tl = extract_rank_glyph(card)
    bottom_right, roi_br = extract_rank_glyph(cv2.rotate(card, cv2.ROTATE_180))

    return {
        "TOP-LEFT": (top_left, roi_tl),
        "BOTTOM-RIGHT": (bottom_right, roi_br),
    }


# ============================================================
# TEMPLATE MATCHING
# ============================================================

def glyph_score(a, b):

    # Normalised cross-correlation of two same-size glyphs, in [-1, 1]
    a = a.astype(np.float32) - a.mean()
    b = b.astype(np.float32) - b.mean()

    denom = np.sqrt((a * a).sum() * (b * b).sum())

    if denom == 0:
        return -1.0

    return float((a * b).sum() / denom)


def classify_glyph(glyph, templates, skip=lambda source, corner: False):

    # Best score per rank over every template that `skip` allows.
    # Templates are (rank, card_name, corner, glyph).
    best = {}

    for rank, source, corner, template in templates:

        if skip(source, corner):
            continue

        score = glyph_score(glyph, template)

        if score > best.get(rank, -2.0):
            best[rank] = score

    if not best:
        return None, 0.0, 0.0

    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)

    top_rank, top_score = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else -1.0

    return top_rank, top_score, top_score - runner_up


def load_templates(folder):

    # Rank glyphs from every labelled card image in `folder`
    templates = []

    for filename in sorted(os.listdir(folder)):

        if not filename.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
            continue

        path = os.path.join(folder, filename)
        rank = get_expected_rank(path)

        if rank is None:
            continue

        image = cv2.imread(path)

        if image is None:
            continue

        result = straighten_card(image)

        if result is None:
            continue

        name = os.path.splitext(filename)[0]

        for corner, (glyph, _) in read_both_corners(result[0]).items():

            if glyph is not None:
                templates.append((rank, name, corner, glyph))

    return templates


# ============================================================
# CARD SIGNATURE (did the card under a tracker ID change?)
# ============================================================
#
# The card's rank glyphs (both corners). main.py stores them when it
# counts a card, and compares later frames of the same tracker ID
# against them to spot a NEW card that inherited an already-counted ID.
#
# Rank glyphs, not the whole card: whole cards are mostly white with the
# same layout, so two different cards scored up to 0.90 against each
# other. On 26 labelled cards, glyphs of the same rank scored >= 0.87
# and glyphs of different ranks <= 0.63.

def card_signature(card_image):

    if card_image is None or card_image.size == 0:
        return None

    result = straighten_card(card_image)

    if result is None:
        return None

    glyphs = [g for g, _ in read_both_corners(result[0]).values() if g is not None]

    return glyphs or None


def signature_similarity(a, b):

    # Best match over every corner pairing (a corner may be cut off).
    # ~0.9 = same rank; different ranks score much lower.
    return max(glyph_score(x, y) for x in a for y in b)


# ============================================================
# RUNTIME VERIFIER (used by main.py)
# ============================================================

class RankVerifier:

    def __init__(self, template_folder):

        self.templates = load_templates(template_folder)

        self.known_ranks = sorted(
            {t[0] for t in self.templates}, key=VALID_RANKS.index
        )

    def read(self, card_image):
        """
        Read the rank of one card crop (BGR or grayscale).

        Returns a dict:
            rank       best rank, or None if nothing could be read
            score      match score of that rank (0-1, higher is better)
            margin     lead over the next-best rank
            agree      True if both corners gave the same rank
            confident  True if score/margin pass MIN_SCORE/MIN_MARGIN and
                       the corners do not contradict each other
            corners    per-corner (rank, score, margin)
        """

        empty = {
            "rank": None, "score": 0.0, "margin": 0.0,
            "agree": False, "confident": False, "corners": {},
        }

        if not self.templates or card_image is None or card_image.size == 0:
            return empty

        result = straighten_card(card_image)

        if result is None:
            return empty

        corners = {}

        for corner, (glyph, _) in read_both_corners(result[0]).items():

            if glyph is not None:
                corners[corner] = classify_glyph(glyph, self.templates)

        if not corners:
            return empty

        # Trust the corner with the stronger match
        rank, score, margin = max(corners.values(), key=lambda c: c[1])

        ranks_seen = {c[0] for c in corners.values()}
        agree = len(corners) == 2 and len(ranks_seen) == 1

        confident = (
            score >= MIN_SCORE
            and margin >= MIN_MARGIN
            and len(ranks_seen) == 1   # one corner only, or both agree
        )

        return {
            "rank": rank, "score": score, "margin": margin,
            "agree": agree, "confident": confident, "corners": corners,
        }
