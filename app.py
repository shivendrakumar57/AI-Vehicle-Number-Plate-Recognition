import os
import base64
import re
import uuid
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from anpr import recognize_image, read_image_file, read_video_file, plate_details, normalize_text, load_rto_data
from database import init_db, add_detection, list_detections, stats, update_plate

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE = {"jpg", "jpeg", "png", "webp", "bmp"}
ALLOWED_VIDEO = {"mp4", "avi", "mov", "mkv", "webm"}

# Render aur local dono ke liye templates aur static folders ka absolute path
template_dir = BASE_DIR / "templates"
static_dir = BASE_DIR / "static"

app = Flask(__name__, template_folder=str(template_dir), static_folder=str(static_dir))
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = str(UPLOAD_DIR)
init_db()

def extension(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

def save_results(results, source, image_path=None):
    saved = []
    for item in results:
        try:
            record_id, created = add_detection(item, source, image_path)
            item = dict(item)
            item["id"] = record_id
            item["saved"] = created
            saved.append(item)
        except Exception:
            app.logger.exception("Could not save detection")
    return saved

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/history")
def history_page():
    return render_template("history.html")

@app.get("/api/stats")
def api_stats():
    return jsonify(stats())

@app.get("/api/history")
def api_history():
    return jsonify(list_detections(request.args.get("q", "")))

@app.get("/api/rto")
def api_rto():
    q = normalize_text(request.args.get("q", ""))
    match = re.match(r"^([A-Z]{2})([0-9]{1,2})", q)
    if not match:
        return jsonify({"error": "Enter a prefix such as UP62 or MH12."}), 400
    state_code = match.group(1)
    rto_code = state_code + match.group(2)
    data = load_rto_data()
    return jsonify({
        "state_code": state_code,
        "state_name": data.get("states", {}).get(state_code, "Unknown state code"),
        "rto_code": rto_code,
        "rto_name": data.get("rtos", {}).get(rto_code, "RTO not in local sample database")
    })

@app.post("/api/detect")
def api_detect_upload():
    if "file" not in request.files:
        return jsonify({"error": "Choose an image or video first."}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Choose a file first."}), 400
    ext = extension(secure_filename(f.filename))
    if ext not in ALLOWED_IMAGE | ALLOWED_VIDEO:
        return jsonify({"error": "Unsupported file. Use JPG, PNG, WEBP, MP4, AVI, MOV or MKV."}), 400
    name = f"{uuid.uuid4().hex}.{ext}"
    path = UPLOAD_DIR / name
    f.save(path)
    try:
        if ext in ALLOWED_IMAGE:
            results, raw_text = read_image_file(path)
            return jsonify({"kind":"image", "results":save_results(results, "image", name), "raw_text":raw_text,
                            "message":f"Found {len(results)} readable plate candidate(s)."})
        results, frames = read_video_file(path)
        return jsonify({"kind":"video", "results":save_results(results, "video", name), "frames_processed":frames,
                        "message":f"Processed {frames} sampled frames; found {len(results)} readable unique candidate(s)."})
    except Exception as exc:
        app.logger.exception("Detection failed")
        return jsonify({"error":f"Detection failed: {exc}"}), 500

@app.post("/api/detect-frame")
def api_detect_frame():
    payload = request.get_json(silent=True) or {}
    data_url = payload.get("image", "")
    if not isinstance(data_url, str) or "," not in data_url:
        return jsonify({"error":"Invalid camera frame."}), 400
    try:
        raw = base64.b64decode(data_url.split(",", 1)[1], validate=True)
        frame = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({"error":"Could not decode camera frame."}), 400
        results, raw_text = recognize_image(frame)
        return jsonify({"results":save_results(results, "webcam"), "raw_text":raw_text})
    except Exception as exc:
        app.logger.exception("Camera detection failed")
        return jsonify({"error":str(exc)}), 500

@app.post("/api/update-plate")
def api_update_plate():
    payload = request.get_json(silent=True) or {}
    record_id = payload.get("id")
    plate = normalize_text(payload.get("plate", ""))
    valid_shape = re.fullmatch(r"(?:[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{1,4}|[0-9]{2}BH[0-9]{4}[A-Z]{1,2})", plate)
    if not isinstance(record_id, int) or not valid_shape:
        return jsonify({"error":"Enter a plate in a supported registration format."}), 400
    details = plate_details(plate)
    update_plate(record_id, plate, details)
    return jsonify({"ok":True, "plate":plate, **details})

@app.get("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error":"File is too large. Maximum upload size is 100 MB."}), 413

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
