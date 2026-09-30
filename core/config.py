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

REQUIRED_STABLE_FRAMES = 5   # frames a card must stay in the zone before it is counted
MISS_TOLERANCE = 3           # missed frames tolerated before a card's progress resets

# A new card landing on the same spot can inherit an already-counted tracker ID.
# Such an ID is counted again once YOLO's class AND the rank glyph have both changed
# for NEW_CARD_FRAMES frames. Measured: same-rank glyphs >= 0.87, different ranks <= 0.63.
NEW_CARD_SIMILARITY = 0.75
NEW_CARD_FRAMES = 3

# The verifier overrules YOLO when YOLO is unsure, or when the verifier is very sure
YOLO_TRUST_CONF = 0.80
VERIFIER_STRONG_SCORE = 0.90
VERIFIER_STRONG_MARGIN = 0.25
