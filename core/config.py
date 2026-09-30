"""Paths and tuning constants shared by the capture pipeline and the UI."""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_PATH = os.path.join(PROJECT_ROOT, "current_models", "blackjack_model_v0.4.pt")

# TensorRT engine to use: "fp32" (matches the .pt exactly) or "fp16" (faster, confidences differ by up to ~0.04).
# Built by utilities/export_tensorrt.py; without a matching engine, the .pt model is used.
ENGINE_PRECISION = "fp32"
ENGINE_PATH = f"{os.path.splitext(MODEL_PATH)[0]}.{ENGINE_PRECISION}.engine"

MASK_PATH = os.path.join(PROJECT_ROOT, "utilities", "mask1.png")

# New captures, named "<RANK>_unverified[_yolo<RANK>]_id<N>_<time>.png" until a human checks them
CROP_FOLDER = os.path.join(PROJECT_ROOT, "captured_cards")
# Human-verified cards, named "<RANK>_<suit>_id<N>_<time>.png"; loaded as verifier templates at startup
TEMPLATE_FOLDER = os.path.join(PROJECT_ROOT, "card_templates")

SETTINGS_PATH = os.path.join(PROJECT_ROOT, "settings.json")

# Defaults; both can be changed in the app (Capture area button, dragging the yellow zone) and are saved
CAPTURE_REGION = {"left": 690, "top": 175, "width": 640, "height": 640}
FRAME_SIZE = 640
ZONE = (230, 540, 350, 625)  # x1, y1, x2, y2 of the counting zone, in feed pixels

# YOLO only sees the zone plus this margin (left, top, right, bottom); the rest of the frame is
# blacked out. These margins reproduce the original utilities/mask1.png for the default zone.
MASK_MARGIN = (2, 3, 2, 1)

DETECTION_CONF = 0.45
DETECTION_IOU = 0.45

# Counting rules are time-based so they hold at any frame rate. Cards sit in the zone for only ~1 s before
# the dealer slides them away, and the live FPS drops to 6-12 while the game video plays and the screen is
# recorded; frame-count rules then missed ~35% of cards (22-minute recording, 2026-09-30).
REQUIRED_STABLE_SECONDS = 0.4   # a card must be in the zone this long (lets the dealer's hand move off it)...
REQUIRED_STABLE_FRAMES = 3      # ...and be seen at least this many times. Every settling frame is read; the best is used.
MISS_TOLERANCE_SECONDS = 0.35   # a card missing from the zone for longer than this loses its settling progress
# A settling card that leaves before REQUIRED_STABLE_SECONDS is still counted on exit if it was seen at least
# EXIT_MIN_FRAMES times with a confident verifier read or a steady YOLO class (a card flashing past is ignored)
EXIT_MIN_FRAMES = 2
EXIT_MIN_YOLO_CONF = 0.80

# A new card landing on the same spot can inherit an already-counted tracker ID.
# Such an ID is counted again once YOLO's class AND the rank glyph have both changed
# for NEW_CARD_FRAMES frames and NEW_CARD_SECONDS; those frames already count toward the new card's settling.
# Measured: same-rank glyphs >= 0.87, different ranks <= 0.63.
NEW_CARD_SIMILARITY = 0.75
NEW_CARD_FRAMES = 2
NEW_CARD_SECONDS = 0.2   # ...and for at least this long: a finger sliding a card away looks "different" for ~0.07 s

# Warn (at most every STALL_REPORT_SECONDS) when frames arrive more than STALL_WARN_SECONDS apart
STALL_WARN_SECONDS = 0.5
STALL_REPORT_SECONDS = 10

# Stop re-reading a settling card with the verifier once it has a read this good (saves ~12 ms per frame)
VERIFIER_ENOUGH_SCORE = 0.90

# The verifier overrules YOLO when YOLO is unsure, or when the verifier is very sure
YOLO_TRUST_CONF = 0.80
# "Strong" verifier read (overrules even a confident YOLO): score and lead over the next rank. Correct reads
# score ~0.87-0.97 while a wrong rank has never scored above 0.63; one readable corner is enough.
VERIFIER_STRONG_SCORE = 0.85
VERIFIER_STRONG_MARGIN = 0.25
