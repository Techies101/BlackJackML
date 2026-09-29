import os
import cv2
import torch

from PIL import Image
from transformers import AutoTokenizer, TrOCRProcessor, VisionEncoderDecoderModel


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

IMAGE_PATH = os.path.join(PROJECT_ROOT, "card_templates", "3_clubs_id4_20260930-011346.png")

MODEL_NAME = "microsoft/trocr-base-printed"

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"[SYSTEM] Device: {DEVICE}")
print("[SYSTEM] Loading TrOCR...")


# ============================================================
# LOAD MODEL
# ============================================================

# Slow tokenizer, passed explicitly into the processor
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, use_fast=False)
processor = TrOCRProcessor.from_pretrained(MODEL_NAME, tokenizer=tokenizer)

model = VisionEncoderDecoderModel.from_pretrained(
    MODEL_NAME
)

model.to(DEVICE)
model.eval()

print("[SYSTEM] TrOCR loaded successfully.")


# ============================================================
# LOAD IMAGE
# ============================================================

image = cv2.imread(IMAGE_PATH)

if image is None:
    raise FileNotFoundError(IMAGE_PATH)

print(f"[SYSTEM] Image size: {image.shape[1]}x{image.shape[0]}")


# ============================================================
# MANUAL RANK CROP FOR INITIAL TEST
# ============================================================
#
# Looking at your supplied image:
#
# The top-left "2" is approximately here.
#
# x = 45 → 115
# y = 15 → 75
#
# We intentionally DON'T send the club symbol.
# ============================================================

rank_crop = image[10:80, 40:120]


# ============================================================
# PREPROCESS
# ============================================================

gray = cv2.cvtColor(rank_crop, cv2.COLOR_BGR2GRAY)

# Upscale substantially
scale = 5

upscaled = cv2.resize(
    gray,
    None,
    fx=scale,
    fy=scale,
    interpolation=cv2.INTER_CUBIC
)


# Threshold
binary = cv2.threshold(
    upscaled,
    0,
    255,
    cv2.THRESH_BINARY + cv2.THRESH_OTSU
)[1]


# Convert back to RGB
rgb = cv2.cvtColor(
    binary,
    cv2.COLOR_GRAY2RGB
)


# ============================================================
# SAVE DEBUG IMAGE
# ============================================================

cv2.imwrite(
    "trocr_rank_crop.png",
    rgb
)

print("[SYSTEM] Saved trocr_rank_crop.png")


# ============================================================
# PIL
# ============================================================

pil_image = Image.fromarray(rgb)


# ============================================================
# TR OCR
# ============================================================

pixel_values = processor(
    images=pil_image,
    return_tensors="pt"
).pixel_values

pixel_values = pixel_values.to(DEVICE)


with torch.no_grad():

    generated_ids = model.generate(
        pixel_values,
        max_new_tokens=5
    )


# ============================================================
# DECODE
# ============================================================

text = processor.batch_decode(
    generated_ids,
    skip_special_tokens=True
)[0]


text = text.strip().upper()


print()
print("========================================")
print("TrOCR RESULT")
print("========================================")
print(f"Raw result: '{text}'")
print("========================================")