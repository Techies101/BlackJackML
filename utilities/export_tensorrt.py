import os
import sys
import glob
import time
import shutil
import cv2
import numpy as np
from ultralytics import YOLO


# ============================================================
# EXPORT YOLO MODEL TO TENSORRT
# ============================================================
#
# Builds current_models/<model>.<precision>.engine from the .pt model,
# then checks that the engine finds the same cards as the .pt model
# before main.py is allowed to use it. Run again whenever the .pt changes:
#
#   venv\Scripts\python utilities\export_tensorrt.py [fp32|fp16]
#
# fp32 (default) matches the .pt exactly; fp16 is faster on this GPU.
# main.py picks one with its ENGINE_PRECISION setting.
# ============================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(PROJECT_ROOT, "current_models", "blackjack_model_v0.4.pt")
MASK_PATH = os.path.join(PROJECT_ROOT, "utilities", "mask1.png")
TEMPLATE_FOLDER = os.path.join(PROJECT_ROOT, "card_templates")

PRECISION = sys.argv[1].lower() if len(sys.argv) > 1 else "fp32"
if PRECISION not in ("fp32", "fp16"):
    sys.exit(f"Unknown precision '{PRECISION}'; use fp32 or fp16.")

HALF = PRECISION == "fp16"
ENGINE_PATH = f"{os.path.splitext(MODEL_PATH)[0]}.{PRECISION}.engine"

# Detections must match the .pt model this closely to pass
MIN_BOX_IOU = 0.90
MAX_CONF_DIFF = 0.05


def make_test_frames():

    # Every labelled card pasted into the mask window at a few positions,
    # at the size cards appear in the live feed (~65 x 46 px).
    mask = cv2.resize(cv2.imread(MASK_PATH, 0), (640, 640), interpolation=cv2.INTER_NEAREST)
    frames = []

    for path in sorted(glob.glob(os.path.join(TEMPLATE_FOLDER, "*.png"))):

        card = cv2.imread(path)

        for x, y in [(240, 548), (262, 562), (280, 575)]:
            screen = np.full((640, 640, 3), 40, np.uint8)
            screen[y:y + 56, x:x + 76] = cv2.resize(card, (76, 56), interpolation=cv2.INTER_AREA)
            frames.append(cv2.bitwise_and(screen, screen, mask=mask))

    return frames


def detections(model, frame):

    r = model.predict(frame, imgsz=640, conf=0.45, iou=0.45, verbose=False)[0].boxes
    return list(zip(r.cls.cpu().numpy().astype(int), r.conf.cpu().numpy(), r.xyxy.cpu().numpy()))


def iou(a, b):

    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def time_model(model, frame, n=100):

    for _ in range(10):
        model.predict(frame, imgsz=640, conf=0.45, verbose=False)
    t = time.perf_counter()
    for _ in range(n):
        model.predict(frame, imgsz=640, conf=0.45, verbose=False)
    return (time.perf_counter() - t) * 1000 / n


def main():

    print(f"[EXPORT] {os.path.basename(MODEL_PATH)} -> TensorRT ({PRECISION})")

    # Keep the current engine until the new one passes the check
    previous_engine = ENGINE_PATH + ".previous"
    if os.path.exists(ENGINE_PATH):
        shutil.copy2(ENGINE_PATH, previous_engine)

    exported = YOLO(MODEL_PATH).export(
        format="engine", imgsz=640, half=HALF, device=0, batch=1, dynamic=False, verbose=False
    )

    # Ultralytics always writes "<model>.engine"; give it its precision-specific name
    os.replace(exported, ENGINE_PATH)

    print(f"[EXPORT] Saved {ENGINE_PATH}")

    # ---- Check: engine vs .pt on every labelled card ----

    pt_model = YOLO(MODEL_PATH).to("cuda")
    engine_model = YOLO(ENGINE_PATH, task="detect")

    frames = make_test_frames()
    mismatches = 0
    worst_iou, worst_conf = 1.0, 0.0

    for frame in frames:

        a = sorted(detections(pt_model, frame), key=lambda d: d[2][0])
        b = sorted(detections(engine_model, frame), key=lambda d: d[2][0])

        if len(a) != len(b) or any(da[0] != db[0] for da, db in zip(a, b)):
            mismatches += 1
            continue

        for da, db in zip(a, b):
            worst_iou = min(worst_iou, iou(da[2], db[2]))
            worst_conf = max(worst_conf, abs(float(da[1]) - float(db[1])))

    passed = mismatches == 0 and worst_iou >= MIN_BOX_IOU and worst_conf <= MAX_CONF_DIFF

    print()
    print(f"[CHECK] Test frames            : {len(frames)}")
    print(f"[CHECK] Different cards found  : {mismatches}")
    print(f"[CHECK] Worst box overlap (IoU): {worst_iou:.3f}  (need >= {MIN_BOX_IOU})")
    print(f"[CHECK] Worst confidence diff  : {worst_conf:.3f}  (need <= {MAX_CONF_DIFF})")

    sample = frames[0] if frames else np.zeros((640, 640, 3), np.uint8)
    print(f"[SPEED] .pt    : {time_model(pt_model, sample):6.1f} ms per frame")
    print(f"[SPEED] engine : {time_model(engine_model, sample):6.1f} ms per frame")

    del engine_model  # release the engine file before replacing it

    if passed:
        if os.path.exists(previous_engine):
            os.remove(previous_engine)
        print("\n[RESULT] PASS - main.py will use the new TensorRT engine.")
    elif os.path.exists(previous_engine):
        os.replace(previous_engine, ENGINE_PATH)
        print("\n[RESULT] FAIL - new engine discarded; the previous engine was restored.")
    else:
        os.remove(ENGINE_PATH)
        print("\n[RESULT] FAIL - engine deleted; main.py keeps using the .pt model.")


if __name__ == "__main__":

    main()
