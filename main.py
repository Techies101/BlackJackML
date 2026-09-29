"""
Live Hi-Lo card counter.

Captures a fixed screen region, tracks cards with YOLO, double-checks each
card's rank with the template verifier (utilities/rank_verifier.py) and keeps
the Hi-Lo running count.

Keys in the "Live Feed" window: R = reset the count (new shoe), Q = quit.
"""
import contextlib
import os
import time

import cv2
import mss
import numpy as np

try:
    import dxcam
except ImportError:
    dxcam = None

from utilities.rank_verifier import (
    HILO_GROUP,
    HILO_VALUE,
    RankVerifier,
    card_signature,
    signature_similarity,
)


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
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

CAPTURE_REGION = {"left": 690, "top": 175, "width": 640, "height": 640}
FRAME_SIZE = 640
ZONE = (230, 540, 350, 625)  # x1, y1, x2, y2 of the counting zone

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

COUNTDOWN_SECONDS = 3
WINDOW_NAME = "Live Feed"

COLOR_COUNTED = (0, 255, 0)
COLOR_PENDING = (0, 165, 255)
COLOR_OUTSIDE = (160, 160, 160)


# ============================================================
# STARTUP
# ============================================================

def start_dxcam():
    """Start dxcam capture, or return None so the caller falls back to mss.

    Must run before torch/ultralytics is imported: on Intel + NVIDIA laptops,
    Windows refuses Desktop Duplication in a process that has initialised CUDA.
    """
    if dxcam is None:
        return None

    region = (
        CAPTURE_REGION["left"],
        CAPTURE_REGION["top"],
        CAPTURE_REGION["left"] + CAPTURE_REGION["width"],
        CAPTURE_REGION["top"] + CAPTURE_REGION["height"],
    )

    try:
        camera = dxcam.create(output_color="BGR")
        camera.start(region=region, target_fps=60, video_mode=True)
        return camera
    except Exception as e:
        print(f"[WARNING] dxcam failed ({e}); falling back to mss.")
        return None


def load_model():
    # Imported here, after dxcam has started (see start_dxcam)
    from ultralytics import YOLO

    if ENGINE_PRECISION not in ("fp32", "fp16"):
        raise ValueError(f'ENGINE_PRECISION must be "fp32" or "fp16", not "{ENGINE_PRECISION}"')

    # The engine is only trusted if it was built from the current .pt
    if os.path.exists(ENGINE_PATH) and os.path.getmtime(ENGINE_PATH) >= os.path.getmtime(MODEL_PATH):
        print(f"[SYSTEM] YOLO model: {os.path.basename(ENGINE_PATH)} (TensorRT {ENGINE_PRECISION})")
        return YOLO(ENGINE_PATH, task="detect")

    reason = "is older than the .pt model" if os.path.exists(ENGINE_PATH) else "was not found"
    print(f"[WARNING] {os.path.basename(ENGINE_PATH)} {reason}; using the slower .pt model. "
          f"Build it with: venv\\Scripts\\python utilities\\export_tensorrt.py {ENGINE_PRECISION}")
    print(f"[SYSTEM] YOLO model: {os.path.basename(MODEL_PATH)} (PyTorch)")
    return YOLO(MODEL_PATH).to("cuda")


def load_mask():
    mask = cv2.imread(MASK_PATH, cv2.IMREAD_GRAYSCALE)

    if mask is None:
        return None

    return cv2.resize(mask, (FRAME_SIZE, FRAME_SIZE), interpolation=cv2.INTER_NEAREST)


# ============================================================
# FRAME HELPERS
# ============================================================

def grab_frame(camera, sct):
    if camera is not None:
        frame = camera.get_latest_frame()
        # Copy: dxcam reuses its buffer for later frames
        return None if frame is None else frame.copy()

    shot = sct.grab(CAPTURE_REGION)
    frame = np.frombuffer(shot.rgb, dtype=np.uint8).reshape(shot.height, shot.width, 3)
    return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)


def crop_and_binarize(image, box, padding=5):
    """Crop a card and turn it into the black/white format of the verifier templates."""
    x1, y1, x2, y2 = box
    height, width = image.shape[:2]

    crop = image[max(0, y1 - padding):min(height, y2 + padding),
                 max(0, x1 - padding):min(width, x2 + padding)]

    if crop.size == 0:
        return None

    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    enlarged = cv2.resize(gray, (0, 0), fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(enlarged, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def in_zone(box):
    # Uses the box centre: a card touching the mask edge has its corner outside the zone
    x1, y1, x2, y2 = box
    center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2

    return ZONE[0] <= center_x <= ZONE[2] and ZONE[1] <= center_y <= ZONE[3]


# ============================================================
# COUNTING
# ============================================================

class CountState:

    def __init__(self):
        self.reset()

    def reset(self):
        self.total_cards = 0
        self.running_count = 0
        self.stable_frames = {}      # track id -> frames seen in the zone, not yet counted
        self.missed_frames = {}      # track id -> consecutive frames missing from the zone
        self.counted_ids = set()
        self.counted_class = {}      # track id -> YOLO class when it was counted
        self.counted_signature = {}  # track id -> rank glyphs when it was counted
        self.changed_frames = {}     # track id -> consecutive frames showing a different card


def decide_rank(yolo_rank, yolo_conf, verdict):
    """Return (final rank, who decided) from YOLO's guess and the verifier's reading."""
    verifier_rank = verdict["rank"] if verdict["confident"] else None

    if verifier_rank is None:
        return yolo_rank, "YOLO"

    if verifier_rank == yolo_rank:
        return yolo_rank, "YOLO + verifier agree"

    strong = (
        verdict["agree"]
        and verdict["score"] >= VERIFIER_STRONG_SCORE
        and verdict["margin"] >= VERIFIER_STRONG_MARGIN
    )

    if yolo_conf < YOLO_TRUST_CONF or strong:
        return verifier_rank, "VERIFIER"

    return yolo_rank, "YOLO (verifier disagreed, not strong enough)"


def save_capture(binary_card, final_rank, yolo_rank, disputed, track_id):
    # "_yolo<RANK>" marks cards where the verifier disagreed with YOLO: the ones worth reviewing
    tag = f"_yolo{yolo_rank}" if disputed else ""
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{final_rank}_unverified{tag}_id{track_id}_{timestamp}.png"

    cv2.imwrite(os.path.join(CROP_FOLDER, filename), binary_card)


def count_card(state, verifier, clean_frame, box, track_id, class_name, conf):
    state.total_cards += 1
    state.counted_ids.add(track_id)
    state.counted_class[track_id] = class_name
    state.changed_frames[track_id] = 0
    state.stable_frames.pop(track_id, None)

    binary_card = crop_and_binarize(clean_frame, box)

    signature = card_signature(binary_card)
    if signature is not None:
        state.counted_signature[track_id] = signature

    yolo_rank = class_name.replace("Card-", "").upper()
    verdict = verifier.read(binary_card)
    final_rank, decided_by = decide_rank(yolo_rank, conf, verdict)

    state.running_count += HILO_VALUE.get(final_rank, 0)

    if binary_card is not None:
        disputed = verdict["confident"] and verdict["rank"] != yolo_rank
        save_capture(binary_card, final_rank, yolo_rank, disputed, track_id)

    print("\n==================================================")
    print(f"[DECISION] ID {track_id} -> {final_rank} ({HILO_GROUP.get(final_rank, '?')})")
    print(f"-> YOLO: {yolo_rank} ({conf:.2f}) | Verifier: {verdict['rank']} "
          f"(score {verdict['score']:.2f}, margin {verdict['margin']:.2f}, "
          f"{'confident' if verdict['confident'] else 'not confident'})")
    print(f"-> Decided by: {decided_by} | Running count: {state.running_count:+d}")
    print("==================================================")


def is_new_card(state, track_id, class_name, clean_frame, box):
    """True once a counted track ID has clearly shown a different card for NEW_CARD_FRAMES frames."""
    similarity = None

    # Only look closer when YOLO's class changed; the glyph check filters out YOLO flicker
    if class_name != state.counted_class.get(track_id) and track_id in state.counted_signature:
        signature = card_signature(crop_and_binarize(clean_frame, box))
        if signature is not None:
            similarity = signature_similarity(signature, state.counted_signature[track_id])

    if similarity is not None and similarity < NEW_CARD_SIMILARITY:
        state.changed_frames[track_id] = state.changed_frames.get(track_id, 0) + 1
    else:
        state.changed_frames[track_id] = 0

    if state.changed_frames[track_id] < NEW_CARD_FRAMES:
        return False

    print(f"\n[SYSTEM] ID {track_id} now shows a different card "
          f"({state.counted_class[track_id]} -> {class_name}, similarity {similarity:.2f}); counting it as new.")
    return True


def process_card(state, verifier, clean_frame, box, track_id, class_name, conf):
    """Advance one card that is inside the zone. Returns its on-screen status."""
    state.missed_frames.pop(track_id, None)

    if track_id in state.counted_ids:
        if not is_new_card(state, track_id, class_name, clean_frame, box):
            return "COUNTED"

        state.counted_ids.discard(track_id)
        state.counted_class.pop(track_id, None)
        state.counted_signature.pop(track_id, None)
        state.changed_frames.pop(track_id, None)

    state.stable_frames[track_id] = state.stable_frames.get(track_id, 0) + 1

    if state.stable_frames[track_id] < REQUIRED_STABLE_FRAMES:
        return f"STABLE {state.stable_frames[track_id]}/{REQUIRED_STABLE_FRAMES}"

    count_card(state, verifier, clean_frame, box, track_id, class_name, conf)
    return "COUNTED"


def forget_missing(state, seen_ids):
    # A card only loses its progress after missing more than MISS_TOLERANCE frames in a row
    for track_id in list(state.stable_frames):
        if track_id in seen_ids:
            continue

        state.missed_frames[track_id] = state.missed_frames.get(track_id, 0) + 1

        if state.missed_frames[track_id] > MISS_TOLERANCE:
            del state.stable_frames[track_id]
            del state.missed_frames[track_id]


# ============================================================
# DRAWING
# ============================================================

def draw_card(frame, box, label, status):
    x1, y1, x2, y2 = box

    if status == "COUNTED":
        color = COLOR_COUNTED
    elif status == "OUTSIDE ZONE":
        color = COLOR_OUTSIDE
    else:
        color = COLOR_PENDING

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    cv2.putText(frame, status, (x1, y2 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)


def draw_overlay(frame, state):
    cv2.rectangle(frame, ZONE[:2], ZONE[2:], (0, 255, 255), 2)
    cv2.putText(frame, f"Cards: {state.total_cards}", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
    cv2.putText(frame, f"Running count: {state.running_count:+d}", (20, 75),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)


# ============================================================
# MAIN LOOP
# ============================================================

def run(model, verifier, mask, camera):
    cv2.startWindowThread()
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
    cv2.setWindowProperty(WINDOW_NAME, cv2.WND_PROP_TOPMOST, 1)

    state = CountState()
    print("\n[SYSTEM] Pipeline active. Streaming live desktop feed now...")

    with (mss.MSS() if camera is None else contextlib.nullcontext()) as sct:
        while True:
            frame = grab_frame(camera, sct)

            if frame is None:
                continue

            # Crops come from this copy so they never include the boxes drawn below
            clean_frame = frame.copy()
            masked = cv2.bitwise_and(frame, frame, mask=mask)

            results = model.track(
                masked,
                imgsz=FRAME_SIZE,
                conf=DETECTION_CONF,
                iou=DETECTION_IOU,
                persist=True,
                verbose=False,
            )

            seen_ids = set()
            boxes = results[0].boxes if results else None

            if boxes is not None and boxes.id is not None:
                for xyxy, track_id, cls, conf in zip(
                    boxes.xyxy.cpu().numpy(),
                    boxes.id.cpu().numpy().astype(int),
                    boxes.cls.cpu().numpy().astype(int),
                    boxes.conf.cpu().numpy(),
                ):
                    box = tuple(int(v) for v in xyxy)
                    class_name = model.names[cls]

                    if in_zone(box):
                        seen_ids.add(track_id)
                        status = process_card(state, verifier, clean_frame, box, track_id, class_name, conf)
                    else:
                        status = "OUTSIDE ZONE"

                    draw_card(frame, box, f"{class_name} {conf:.2f} ID:{track_id}", status)

            forget_missing(state, seen_ids)
            draw_overlay(frame, state)
            cv2.imshow(WINDOW_NAME, frame)

            key = cv2.waitKey(1) & 0xFF

            if key in (ord("r"), ord("R")):
                state.reset()
                print("[SYSTEM] Count reset to 0.")

            if key in (ord("q"), ord("Q")):
                print("[SYSTEM] Quitting.")
                break

            if cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                print("[SYSTEM] Window closed.")
                break


def main():
    camera = start_dxcam()
    print(f"[SYSTEM] Screen capture: {'dxcam' if camera is not None else 'mss'}")

    try:
        mask = load_mask()
        if mask is None:
            print(f"[ERROR] Mask not found: {MASK_PATH}")
            return

        os.makedirs(CROP_FOLDER, exist_ok=True)
        os.makedirs(TEMPLATE_FOLDER, exist_ok=True)

        model = load_model()

        verifier = RankVerifier(TEMPLATE_FOLDER)
        print(f"[SYSTEM] Rank verifier: {len(verifier.templates)} templates "
              f"for ranks {', '.join(verifier.known_ranks) or 'none'}")
        if not verifier.templates:
            print("[WARNING] No labelled cards in card_templates/; using YOLO only.")

        print("\n==================================================")
        print("             PRE-CAPTURE COUNTDOWN")
        print("==================================================")
        print("Quickly switch to your browser and open Casino Plus!")

        # The first inference takes several seconds (CUDA setup), so it runs during the countdown
        countdown_start = time.perf_counter()
        model.track(np.zeros((FRAME_SIZE, FRAME_SIZE, 3), dtype=np.uint8), imgsz=FRAME_SIZE,
                    conf=DETECTION_CONF, iou=DETECTION_IOU, persist=True, verbose=False)
        print("[SYSTEM] GPU warm-up complete.")

        remaining = COUNTDOWN_SECONDS - (time.perf_counter() - countdown_start)
        while remaining > 0:
            print(f"Capturing screen in {int(remaining + 0.999)} seconds... Get ready!")
            time.sleep(min(1, remaining))
            remaining -= 1

        run(model, verifier, mask, camera)

    finally:
        if camera is not None:
            camera.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
