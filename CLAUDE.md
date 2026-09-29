# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A live Hi-Lo card counter for an online blackjack table. `main.py` captures a fixed 640×640 screen region, detects and tracks cards with a YOLO model, cross-checks each card's rank with a template-matching verifier, and updates the running count. Windows-only, runs on the NVIDIA GPU (GTX 1650 Ti, Intel + NVIDIA laptop). Not a git repository.

## Environment and commands

Always use the project venv (VS Code is configured against it; the global Python has different packages):

```
venv\Scripts\python -m pip install -r requirements.txt   # install
venv\Scripts\python main.py                              # run the live counter (needs the game on screen)
venv\Scripts\python experimentations\test_rank_verifier.py   # offline accuracy test of the verifier
venv\Scripts\python utilities\export_tensorrt.py [fp32|fp16] # rebuild + validate a TensorRT engine
```

There is no test framework, linter or build step. `test_rank_verifier.py` is the main regression check: it scores the verifier leave-one-card-out (honest) and cross-corner (optimistic) on `card_templates/`, and writes per-step debug images to `rank_verifier_results/`. `test_trocr*.py` are abandoned TrOCR experiments.

## Architecture

**Per-frame pipeline (`main.py`, a top-level script, no `main()`):**
1. Capture via `dxcam` (background thread, ~1.6 ms), falling back to `mss`. `crop_monitor` fixes the region.
2. Apply `utilities/mask1.png`: YOLO only sees a small window (x 228–352, y 537–626), almost identical to the counting zone (`zone_x1..zone_y2`).
3. `model.track(...)` (ByteTrack). A card counts once its box **centre** is in the zone for `REQUIRED_STABLE_FRAMES` frames; up to `MISS_TOLERANCE` missed frames are tolerated.
4. On count: crop from `clean_frame` (copy taken before any drawing), 2.5× upscale + Otsu → `verifier.read()`; YOLO vs verifier decided by `YOLO_TRUST_CONF` / `VERIFIER_STRONG_*`; crop saved to `captured_cards/`.
5. **Reused tracker IDs:** a new card landing on the same spot often inherits an already-counted ID. `main.py` stores the counted card's rank-glyph signature and re-counts the ID when both the YOLO class and the glyph change for `NEW_CARD_FRAMES` frames.

**`utilities/rank_verifier.py`** (shared by `main.py` and the test script, classic CV, not a neural net): find card contour → perspective-warp to a 280×200 **landscape** card (the game shows cards landscape; a 180° flip is harmless) → crop the rank from both corners (bottom-right rotated upright, which avoids 6/9 confusion) → 40×48 glyph → normalised cross-correlation against templates. `MIN_SCORE`/`MIN_MARGIN` gate confidence; measured on labelled cards, same-rank glyphs score ≥ 0.87 and different ranks ≤ 0.63.

## Data conventions

- `card_templates/` = verified, labelled cards used as verifier templates. Name: `<RANK>_<suit>_id<N>_<timestamp>.png`; rank is parsed from the first `_` token (`2`–`10`, `J`, `Q`, `K`, `A`).
- `captured_cards/` = new captures from `main.py`, named `<RANK>_unverified[_yolo<RANK>]_id<N>_<timestamp>.png`. The rank there is only the pipeline's guess (`_yolo<X>` marks a YOLO/verifier disagreement). Any filename containing `unverified` is ignored as a template/label; a human renames it and moves it to `card_templates/`. Templates load only at startup.
- Suits don't matter to the verifier (images are binarized, suit symbol is discarded); 3–5 examples per rank matter.

## Gotchas

- **dxcam must be created before `ultralytics`/`torch` are imported.** On this Intel+NVIDIA laptop, Desktop Duplication fails (`COMError ... feature level is not supported`) once the process has initialised CUDA. That is why the capture setup sits above the YOLO import in `main.py`.
- **Do not use `quantize="fp16"` / half precision with the `.pt` model:** on the GTX 1650 Ti it is slower (≈63 ms vs 37 ms per frame).
- `ENGINE_PRECISION` in `main.py` (`"fp32"` or `"fp16"`) selects `current_models/<model>.<precision>.engine`. It is used only when it exists and is newer than the `.pt`; otherwise `main.py` warns and falls back to the slower `.pt` on CUDA. After changing the `.pt`, rerun `export_tensorrt.py <precision>`: it keeps a new engine only if detections match the `.pt` on every template card, and restores the previous engine otherwise. fp32 matches the `.pt` exactly (full loop ≈31 ms/frame); fp16 is faster (≈25 ms) with confidences up to ~0.04 off. Engine files are GPU/TensorRT-version specific; the `.onnx` files are export by-products.
- PaddleOCR was removed on purpose (1–2.5 s per card on CPU froze the feed, and misread cards). `opencv-python` is the only OpenCV package; installing `opencv-contrib-python` alongside it breaks `cv2`.
- Startup is ~10 s, mostly `import torch` (~3.7 s, not caused by OneDrive) and the first CUDA call; the 3 s countdown overlaps the warm-up.
- Code comments in `main.py` are a Tagalog/English mix; match the surrounding style when editing.
