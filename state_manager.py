"""Database-backed schedules and bookings, plus the room IP cache."""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from database import get_db

logger = logging.getLogger("ktv")

DATA_DIR = Path(__file__).parent / "data"
LEGACY_STATE_FILE = DATA_DIR / "state.json"
IP_MAP_FILE = DATA_DIR / "room_ip_map.json"
TZ = timezone(timedelta(hours=8))


def _write_json_atomic(path: Path, payload: object):
    """Write JSON through a unique temporary file, then atomically replace the target."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        temp_file.replace(path)
    finally:
        if temp_file.exists():
            temp_file.unlink()


class StateManager:
    """Manages asyncio tasks while persisting schedules and bookings in SQLite."""

    def __init__(self):
        self.auto_close_tasks: dict[str, "asyncio.Task"] = {}
        self.booking_tasks: dict[str, "asyncio.Task"] = {}
        self.device_worker_task: "asyncio.Task | None" = None
        self.ip_map: dict[str, str] = {}
        self._load_ip_map()

    def _load_ip_map(self):
        if IP_MAP_FILE.exists():
            try:
                self.ip_map = json.loads(IP_MAP_FILE.read_text(encoding="utf-8"))
            except Exception:
                self.ip_map = {}

    def save_ip_map(self, mapping: dict[str, str]):
        """Merge newly discovered rooms so a partial device response cannot erase the cache."""
        self.ip_map.update(mapping)
        _write_json_atomic(IP_MAP_FILE, self.ip_map)

    @property
    def now(self) -> datetime:
        return datetime.now(TZ)

    def migrate_legacy_state(self):
        """Import the former state.json once, then remove it after a successful commit."""
        if not LEGACY_STATE_FILE.exists():
            return
        try:
            legacy = json.loads(LEGACY_STATE_FILE.read_text(encoding="utf-8"))
            conn = get_db()
            try:
                for room_name, info in legacy.get("auto_close", {}).items():
                    if info.get("room_ip") and info.get("close_at"):
                        conn.execute(
                            """INSERT INTO auto_close_schedules
                               (room_name, room_ip, close_at, status, updated_at)
                               VALUES (?, ?, ?, 'pending', datetime('now', 'localtime'))
                               ON CONFLICT(room_name) DO UPDATE SET
                                 room_ip=excluded.room_ip, close_at=excluded.close_at,
                                 status='pending', updated_at=datetime('now', 'localtime')""",
                            (room_name, info["room_ip"], info["close_at"]),
                        )
                for booking in legacy.get("bookings", []):
                    booking_id = booking.get("id") or str(uuid.uuid4())
                    conn.execute(
                        """INSERT OR IGNORE INTO bookings
                           (id, room_ip, room_name, open_at, duration_type,
                            duration_minutes, package_id, customer_type,
                            member_id, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            booking_id, booking.get("room_ip", ""),
                            booking.get("room_name", ""), booking.get("open_at", ""),
                            booking.get("duration_type", "timed"),
                            booking.get("duration_minutes"), booking.get("package_id"),
                            booking.get("customer_type", "retail"),
                            booking.get("member_id"), booking.get("status", "pending"),
                        ),
                    )
                conn.commit()
            finally:
                conn.close()
            LEGACY_STATE_FILE.unlink()
            logger.info("Legacy state.json migrated to SQLite")
        except Exception as exc:
            logger.error(f"Legacy state migration failed: {exc}")

    def set_auto_close(self, room_name: str, room_ip: str, close_at: str | None):
        conn = get_db()
        try:
            if close_at is None:
                conn.execute("DELETE FROM auto_close_schedules WHERE room_name = ?", (room_name,))
            else:
                conn.execute(
                    """INSERT INTO auto_close_schedules
                       (room_name, room_ip, close_at, status, updated_at)
                       VALUES (?, ?, ?, 'pending', datetime('now', 'localtime'))
                       ON CONFLICT(room_name) DO UPDATE SET
                         room_ip=excluded.room_ip, close_at=excluded.close_at,
                         status='pending', updated_at=datetime('now', 'localtime')""",
                    (room_name, room_ip, close_at),
                )
            conn.commit()
        finally:
            conn.close()

    def get_auto_close(self, room_name: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT room_ip, close_at FROM auto_close_schedules WHERE room_name = ? AND status = 'pending'",
                (room_name,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all_auto_close(self) -> dict:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT room_name, room_ip, close_at FROM auto_close_schedules WHERE status = 'pending'"
            ).fetchall()
            return {row["room_name"]: {"room_ip": row["room_ip"], "close_at": row["close_at"]} for row in rows}
        finally:
            conn.close()

    def add_booking(self, booking: dict) -> str:
        booking_id = str(uuid.uuid4())
        conn = get_db()
        try:
            conn.execute(
                """INSERT INTO bookings
                   (id, room_ip, room_name, open_at, duration_type,
                    duration_minutes, package_id, customer_type, member_id, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')""",
                (
                    booking_id, booking["room_ip"], booking["room_name"], booking["open_at"],
                    booking.get("duration_type", "timed"), booking.get("duration_minutes"),
                    booking.get("package_id"), booking.get("customer_type", "retail"),
                    booking.get("member_id"),
                ),
            )
            conn.commit()
        finally:
            conn.close()
        booking["id"] = booking_id
        booking["status"] = "pending"
        return booking_id

    def get_bookings(self) -> list:
        conn = get_db()
        try:
            rows = conn.execute(
                """SELECT id, room_ip, room_name, open_at, duration_type,
                          duration_minutes, package_id, customer_type, member_id,
                          status, created_at, updated_at
                   FROM bookings
                   ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, open_at DESC
                   LIMIT 300"""
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_booking(self, booking_id: str) -> dict | None:
        conn = get_db()
        try:
            row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_active_bookings(self) -> list:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT * FROM bookings WHERE status = 'pending' ORDER BY open_at"
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def mark_booking(self, booking_id: str, status: str) -> bool:
        conn = get_db()
        try:
            cursor = conn.execute(
                """UPDATE bookings SET status = ?, updated_at = datetime('now', 'localtime')
                   WHERE id = ?""",
                (status, booking_id),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()


state_mgr = StateManager()