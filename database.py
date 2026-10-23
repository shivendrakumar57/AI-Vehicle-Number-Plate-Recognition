import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "history.db"

def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plate_number TEXT NOT NULL,
                state_code TEXT,
                state_name TEXT,
                rto_code TEXT,
                rto_name TEXT,
                confidence REAL,
                detector_confidence REAL,
                source TEXT,
                created_at TEXT NOT NULL,
                image_path TEXT,
                reviewed INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Migrate an earlier version's database without losing existing history.
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(detections)")}
        if "detector_confidence" not in cols:
            conn.execute("ALTER TABLE detections ADD COLUMN detector_confidence REAL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_plate ON detections(plate_number)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created ON detections(created_at)")

def add_detection(item, source, image_path=None):
    now = datetime.now().astimezone()
    with get_connection() as conn:
        # Suppress same plate from webcam within 30 seconds.
        if source == "webcam":
            row = conn.execute("""
                SELECT id FROM detections
                WHERE plate_number = ? AND source = 'webcam'
                ORDER BY id DESC LIMIT 1
            """, (item["plate_number"],)).fetchone()
            if row:
                try:
                    old = datetime.fromisoformat(row["created_at"])
                    if (now - old).total_seconds() < 30:
                        return row["id"], False
                except (TypeError, ValueError):
                    pass
        cur = conn.execute("""
            INSERT INTO detections
            (plate_number, state_code, state_name, rto_code, rto_name,
             confidence, detector_confidence, source, created_at, image_path, reviewed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
        """, (
            item["plate_number"], item.get("state_code"), item.get("state_name"),
            item.get("rto_code"), item.get("rto_name"), item.get("confidence", 0),
            item.get("detector_confidence", 0), source, now.isoformat(timespec="seconds"),
            image_path
        ))
        return cur.lastrowid, True

def list_detections(search="", limit=500):
    q = f"%{search.strip()}%"
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM detections
            WHERE plate_number LIKE ? OR state_name LIKE ? OR rto_name LIKE ?
            ORDER BY id DESC LIMIT ?
        """, (q, q, q, limit)).fetchall()
        return [dict(r) for r in rows]

def stats():
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
        unique = conn.execute("SELECT COUNT(DISTINCT plate_number) FROM detections").fetchone()[0]
        today = conn.execute("""
            SELECT COUNT(*) FROM detections
            WHERE date(created_at, 'localtime') = date('now', 'localtime')
        """).fetchone()[0]
        return {"total": total, "unique": unique, "today": today}

def update_plate(record_id, plate, details):
    with get_connection() as conn:
        conn.execute("""
            UPDATE detections
            SET plate_number=?, state_code=?, state_name=?, rto_code=?, rto_name=?, reviewed=1
            WHERE id=?
        """, (plate, details["state_code"], details["state_name"],
              details["rto_code"], details["rto_name"], record_id))
