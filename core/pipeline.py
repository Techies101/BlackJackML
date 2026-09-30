"""
Capture → YOLO tracking → rank verifier → Hi-Lo count, on a background thread.

The thread loads the model at startup, then streams while capture is switched on.
It emits each annotated frame for the live feed and adds counted cards to the
shared ShoeCounter; the UI reads the counter and never waits on the model.
"""
import contextlib
import os
import time

import cv2
import mss
import numpy as np
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

from core import config
from core.logbus import log
from utilities.rank_verifier import HILO_GROUP, HILO_VALUE, RankVerifier, card_signature, signature_similarity

FEED_COUNTED = (0, 255, 0)
FEED_PENDING = (0, 165, 255)
FEED_OUTSIDE = (128, 128, 128)


# ============================================================
# FRAME HELPERS
# ============================================================

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


def in_zone(box, zone):
    # Uses the box centre: a card touching the mask edge has its corner outside the zone
    x1, y1, x2, y2 = box
    center_x, center_y = (x1 + x2) // 2, (y1 + y2) // 2
    zx1, zy1, zx2, zy2 = zone

    return zx1 <= center_x <= zx2 and zy1 <= center_y <= zy2


def zone_mask(zone):
    """YOLO's view: the counting zone plus a small margin; everything else is blacked out."""
    size = config.FRAME_SIZE
    left, top, right, bottom = config.MASK_MARGIN
    x1, y1, x2, y2 = zone
    mask = np.zeros((size, size), dtype=np.uint8)
    mask[max(0, y1 - top):min(size, y2 + bottom + 1), max(0, x1 - left):min(size, x2 + right + 1)] = 255
    return mask


def load_model():
    # Imported here: torch/CUDA must not initialise before dxcam is created (see main.py)
    from ultralytics import YOLO

    if config.ENGINE_PRECISION not in ("fp32", "fp16"):
        raise ValueError(f'ENGINE_PRECISION must be "fp32" or "fp16", not "{config.ENGINE_PRECISION}"')

    engine, pt = config.ENGINE_PATH, config.MODEL_PATH

    # The engine is only trusted if it was built from the current .pt
    if os.path.exists(engine) and os.path.getmtime(engine) >= os.path.getmtime(pt):
        return YOLO(engine, task="detect"), f"TensorRT {config.ENGINE_PRECISION}"

    reason = "is older than the .pt model" if os.path.exists(engine) else "was not found"
    log("WARNING", f"{os.path.basename(engine)} {reason}; using the slower .pt model. "
                   f"Build it with: venv\\Scripts\\python utilities\\export_tensorrt.py {config.ENGINE_PRECISION}")
    return YOLO(pt).to("cuda"), "PyTorch .pt"


def draw_card(frame, box, label, status):
    x1, y1, x2, y2 = box
    color = FEED_COUNTED if status == "COUNTED" else FEED_OUTSIDE if status == "OUTSIDE ZONE" else FEED_PENDING

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
    cv2.putText(frame, status, (x1, y2 + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)


# ============================================================
# TRACKING STATE
# ============================================================

class TrackState:
    """Per-tracker-ID bookkeeping. Kept across "New shoe" so cards still on the table are not recounted.

    All timing uses `now`, the capture time of the current frame (set once per frame by the capture loop).
    """

    def __init__(self):
        self.now = 0.0
        self.last_seen = {}          # track id -> time it was last seen in the zone
        self.settling = {}           # track id -> {"start", "frames", "votes": {class: [conf sum, n]}, "best": (key, verdict, crop)}
        self.counted_ids = set()
        self.counted_class = {}      # track id -> YOLO class when it was counted
        self.counted_signature = {}  # track id -> rank glyphs when it was counted
        self.changed = {}            # counted track id -> [frames showing a different card, time of the first one]


def decide_rank(yolo_rank, yolo_conf, verdict):
    """Return (final rank, who decided) from YOLO's guess and the verifier's reading."""
    verifier_rank = verdict["rank"] if verdict["confident"] else None

    if verifier_rank is None:
        return yolo_rank, "YOLO"

    if verifier_rank == yolo_rank:
        return yolo_rank, "YOLO + verifier agree"

    # "confident" already means no readable corner disagrees; one corner covered by the dealer's hand is fine
    strong = verdict["score"] >= config.VERIFIER_STRONG_SCORE and verdict["margin"] >= config.VERIFIER_STRONG_MARGIN

    if yolo_conf < config.YOLO_TRUST_CONF or strong:
        return verifier_rank, "decided by VERIFIER"

    # Safety net: a disagreement across Hi-Lo groups (e.g. YOLO 8 = 0, verifier Q = −1) changes the count,
    # so a confident verifier wins even against a confident YOLO. Measured on labelled cards, a confident
    # verifier match is reliable: same-rank glyphs score ≥ 0.87, different ranks ≤ 0.63.
    if HILO_VALUE.get(verifier_rank) != HILO_VALUE.get(yolo_rank):
        return verifier_rank, "decided by VERIFIER (Hi-Lo group differs)"

    return yolo_rank, "YOLO kept (verifier disagreed, not strong enough)"


def save_capture(binary_card, final_rank, yolo_rank, disputed, track_id):
    # "_yolo<RANK>" marks cards where the verifier disagreed with YOLO: the ones worth reviewing
    tag = f"_yolo{yolo_rank}" if disputed else ""
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    filename = f"{final_rank}_unverified{tag}_id{track_id}_{timestamp}.png"

    cv2.imwrite(os.path.join(config.CROP_FOLDER, filename), binary_card)


def is_new_card(state, track_id, class_name, clean_frame, box):
    """For a counted track ID: once it has clearly shown a different card for NEW_CARD_FRAMES frames and
    NEW_CARD_SECONDS, return the time the change started (the new card's settling starts there). Otherwise None."""
    similarity = None

    # Only look closer when YOLO's class changed; the glyph check filters out YOLO flicker
    if class_name != state.counted_class.get(track_id) and track_id in state.counted_signature:
        signature = card_signature(crop_and_binarize(clean_frame, box))
        if signature is not None:
            similarity = signature_similarity(signature, state.counted_signature[track_id])

    if similarity is None or similarity >= config.NEW_CARD_SIMILARITY:
        state.changed.pop(track_id, None)
        return None

    change = state.changed.setdefault(track_id, [0, state.now])
    change[0] += 1
    if change[0] < config.NEW_CARD_FRAMES or state.now - change[1] < config.NEW_CARD_SECONDS:
        return None

    # Normal at this table: each card is placed on the same spot and then slid away, so the tracker often
    # gives the next card the previous card's ID. The new card is counted by the next DECISION line.
    log("SYSTEM", f"ID {track_id}: new card replaced {state.counted_class[track_id].replace('Card-', '')}")
    state.changed.pop(track_id, None)
    return change[1]


def find_predecessor(state, track_id):
    """The ID that was in the zone moments ago but not in this frame: when frames arrive unevenly the tracker
    often gives the same card a new ID. A genuinely new card arrives ~1.5 s after the previous one is slid away,
    so MISS_TOLERANCE_SECONDS (0.35 s) cannot confuse the two."""
    best = None
    for tid, seen in state.last_seen.items():
        if tid == track_id or seen >= state.now:      # seen in this frame: a different card
            continue
        if state.now - seen <= config.MISS_TOLERANCE_SECONDS and (best is None or seen > state.last_seen[best]):
            best = tid
    return best


# ============================================================
# CAPTURE THREAD
# ============================================================

class CaptureWorker(QThread):

    frame_ready = Signal(QImage)
    ready = Signal(str)       # model description, once loaded and warmed up
    failed = Signal(str)

    def __init__(self, camera, counter, region, zone):
        super().__init__()
        self.camera = camera            # dxcam camera (started in main.py), or None for mss
        self.counter = counter
        self.region = dict(region)      # screen area captured: left, top, width, height
        self.zone = tuple(zone)         # counting zone in feed pixels
        self._region_changed = False
        self.capturing = False
        self.show_feed = True           # False: keep counting, but skip drawing and sending frames to the UI
        self.fps = 0.0
        self._stop = False
        self.state = TrackState()

    def set_region(self, left, top):
        # Applied by the capture thread before its next frame
        self.region = {**self.region, "left": int(left), "top": int(top)}
        self._region_changed = True

    def set_zone(self, zone):
        self.zone = tuple(int(v) for v in zone)

    def set_capturing(self, on):
        self.capturing = on
        if not on:
            self.fps = 0.0

    def stop(self):
        """Stop and wait for the thread to end. Model loading / GPU warm-up can't be interrupted, so if
        the app closes during start-up this waits for that step to finish (the thread then exits at once)."""
        self._stop = True
        if not self.wait(2000):
            print("[SYSTEM] Waiting for model loading to finish before exiting…", flush=True)
            self.wait()

    # ---------- per-card logic ----------

    def count_card(self, track_id, settling):
        """Count a settled card from its best frame: the verifier's best read and YOLO's most-voted class."""
        state = self.state
        # YOLO: the class with the highest total confidence over the settling frames, at its average confidence
        class_name, (conf_sum, n) = max(settling["votes"].items(), key=lambda kv: kv[1][0])
        conf = conf_sum / n
        _, verdict, binary_card = settling["best"]

        state.counted_ids.add(track_id)
        state.counted_class[track_id] = class_name
        state.changed.pop(track_id, None)
        state.settling.pop(track_id, None)

        signature = card_signature(binary_card)
        if signature is not None:
            state.counted_signature[track_id] = signature

        yolo_rank = class_name.replace("Card-", "").upper()
        final_rank, decided_by = decide_rank(yolo_rank, conf, verdict)
        value = HILO_VALUE.get(final_rank, 0)

        short = "agree" if decided_by == "YOLO + verifier agree" else decided_by
        self.counter.add_card(final_rank, f"{final_rank} ({value:+d}) · {decided_by}")

        if binary_card is not None:
            disputed = verdict["confident"] and verdict["rank"] != yolo_rank
            save_capture(binary_card, final_rank, yolo_rank, disputed, track_id)

        verifier_text = (f"{verdict['rank']} ({verdict['score']:.2f})" if verdict["rank"] else "none") + \
                        ("" if verdict["confident"] else " not confident")
        group = HILO_GROUP.get(final_rank, "?").replace("(", "").replace(")", "")
        log("DECISION", f"ID {track_id} -> {final_rank} ({group}) · YOLO: {yolo_rank} ({conf:.2f}) · "
                        f"Verifier: {verifier_text} · {short}")

    def process_card(self, verifier, clean_frame, box, track_id, class_name, conf):
        """Advance one card that is inside the zone. Returns its on-screen status."""
        state = self.state
        start = state.now

        if track_id in state.counted_ids:
            state.last_seen[track_id] = state.now
            change_start = is_new_card(state, track_id, class_name, clean_frame, box)
            if change_start is None:
                return "COUNTED"

            # The new card on this reused ID: its settling started when the change was first seen
            state.counted_ids.discard(track_id)
            state.counted_class.pop(track_id, None)
            state.counted_signature.pop(track_id, None)
            state.settling[track_id] = {"start": change_start, "frames": config.NEW_CARD_FRAMES - 1,
                                        "votes": {}, "best": None}

        elif track_id not in state.settling:
            # A new ID in the zone: possibly the same card, re-identified by the tracker after a gap
            previous = find_predecessor(state, track_id)
            if previous in state.settling:
                state.settling[track_id] = state.settling.pop(previous)
                state.last_seen.pop(previous, None)
            elif previous in state.counted_ids:
                same = class_name == state.counted_class.get(previous)
                signature = card_signature(crop_and_binarize(clean_frame, box))
                if signature is not None and previous in state.counted_signature:
                    same = signature_similarity(signature, state.counted_signature[previous]) >= config.NEW_CARD_SIMILARITY
                if same:
                    # The already-counted card under a new ID: never count it twice
                    state.counted_ids.add(track_id)
                    state.counted_class[track_id] = state.counted_class[previous]
                    if previous in state.counted_signature:
                        state.counted_signature[track_id] = state.counted_signature[previous]
                    state.last_seen.pop(previous, None)
                    state.last_seen[track_id] = state.now
                    return "COUNTED"

        state.last_seen[track_id] = state.now
        settling = state.settling.setdefault(track_id, {"start": start, "frames": 0, "votes": {}, "best": None})
        settling["frames"] += 1

        # Every settling frame votes for YOLO's class; the verifier reads frames until it has a very good read
        # (the dealer's hand often covers a corner in the first frames, so the clearest frame wins)
        votes = settling["votes"].setdefault(class_name, [0.0, 0])
        votes[0] += conf
        votes[1] += 1
        best = settling["best"]
        if best is None or not best[0][0] or best[0][1] < config.VERIFIER_ENOUGH_SCORE:
            crop = crop_and_binarize(clean_frame, box)
            verdict = verifier.read(crop)
            key = (verdict["confident"], verdict["score"])
            if crop is not None and (best is None or key > best[0]):
                settling["best"] = (key, verdict, crop)

        if settling["frames"] < config.REQUIRED_STABLE_FRAMES:
            return f"STABLE {settling['frames']}/{config.REQUIRED_STABLE_FRAMES}"
        if state.now - settling["start"] < config.REQUIRED_STABLE_SECONDS or settling["best"] is None:
            return "SETTLING"

        self.count_card(track_id, settling)
        return "COUNTED"

    def forget_missing(self, seen_ids):
        """Settling cards that have left the zone (missing > MISS_TOLERANCE_SECONDS). If one was clearly seen but
        left before REQUIRED_STABLE_SECONDS (uneven frames can hide most of its ~1 s in the zone), count it now."""
        state = self.state
        for track_id in list(state.settling):
            if track_id in seen_ids or state.now - state.last_seen.get(track_id, state.now) <= config.MISS_TOLERANCE_SECONDS:
                continue
            settling = state.settling[track_id]
            best = settling["best"]
            votes = settling["votes"]
            steady_yolo = any(n and total / n >= config.EXIT_MIN_YOLO_CONF for total, n in votes.values())
            if settling["frames"] >= config.EXIT_MIN_FRAMES and best is not None and (best[1]["confident"] or steady_yolo):
                self.count_card(track_id, settling)
            else:
                del state.settling[track_id]
        for track_id in [t for t, seen in state.last_seen.items() if state.now - seen > 5.0]:
            del state.last_seen[track_id]

    # ---------- thread ----------

    def grab_frame(self, sct):
        if self.camera is not None:
            frame = self.camera.get_latest_frame()
            # Copy: dxcam reuses its buffer for later frames
            return None if frame is None else frame.copy()

        shot = sct.grab(self.region)
        frame = np.frombuffer(shot.rgb, dtype=np.uint8).reshape(shot.height, shot.width, 3)
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def run(self):
        try:
            os.makedirs(config.CROP_FOLDER, exist_ok=True)
            os.makedirs(config.TEMPLATE_FOLDER, exist_ok=True)

            model, model_text = load_model()
            if self._stop:
                return

            verifier = RankVerifier(config.TEMPLATE_FOLDER)
            log("SYSTEM", f"Rank verifier: {len(verifier.templates)} templates "
                          f"for ranks {', '.join(verifier.known_ranks) or 'none'}")
            for name, corner in verifier.skipped:
                log("WARNING", f"Template {name} ({corner.lower()} corner) doesn't look like its rank; skipped")
            if not verifier.templates:
                log("WARNING", "No labelled cards in card_templates/; using YOLO only.")

            # The first inference takes several seconds (CUDA setup)
            model.track(np.zeros((config.FRAME_SIZE, config.FRAME_SIZE, 3), dtype=np.uint8),
                        imgsz=config.FRAME_SIZE, conf=config.DETECTION_CONF, iou=config.DETECTION_IOU,
                        persist=True, verbose=False)
        except Exception as e:
            log("ERROR", f"Startup failed: {e}")
            self.failed.emit(str(e))
            return

        if self._stop:
            return
        log("SYSTEM", "GPU warm-up complete. Press Start capture.")
        self.ready.emit(model_text)

        mask_zone, mask = None, None
        last_frame = None                  # frame-gap tracking: long gaps are when cards get missed
        stalls, longest, report_at = 0, 0.0, time.monotonic() + config.STALL_REPORT_SECONDS

        # mss handles are per thread, so the fallback is opened here
        with (mss.MSS() if self.camera is None else contextlib.nullcontext()) as sct:
            while not self._stop:
                if self._region_changed:
                    self._apply_region()

                if not self.capturing:
                    last_frame = None          # a pause is not a stall
                    time.sleep(0.05)
                    continue

                zone = self.zone
                if zone != mask_zone:
                    mask_zone, mask = zone, zone_mask(zone)

                started = time.perf_counter()
                frame = self.grab_frame(sct)
                self.state.now = time.monotonic()    # one timestamp for everything in this frame

                if frame is None:
                    continue

                # Crops come from this copy so they never include the boxes drawn below
                clean_frame = frame.copy()
                masked = cv2.bitwise_and(frame, frame, mask=mask)

                results = model.track(masked, imgsz=config.FRAME_SIZE, conf=config.DETECTION_CONF,
                                      iou=config.DETECTION_IOU, persist=True, verbose=False)

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

                        if in_zone(box, zone):
                            seen_ids.add(track_id)
                            status = self.process_card(verifier, clean_frame, box, track_id, class_name, conf)
                        else:
                            status = "OUTSIDE ZONE"

                        if self.show_feed:
                            draw_card(frame, box, f"{class_name} {conf:.2f} ID:{track_id}", status)

                self.forget_missing(seen_ids)

                if self.show_feed:
                    height, width = frame.shape[:2]
                    image = QImage(frame.data, width, height, 3 * width, QImage.Format.Format_BGR888).copy()
                    self.frame_ready.emit(image)

                elapsed = time.perf_counter() - started
                self.fps = 1 / elapsed if self.fps == 0 else 0.9 * self.fps + 0.1 / max(elapsed, 1e-3)

                # A card sits in the zone ~1 s, so gaps of 0.5 s+ between frames risk missing it
                if last_frame is not None and self.state.now - last_frame > config.STALL_WARN_SECONDS:
                    stalls += 1
                    longest = max(longest, self.state.now - last_frame)
                last_frame = self.state.now
                if self.state.now >= report_at:
                    if stalls:
                        log("WARNING", f"{stalls} frame gap{'s' if stalls > 1 else ''} over "
                                       f"{config.STALL_WARN_SECONDS} s in the last {config.STALL_REPORT_SECONDS} s "
                                       f"(longest {longest:.1f} s): the PC is too busy; cards may be missed")
                    stalls, longest, report_at = 0, 0.0, self.state.now + config.STALL_REPORT_SECONDS

    def _apply_region(self):
        self._region_changed = False
        r = self.region
        if self.camera is not None:
            # dxcam can restart on a new region even after CUDA is initialised (verified)
            try:
                self.camera.stop()
                self.camera.start(region=(r["left"], r["top"], r["left"] + r["width"], r["top"] + r["height"]),
                                  target_fps=60, video_mode=True)
            except Exception as e:
                log("ERROR", f"Could not move the capture area: {e}")
                return
        log("SYSTEM", f"Capture area moved to x {r['left']}, y {r['top']} ({r['width']} × {r['height']})")
