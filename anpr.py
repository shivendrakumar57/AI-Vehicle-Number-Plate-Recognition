import re
import threading
from pathlib import Path

import cv2
import easyocr
import numpy as np
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "alpr_26n.pt"
RTO_PATH = BASE_DIR / "data" / "rto_codes.json"

_reader = None
_yolo = None
_reader_lock = threading.Lock()
_yolo_lock = threading.Lock()

def get_reader():
    global _reader
    with _reader_lock:
        if _reader is None:
            # CPU mode: compatible with 8 GB RAM systems without a known GPU.
            _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        return _reader

def get_yolo():
    global _yolo
    with _yolo_lock:
        if _yolo is None:
            if not MODEL_PATH.exists():
                raise FileNotFoundError(
                    "Dedicated plate model missing. Run 'python download_model.py' first."
                )
            _yolo = YOLO(str(MODEL_PATH))
        return _yolo

def load_rto_data():
    import json
    try:
        with open(RTO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"states": {}, "rtos": {}}

def normalize_text(text):
    return re.sub(r"[^A-Z0-9]", "", str(text).upper())

# Common Indian registration formats. This validates shape, not legal registration.
PLATE_PATTERNS = [
    re.compile(r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}$"),
    re.compile(r"^[0-9]{2}BH[0-9]{4}[A-Z]{1,2}$"),
]

def is_plate_shape(text):
    compact = normalize_text(text)
    return any(p.fullmatch(compact) for p in PLATE_PATTERNS)

def plate_details(plate):
    data = load_rto_data()
    plate = normalize_text(plate)
    state_code = plate[:2] if len(plate) >= 2 and plate[:2].isalpha() else ""
    # Most state registrations begin with 2 letters followed by a numeric RTO code.
    match = re.match(r"^([A-Z]{2})([0-9]{1,2})", plate)
    rto_code = match.group(1) + match.group(2) if match else ""
    return {
        "state_code": state_code,
        "state_name": data.get("states", {}).get(state_code, "Unknown / verify"),
        "rto_code": rto_code,
        "rto_name": data.get("rtos", {}).get(rto_code, "RTO not in local sample database"),
    }

def _preprocess_crop(crop):
    if crop is None or crop.size == 0:
        return None
    h, w = crop.shape[:2]
    if w < 1 or h < 1:
        return None
    # Plate crops are often small. Upscaling helps OCR, but keep RAM bounded.
    target_w = min(960, max(w, 2 * w))
    scale = target_w / w
    target_h = max(1, int(h * scale))
    crop = cv2.resize(crop, (target_w, target_h), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    # Mild contrast normalization; avoid hard thresholding that destroys thin characters.
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return gray

def _ocr_crop(crop):
    prepared = _preprocess_crop(crop)
    if prepared is None:
        return "", 0.0
    reader = get_reader()
    results = reader.readtext(
        prepared, detail=1, paragraph=False, batch_size=1,
        allowlist="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
    if not results:
        return "", 0.0
    # Sort text regions by horizontal position, then join them.
    results = sorted(results, key=lambda r: min(pt[0] for pt in r[0]))
    text = "".join(normalize_text(r[1]) for r in results)
    confs = [float(r[2]) for r in results if r[1]]
    confidence = (sum(confs) / len(confs) * 100) if confs else 0.0
    return normalize_text(text), round(confidence, 1)

def _candidate_variants(raw):
    raw = normalize_text(raw)
    # Keep the actual OCR result; do not silently mutate characters into a different number.
    if is_plate_shape(raw):
        return [raw]
    # OCR sometimes splits text; joining regions above already removes spaces.
    # Return plausible candidates only, and leave all ambiguous output for manual review.
    return []

def recognize_image(image, max_results=10):
    if image is None:
        raise ValueError("Image could not be read. Try a clearer JPG/PNG image.")
    h, w = image.shape[:2]
    if w > 1600:
        scale = 1600 / w
        image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

    model = get_yolo()
    # Small model, CPU inference and reduced image size are chosen for 8 GB RAM.
    prediction = model.predict(
        source=image, imgsz=640, conf=0.20, iou=0.45, max_det=12,
        device="cpu", verbose=False
    )
    result = prediction[0]
    h, w = image.shape[:2]
    candidates = []
    raw_texts = []

    if result.boxes is None or len(result.boxes) == 0:
        # Deliberately do not OCR the entire scene: that tends to create false plate guesses.
        return [], "No plate region detected. Try a closer, sharper image."

    boxes = sorted(
        result.boxes,
        key=lambda box: float(box.conf[0]),
        reverse=True
    )
    for box in boxes[:max_results]:
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        # A small margin avoids clipping characters at the plate edges.
        pad_x = max(2, int((x2 - x1) * 0.04))
        pad_y = max(2, int((y2 - y1) * 0.12))
        x1, y1 = max(0, x1-pad_x), max(0, y1-pad_y)
        x2, y2 = min(w, x2+pad_x), min(h, y2+pad_y)
        crop = image[y1:y2, x1:x2]
        try:
            raw, ocr_conf = _ocr_crop(crop)
        except Exception:
            continue
        raw_texts.append(raw)
        variants = _candidate_variants(raw)
        if not variants:
            continue
        plate = variants[0]
        item = {
            "plate_number": plate,
            "confidence": ocr_conf,
            "detector_confidence": round(float(box.conf[0]) * 100, 1),
            "bbox": [x1, y1, x2, y2],
            **plate_details(plate)
        }
        # If the same plate is detected twice in the same frame, retain the stronger box.
        previous = next((x for x in candidates if x["plate_number"] == plate), None)
        if previous is None:
            candidates.append(item)
        elif item["detector_confidence"] > previous["detector_confidence"]:
            candidates.remove(previous)
            candidates.append(item)

    return candidates, " | ".join(x for x in raw_texts if x) or "Plate region detected; OCR could not read a valid-format candidate."

def read_image_file(path):
    image = cv2.imread(str(path))
    return recognize_image(image)

def read_video_file(path, sample_every_seconds=1.5, max_frames=120):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("Video could not be opened. Try MP4, AVI or MOV.")
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 25
    interval = max(1, int(fps * sample_every_seconds))
    frame_index, processed = 0, 0
    detections = {}
    try:
        while processed < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if frame_index % interval == 0:
                try:
                    found, _ = recognize_image(frame)
                    for item in found:
                        old = detections.get(item["plate_number"])
                        if old is None or item["confidence"] > old["confidence"]:
                            detections[item["plate_number"]] = item
                except Exception:
                    pass
                processed += 1
            frame_index += 1
    finally:
        cap.release()
    return list(detections.values()), processed
