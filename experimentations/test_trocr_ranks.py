import os
import re
import cv2
import torch

from PIL import Image
from transformers import TrOCRProcessor, VisionEncoderDecoderModel


# ============================================================
# CONFIGURATION
# ============================================================
#
# Abandoned experiment: TrOCR read single card ranks poorly (e.g. "7" as
# "12"). Kept for reference; the live pipeline uses utilities/rank_verifier.py.
# ============================================================

MODEL_NAME = "microsoft/trocr-base-printed"

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Verified, labelled cards
TEST_FOLDER = os.path.join(PROJECT_ROOT, "card_templates")

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# Valid blackjack ranks
VALID_RANKS = {
    "2", "3", "4", "5", "6", "7", "8", "9",
    "10", "J", "Q", "K", "A"
}

# ============================================================
# CARD RANK CROP SETTINGS
# ============================================================
#
# These percentages are based on the type of card image
# you supplied.
#
# TOP-LEFT:
#       ┌──────────────────┐
#       │ 2                │
#       │                  │
#       │                  │
#       │                  │
#       │              2   │
#       └──────────────────┘
#
# We crop the corner instead of sending the entire card
# to TrOCR.
#
# These values can be adjusted later.
# ============================================================

TOP_LEFT_X1 = 0.00
TOP_LEFT_Y1 = 0.00
TOP_LEFT_X2 = 0.42
TOP_LEFT_Y2 = 0.55

# ============================================================
# PREPROCESSING
# ============================================================

UPSCALE = 5

# ============================================================
# OUTPUT DIRECTORY
# ============================================================

OUTPUT_FOLDER = os.path.join(PROJECT_ROOT, "trocr_rank_results")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ============================================================
# STARTUP
# ============================================================

print()
print("=" * 60)
print("             TrOCR BLACKJACK RANK TEST")
print("=" * 60)
print()

print(f"[SYSTEM] Device: {DEVICE}")
print(f"[SYSTEM] Model : {MODEL_NAME}")
print()


# ============================================================
# LOAD PROCESSOR
# ============================================================

print("[SYSTEM] Loading TrOCR processor...")

processor = TrOCRProcessor.from_pretrained(
    MODEL_NAME
)

print("[SYSTEM] Processor loaded.")


# ============================================================
# LOAD MODEL
# ============================================================

print("[SYSTEM] Loading TrOCR model...")

model = VisionEncoderDecoderModel.from_pretrained(
    MODEL_NAME
)

model.to(DEVICE)
model.eval()

print("[SYSTEM] TrOCR model loaded.")
print()


# ============================================================
# IMAGE DISCOVERY
# ============================================================

def get_test_images():

    supported_extensions = (
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".webp"
    )

    images = []

    if os.path.exists(TEST_FOLDER):

        for filename in sorted(os.listdir(TEST_FOLDER)):

            if filename.lower().endswith(
                supported_extensions
            ):

                path = os.path.join(
                    TEST_FOLDER,
                    filename
                )

                images.append(path)

    if not images:
        print(f"\n[ERROR] No test images found in {TEST_FOLDER}")

    return images


# ============================================================
# EXPECTED RANK FROM FILENAME
# ============================================================

def get_expected_rank(image_path):

    filename = os.path.basename(
        image_path
    )

    name = os.path.splitext(
        filename
    )[0]

    name = name.upper().strip()

    # Remove common prefixes
    name = re.sub(
        r"^(CARD_|RANK_|TEST_)",
        "",
        name
    )

    if name in VALID_RANKS:
        return name

    # Auto-named by main.py and not yet checked by a human
    if "UNVERIFIED" in name:
        return None

    # Labelled captures: "<RANK>_<suit>_id<N>", e.g. "10_DIAMONDS_ID2"
    first = name.split("_")[0]

    if first in VALID_RANKS:
        return first

    return None


# ============================================================
# CROP TOP-LEFT RANK
# ============================================================

def crop_top_left_rank(image):

    height, width = image.shape[:2]

    x1 = int(width * TOP_LEFT_X1)
    y1 = int(height * TOP_LEFT_Y1)

    x2 = int(width * TOP_LEFT_X2)
    y2 = int(height * TOP_LEFT_Y2)

    crop = image[
        y1:y2,
        x1:x2
    ]

    return crop


# ============================================================
# CROP BOTTOM-RIGHT RANK
# ============================================================
#
# Instead of manually calculating a different crop,
# rotate the card 180 degrees.
#
# Then the bottom-right rank becomes the top-left rank.
# ============================================================

def crop_bottom_right_rank(image):

    rotated = cv2.rotate(
        image,
        cv2.ROTATE_180
    )

    return crop_top_left_rank(
        rotated
    )


# ============================================================
# PREPROCESS VARIANTS
# ============================================================

def create_preprocessing_variants(rank_crop):

    variants = {}

    if rank_crop is None:
        return variants

    if rank_crop.size == 0:
        return variants

    # --------------------------------------------------------
    # Variant 1: Original color
    # --------------------------------------------------------

    rgb = cv2.cvtColor(
        rank_crop,
        cv2.COLOR_BGR2RGB
    )

    rgb_upscaled = cv2.resize(
        rgb,
        None,
        fx=UPSCALE,
        fy=UPSCALE,
        interpolation=cv2.INTER_CUBIC
    )

    variants["RGB"] = rgb_upscaled


    # --------------------------------------------------------
    # Variant 2: Grayscale
    # --------------------------------------------------------

    gray = cv2.cvtColor(
        rank_crop,
        cv2.COLOR_BGR2GRAY
    )

    gray_upscaled = cv2.resize(
        gray,
        None,
        fx=UPSCALE,
        fy=UPSCALE,
        interpolation=cv2.INTER_CUBIC
    )

    gray_rgb = cv2.cvtColor(
        gray_upscaled,
        cv2.COLOR_GRAY2RGB
    )

    variants["GRAY"] = gray_rgb


    # --------------------------------------------------------
    # Variant 3: OTSU binary
    # --------------------------------------------------------

    _, binary = cv2.threshold(
        gray_upscaled,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    binary_rgb = cv2.cvtColor(
        binary,
        cv2.COLOR_GRAY2RGB
    )

    variants["OTSU"] = binary_rgb


    # --------------------------------------------------------
    # Variant 4: Adaptive threshold
    # --------------------------------------------------------

    adaptive = cv2.adaptiveThreshold(
        gray_upscaled,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        21,
        5
    )

    adaptive_rgb = cv2.cvtColor(
        adaptive,
        cv2.COLOR_GRAY2RGB
    )

    variants["ADAPTIVE"] = adaptive_rgb


    return variants


# ============================================================
# RUN TROCR
# ============================================================

def run_trocr(image_rgb):

    pil_image = Image.fromarray(
        image_rgb
    ).convert("RGB")

    pixel_values = processor(
        images=pil_image,
        return_tensors="pt"
    ).pixel_values

    pixel_values = pixel_values.to(
        DEVICE
    )

    with torch.no_grad():

        generated_ids = model.generate(
            pixel_values,
            max_new_tokens=5,
            num_beams=3
        )

    text = processor.batch_decode(
        generated_ids,
        skip_special_tokens=True
    )[0]

    text = text.strip().upper()

    return text


# ============================================================
# NORMALIZE OCR RESULT
# ============================================================

def normalize_rank(text):

    if not text:
        return ""

    text = text.strip().upper()

    # Remove spaces
    text = text.replace(
        " ",
        ""
    )

    # Exact valid result
    if text in VALID_RANKS:
        return text

    # Common OCR representations
    replacements = {
        "TEN": "10",
        "T": "10",
    }

    if text in replacements:
        return replacements[text]

    # Sometimes OCR returns punctuation
    cleaned = re.sub(
        r"[^A-Z0-9]",
        "",
        text
    )

    if cleaned in VALID_RANKS:
        return cleaned

    if cleaned in replacements:
        return replacements[cleaned]

    return cleaned


# ============================================================
# SAVE DEBUG IMAGE
# ============================================================

def save_debug_image(
    image,
    filename
):

    path = os.path.join(
        OUTPUT_FOLDER,
        filename
    )

    cv2.imwrite(
        path,
        image
    )

    return path


# ============================================================
# TEST ONE CARD
# ============================================================

def test_card(image_path):

    print()
    print("=" * 60)
    print(
        f"[TEST] {os.path.basename(image_path)}"
    )
    print("=" * 60)

    image = cv2.imread(
        image_path
    )

    if image is None:

        print(
            "[ERROR] Could not load image."
        )

        return None


    height, width = image.shape[:2]

    print(
        f"[IMAGE] Size: {width} x {height}"
    )


    expected = get_expected_rank(
        image_path
    )

    if expected:

        print(
            f"[EXPECTED] {expected}"
        )

    else:

        print(
            "[EXPECTED] Unknown "
            "(filename does not specify a rank)"
        )


    # ========================================================
    # TOP-LEFT
    # ========================================================

    top_left = crop_top_left_rank(
        image
    )

    top_left_path = save_debug_image(
        top_left,
        f"{os.path.splitext(os.path.basename(image_path))[0]}_top_left.png"
    )

    print(
        f"[DEBUG] Top-left crop saved:"
    )

    print(
        f"        {top_left_path}"
    )


    # ========================================================
    # BOTTOM-RIGHT
    # ========================================================

    bottom_right = crop_bottom_right_rank(
        image
    )

    bottom_right_path = save_debug_image(
        bottom_right,
        f"{os.path.splitext(os.path.basename(image_path))[0]}_bottom_right.png"
    )

    print(
        f"[DEBUG] Bottom-right crop saved:"
    )

    print(
        f"        {bottom_right_path}"
    )


    # ========================================================
    # RUN BOTH CORNERS
    # ========================================================

    all_results = []

    for corner_name, rank_crop in [
        ("TOP-LEFT", top_left),
        ("BOTTOM-RIGHT", bottom_right)
    ]:

        print()
        print(
            f"--- {corner_name} ---"
        )

        variants = create_preprocessing_variants(
            rank_crop
        )

        corner_results = {}

        for variant_name, variant_image in variants.items():

            # Save processed image
            debug_filename = (
                f"{os.path.splitext(os.path.basename(image_path))[0]}"
                f"_{corner_name.lower().replace('-', '_')}"
                f"_{variant_name.lower()}.png"
            )

            debug_path = save_debug_image(
                cv2.cvtColor(
                    variant_image,
                    cv2.COLOR_RGB2BGR
                ),
                debug_filename
            )

            # OCR
            raw_text = run_trocr(
                variant_image
            )

            normalized = normalize_rank(
                raw_text
            )

            corner_results[
                variant_name
            ] = normalized

            print(
                f"{variant_name:10s} -> "
                f"Raw: '{raw_text}' "
                f"| Normalized: '{normalized}'"
            )

        all_results.append(
            (
                corner_name,
                corner_results
            )
        )


    return {
        "expected": expected,
        "results": all_results
    }


# ============================================================
# SUMMARY
# ============================================================

def print_summary(results):

    print()
    print()
    print("=" * 70)
    print("                         FINAL SUMMARY")
    print("=" * 70)

    for image_name, result in results:

        expected = result["expected"]

        print()
        print(
            f"IMAGE: {image_name}"
        )

        print(
            f"EXPECTED: {expected if expected else 'UNKNOWN'}"
        )

        for corner_name, corner_results in result["results"]:

            print()
            print(
                f"  {corner_name}:"
            )

            for variant_name, prediction in corner_results.items():

                if expected:

                    if prediction == expected:

                        status = "PASS"

                    else:

                        status = "FAIL"

                else:

                    status = "N/A"

                print(
                    f"    {variant_name:10s} "
                    f"-> {prediction:5s} "
                    f"[{status}]"
                )

    print()
    print("=" * 70)
    print("[SYSTEM] Test complete.")
    print("=" * 70)
    print()


# ============================================================
# MAIN
# ============================================================

def main():

    image_paths = get_test_images()

    if not image_paths:
        return


    print()
    print(
        f"[SYSTEM] Found {len(image_paths)} test image(s)."
    )


    results = []

    for image_path in image_paths:

        result = test_card(
            image_path
        )

        if result is not None:

            results.append(
                (
                    os.path.basename(image_path),
                    result
                )
            )


    print_summary(
        results
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()