# AutoVision AI — CPU-optimized ANPR

## Designed for
- Windows + Python 3.11
- 8 GB RAM
- Unknown graphics hardware (CPU inference by default)
- PC webcam, image uploads and video uploads

## What is included
- Dedicated license-plate detector (YOLO26n fine-tuned model)
- EasyOCR on plate crops, not the entire scene
- Browser webcam frame sampling every 2 seconds
- Photo and video uploads
- SQLite history, duplicate suppression, manual corrections and CSV export
- State prefix and sample RTO lookup

## Important accuracy notes
The detector is a pretrained general license-plate model, not guaranteed to be optimized for every Indian plate style. OCR confidence is not a guarantee of correctness. Review every result and test with representative Indian vehicles. The included RTO directory is a starter sample, not a live or official government lookup. A prefix generally identifies a registering RTO, not necessarily the vehicle's current location or owner's address.

The selected model is published at https://huggingface.co/ishaqinu/yolo26n-license-plate-detection and is AGPL-3.0 licensed. Review its model and software license terms before redistributing or using commercially. Ultralytics also has licensing requirements: https://www.ultralytics.com/license.

## Step-by-step setup (Windows)

1. Install Python 3.11 (64-bit) and VS Code.
2. Extract this project ZIP and open the folder containing `app.py` in VS Code.
3. Open Terminal and run:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

4. Download the dedicated plate model:

```powershell
python download_model.py
```

5. Start the application:

```powershell
python app.py
```

6. Open http://127.0.0.1:5000 in Chrome or Edge and allow camera access.

First run can take a few minutes to initialize/download YOLO and EasyOCR model files. Keep an internet connection until setup is complete.

## Performance settings
- The app explicitly uses `device="cpu"`.
- Image inference uses `imgsz=640`.
- Webcam sends reduced-size frames and samples every 2 seconds.
- Video processing samples every 1.5 seconds and caps processing at 120 sampled frames.
- Do not run model training on this 8 GB RAM setup. Inference is the target workflow.

## Troubleshooting
- `No module named ultralytics`: activate `.venv`, then `pip install -r requirements.txt`.
- Model download fails: check internet and rerun `python download_model.py`.
- PyTorch installation fails: use the official selector at https://pytorch.org/get-started/locally/ then reinstall the requirements.
- Webcam fails: close apps using the camera and allow browser permission; use localhost.
- Out of memory: close other heavy apps, reduce camera resolution, and restart the server.
- Poor detection on Indian plates: use sharper/closer footage and evaluate whether an India-specific detector fine-tuned on representative data is needed.

## Privacy
The prototype runs on localhost and saves uploads/history in this project folder. Process footage only when authorized. Do not expose the app to the internet without authentication and appropriate security controls.
