from pathlib import Path
from urllib.request import Request, urlopen
import sys

BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"
MODEL_PATH = MODEL_DIR / "alpr_26n.pt"
MODEL_URL = "https://huggingface.co/ishaqinu/yolo26n-license-plate-detection/resolve/main/alpr_26n.pt"

def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if MODEL_PATH.exists() and MODEL_PATH.stat().st_size > 1_000_000:
        print(f"Model already exists: {MODEL_PATH}")
        return
    tmp = MODEL_PATH.with_suffix(".pt.download")
    print("Downloading lightweight license-plate detector (~5-20 MB).")
    print("A working internet connection is needed for this one-time download.")
    try:
        req = Request(MODEL_URL, headers={"User-Agent": "AutoVisionANPR/1.0"})
        with urlopen(req, timeout=45) as response, open(tmp, "wb") as out:
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                total += len(chunk)
                print(f"\rDownloaded {total / (1024 * 1024):.1f} MB", end="", flush=True)
        print()
        if tmp.stat().st_size < 1_000_000:
            raise RuntimeError("Downloaded file is unexpectedly small; the model URL may have changed.")
        tmp.replace(MODEL_PATH)
        print(f"Model saved to: {MODEL_PATH}")
        print("Model license is AGPL-3.0; review its terms before redistribution or commercial deployment.")
    except Exception as exc:
        if tmp.exists():
            tmp.unlink()
        print(f"\nModel download failed: {exc}", file=sys.stderr)
        print("Check your internet connection and run: python download_model.py", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
