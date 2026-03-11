"""
Fish Species Vision API
-----------------------
POST /api/v1/vision/identify   — Upload an image; returns YOLO detections from best.onnx
GET  /api/v1/vision/classes    — Returns all 28 detectable class names
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse

# ── ONNX runtime (lazy-import so server still starts even if not installed) ────
try:
    import onnxruntime as ort
    _ORT_OK = True
except ImportError:
    _ORT_OK = False

# ── Pillow for image preprocessing ────────────────────────────────────────────
try:
    from PIL import Image
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

router = APIRouter()

# ── Model path ────────────────────────────────────────────────────────────────
_MODEL_PATH = Path(__file__).parent.parent.parent / "ml" / "vision" / "best.onnx"

# ── 28 class names (from ONNX metadata) ──────────────────────────────────────
CLASS_NAMES = [
    "Albacore",              # 0
    "Bigeye tuna",           # 1
    "Black marlin",          # 2
    "Blue marlin",           # 3
    "Great barracuda",       # 4
    "Human",                 # 5
    "Indo Pacific sailfish", # 6
    "Long snouted lancetfish",# 7
    "Mahi mahi",             # 8
    "Mola mola",             # 9
    "No fish",               # 10
    "Oilfish",               # 11
    "Opah",                  # 12
    "Pelagic stingray",      # 13
    "Pomfret",               # 14
    "Rainbow runner",        # 15
    "Roudie scolar",         # 16
    "Shark",                 # 17
    "Shortbill spearfish",   # 18
    "Sickle pomfret",        # 19
    "Skipjack tuna",         # 20
    "Snake mackerel",        # 21
    "Striped marlin",        # 22
    "Swordfish",             # 23
    "Thresher shark",        # 24
    "Unknown",               # 25
    "Wahoo",                 # 26
    "Yellowfin tuna",        # 27
]

# Classes that are NOT fish — excluded from primary detection
# 5=Human, 10=No fish, 25=Unknown
_NON_FISH_IDS: set[int] = {5, 10, 25}

# Market code mapping: YOLO class → market code used in market.py
CLASS_TO_MARKET_CODE: dict[str, str] = {
    "Yellowfin tuna":        "YFT",
    "Bigeye tuna":           "BET",
    "Skipjack tuna":         "SKJ",
    "Albacore":              "ALB",
    "Swordfish":             "SWO",
    "Mahi mahi":             "MAHI",
    "Blue marlin":           "BUM",
    "Black marlin":          "BUM",
    "Striped marlin":        "BUM",
    "Shortbill spearfish":   "SAX",
    "Indo Pacific sailfish": "SAX",
}

# ── Singleton ONNX session ─────────────────────────────────────────────────────
_session: Optional["ort.InferenceSession"] = None

def _get_session() -> "ort.InferenceSession":
    global _session
    if _session is None:
        if not _ORT_OK:
            raise RuntimeError("onnxruntime is not installed. Run: pip install onnxruntime")
        if not _MODEL_PATH.exists():
            raise RuntimeError(f"Model not found at {_MODEL_PATH}")
        _session = ort.InferenceSession(
            str(_MODEL_PATH),
            providers=["CPUExecutionProvider"],
        )
    return _session

# ── Image preprocessing ────────────────────────────────────────────────────────
_INPUT_SIZE = 640

def _preprocess(image_bytes: bytes) -> tuple[np.ndarray, int, int]:
    """Read image bytes → padded 640×640 float32 NCHW tensor.
    Returns (tensor, orig_w, orig_h).
    """
    if not _PIL_OK:
        raise RuntimeError("Pillow is not installed. Run: pip install Pillow")

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    orig_w, orig_h = img.size

    # Letterbox resize preserving aspect ratio
    scale = _INPUT_SIZE / max(orig_w, orig_h)
    new_w = int(round(orig_w * scale))
    new_h = int(round(orig_h * scale))
    img = img.resize((new_w, new_h), Image.BILINEAR)

    # Pad to 640×640
    canvas = Image.new("RGB", (_INPUT_SIZE, _INPUT_SIZE), (114, 114, 114))
    pad_x = (_INPUT_SIZE - new_w) // 2
    pad_y = (_INPUT_SIZE - new_h) // 2
    canvas.paste(img, (pad_x, pad_y))

    arr = np.array(canvas, dtype=np.float32) / 255.0          # HWC [0,1]
    arr = arr.transpose(2, 0, 1)[np.newaxis, ...]              # 1×3×H×W
    return arr, orig_w, orig_h

# ── NMS helper ────────────────────────────────────────────────────────────────
def _iou(a: np.ndarray, b: np.ndarray) -> float:
    """IoU of two [x1,y1,x2,y2] boxes."""
    xi1, yi1 = max(a[0], b[0]), max(a[1], b[1])
    xi2, yi2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    ua = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - inter
    return inter / max(ua, 1e-6)

def _nms(boxes: list, scores: list, iou_thresh: float = 0.45) -> list[int]:
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    keep = []
    while order:
        i = order.pop(0)
        keep.append(i)
        order = [j for j in order if _iou(boxes[i], boxes[j]) < iou_thresh]
    return keep

# ── YOLO v8 post-processing ───────────────────────────────────────────────────
def _postprocess(
    raw: np.ndarray,
    orig_w: int,
    orig_h: int,
    conf_thresh: float = 0.25,
    iou_thresh: float  = 0.45,
    top_k: int         = 10,
) -> list[dict]:
    """
    raw shape: [1, 32, 8400]  →  4 box coords + 28 class scores
    Returns list of detection dicts sorted by confidence.
    """
    preds = raw[0]  # [32, 8400]
    # Transpose to [8400, 32]
    preds = preds.T  # [8400, 32]

    boxes  = preds[:, :4]      # cx, cy, w, h  (in 640-px space)
    scores = preds[:, 4:]      # 28 class logits / probs

    # Zero out non-fish classes so they can NEVER become primary
    # 5=Human, 10=No fish, 25=Unknown
    for non_fish_id in _NON_FISH_IDS:
        if non_fish_id < scores.shape[1]:
            scores[:, non_fish_id] = 0.0

    # Best fish class per anchor
    cls_ids = scores.argmax(axis=1)
    cls_conf = scores.max(axis=1)

    # Filter by confidence
    mask = cls_conf >= conf_thresh
    if not mask.any():
        # Fallback: best fish anchor (non-fish already zeroed out above)
        best = int(cls_conf.argmax())
        mask = np.zeros(len(cls_conf), dtype=bool)
        mask[best] = True

    boxes    = boxes[mask]
    cls_conf = cls_conf[mask]
    cls_ids  = cls_ids[mask]

    # Convert cx,cy,w,h → x1,y1,x2,y2 (still in 640-space)
    x1 = boxes[:, 0] - boxes[:, 2] / 2
    y1 = boxes[:, 1] - boxes[:, 3] / 2
    x2 = boxes[:, 0] + boxes[:, 2] / 2
    y2 = boxes[:, 1] + boxes[:, 3] / 2
    xyxy = np.stack([x1, y1, x2, y2], axis=1)

    # NMS
    keep = _nms(xyxy.tolist(), cls_conf.tolist(), iou_thresh)[:top_k]

    # Scale boxes back to original image
    scale = _INPUT_SIZE / max(orig_w, orig_h)
    pad_x = (_INPUT_SIZE - int(round(orig_w * scale))) // 2
    pad_y = (_INPUT_SIZE - int(round(orig_h * scale))) // 2

    results = []
    for idx in keep:
        bx1, by1, bx2, by2 = xyxy[idx]
        # Remove letterbox padding then rescale
        bx1 = max(0.0, (float(bx1) - pad_x) / scale)
        by1 = max(0.0, (float(by1) - pad_y) / scale)
        bx2 = min(float(orig_w), (float(bx2) - pad_x) / scale)
        by2 = min(float(orig_h), (float(by2) - pad_y) / scale)

        class_id   = int(cls_ids[idx])
        class_name = CLASS_NAMES[class_id] if class_id < len(CLASS_NAMES) else "Unknown"
        confidence = round(float(cls_conf[idx]), 4)
        market_code = CLASS_TO_MARKET_CODE.get(class_name)

        results.append({
            "class_id":    class_id,
            "class_name":  class_name,
            "confidence":  confidence,
            "confidence_pct": round(confidence * 100, 1),
            "market_code": market_code,
            "bbox": {
                "x1": round(bx1, 1),
                "y1": round(by1, 1),
                "x2": round(bx2, 1),
                "y2": round(by2, 1),
                "width":  round(bx2 - bx1, 1),
                "height": round(by2 - by1, 1),
            },
        })

    # Sort by confidence descending
    results.sort(key=lambda d: d["confidence"], reverse=True)
    return results


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/classes")
def list_classes():
    """Return all detectable fish species classes."""
    return {
        "total": len(CLASS_NAMES),
        "classes": [
            {
                "id":          i,
                "name":        name,
                "market_code": CLASS_TO_MARKET_CODE.get(name),
            }
            for i, name in enumerate(CLASS_NAMES)
        ],
    }


@router.post("/identify")
async def identify_fish(file: UploadFile = File(...)):
    """
    Upload an image; returns YOLO detections with class names and confidence.

    Accepts: image/jpeg, image/png, image/webp, image/bmp
    Returns: list of detections sorted by confidence
    """
    # Validate content type
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type '{file.content_type}'. Please upload an image.",
        )

    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    t0 = time.perf_counter()

    try:
        session = _get_session()
        tensor, orig_w, orig_h = _preprocess(image_bytes)

        input_name = session.get_inputs()[0].name
        raw_output = session.run(None, {input_name: tensor})[0]  # [1, 32, 8400]

        detections = _postprocess(raw_output, orig_w, orig_h)

    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inference error: {exc}")

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)

    # human_in_frame: check raw output before non-fish zeroing
    # (detections list never contains Human — it was zeroed out at score level)
    human_in_frame = False
    try:
        raw_scores = raw_output[0].T[:, 4:]   # [8400, 28] before zeroing
        human_conf = raw_scores[:, 5].max()
        human_in_frame = bool(human_conf >= 0.25)
    except Exception:
        pass

    primary = detections[0] if detections else None

    return {
        "model":            "best.onnx (YOLOv8)",
        "image_size":       {"width": orig_w, "height": orig_h},
        "inference_ms":     elapsed_ms,
        "total_detections": len(detections),
        "human_in_frame":   human_in_frame,
        "primary":          primary,
        "detections":       detections,
    }
