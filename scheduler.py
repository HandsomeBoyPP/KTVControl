"""KTV API helpers, durable device commands, and scheduled tasks."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta

import requests

from database import get_db, log_operation
from state_manager import state_mgr

logger = logging.getLogger("ktv")

KTV_API_BASE = "http://192.168.110.201:18888"


class StaleAutoCloseCommand(RuntimeError):
    """Raised when an old auto-close command no longer owns the room timer."""



def _auto_close_command_is_current(command: dict) -> bool:
    if command.get("action") != "auto_close":
        return True
    room_name = command.get("room_no") or ""
    prefix = f"auto-close:{room_name}:"
    key = command.get("idempotency_key") or ""
    if not room_name or not key.startswith(prefix):
        return False
    close_at = key[len(prefix):]
    current = state_mgr.get_auto_close(room_name)
    if not current or current.get("close_at") != close_at:
        return False
    try:
        payload = json.loads(command.get("payload_json") or "[]")
        room_ip = payload[0].get("room_ip") if payload else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return bool(
        room_ip
        and current.get("room_ip") == room_ip
    )


def _cancel_device_command(command_id: int, reason: str):
    conn = get_db()
    try:
        conn.execute(
            """UPDATE device_commands
               SET retryable = 0, status = 'cancelled', last_error = ?,
                   updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (reason[:500], command_id),
        )
        conn.commit()
    finally:
        conn.close()


async def ktv_get(path: str, params: dict | None = None) -> dict:
    def _do():
        resp = requests.get(f"{KTV_API_BASE}{path}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    return await asyncio.to_thread(_do)


async def ktv_post(path: str, data: list[dict]) -> dict:
    def _do():
        resp = requests.post(f"{KTV_API_BASE}{path}", json=data, timeout=10)
        resp.raise_for_status()
        return resp.json()
    return await asyncio.to_thread(_do)


def _enqueue_device_command(
    action: str,
    path: str,
    data: list[dict],
    room_name: str | None,
    idempotency_key: str,
    retryable: bool,
) -> int:
    conn = get_db()
    try:
        conn.execute(
            """INSERT OR IGNORE INTO device_commands
               (idempotency_key, action, api_path, payload_json, room_no, retryable)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                idempotency_key, action, path,
                json.dumps(data, ensure_ascii=False), room_name, int(retryable),
            ),
        )
        row = conn.execute(
            "SELECT id FROM device_commands WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        conn.commit()
        return int(row["id"])
    finally:
        conn.close()


async def _process_device_command(command_id: int) -> dict:
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM device_commands WHERE id = ?", (command_id,)).fetchone()
        if not row:
            raise RuntimeError("设备指令不存在")
        command = dict(row)
        if command["status"] == "succeeded":
            return json.loads(command["response_json"] or "{}")
        if command["status"] == "cancelled":
            raise StaleAutoCloseCommand(command["last_error"] or "设备指令已取消")
        if command["status"] == "processing":
            raise RuntimeError("设备指令正在执行")
        if not _auto_close_command_is_current(command):
            reason = "旧自动关台任务已失效，已阻止执行"
            conn.execute(
                """UPDATE device_commands
                   SET retryable = 0, status = 'cancelled', last_error = ?,
                       updated_at = datetime('now', 'localtime')
                   WHERE id = ?""",
                (reason, command_id),
            )
            conn.commit()
            raise StaleAutoCloseCommand(reason)
        claimed = conn.execute(
            """UPDATE device_commands
               SET status = 'processing', attempts = attempts + 1,
                   last_error = NULL, updated_at = datetime('now', 'localtime')
               WHERE id = ? AND status IN ('pending', 'failed')""",
            (command_id,),
        )
        conn.commit()
        if claimed.rowcount != 1:
            raise RuntimeError("设备指令已被其他服务进程接管")
    finally:
        conn.close()

    if not _auto_close_command_is_current(command):
        reason = "自动关台执行前计时已变更，已阻止旧任务"
        _cancel_device_command(command_id, reason)
        raise StaleAutoCloseCommand(reason)

    try:
        response = await ktv_post(command["api_path"], json.loads(command["payload_json"]))
    except Exception as exc:
        conn = get_db()
        try:
            conn.execute(
                """UPDATE device_commands
                   SET status = 'failed', last_error = ?,
                       updated_at = datetime('now', 'localtime')
                   WHERE id = ? AND status = 'processing'""",
                (str(exc)[:500], command_id),
            )
            conn.commit()
        finally:
            conn.close()
        raise

    conn = get_db()
    try:
        conn.execute(
            """UPDATE device_commands
               SET status = 'succeeded', response_json = ?, last_error = NULL,
                   updated_at = datetime('now', 'localtime')
               WHERE id = ? AND status = 'processing'""",
            (json.dumps(response, ensure_ascii=False), command_id),
        )
        conn.commit()
    finally:
        conn.close()
    return response

async def execute_device_command(
    action: str,
    path: str,
    data: list[dict],
    room_name: str | None = None,
    idempotency_key: str | None = None,
    retryable: bool = True,
    immediate_attempts: int = 1,
) -> dict:
    """Persist and execute one idempotent device command."""
    key = idempotency_key or f"{action}:{uuid.uuid4()}"
    command_id = _enqueue_device_command(action, path, data, room_name, key, retryable)
    last_error: Exception | None = None
    for attempt in range(max(1, immediate_attempts)):
        try:
            return await _process_device_command(command_id)
        except Exception as exc:
            last_error = exc
            if attempt + 1 < immediate_attempts:
                await asyncio.sleep(0.5 * (attempt + 1))
    raise last_error or RuntimeError("设备指令执行失败")


async def retry_device_commands_once():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id FROM device_commands
               WHERE retryable = 1 AND status IN ('pending', 'failed') AND attempts < 10
               ORDER BY id LIMIT 20"""
        ).fetchall()
    finally:
        conn.close()
    for row in rows:
        try:
            await _process_device_command(int(row["id"]))
        except asyncio.CancelledError:
            raise
        except StaleAutoCloseCommand as exc:
            logger.info(f"Skipped stale auto-close command id={row['id']}: {exc}")
        except Exception as exc:
            logger.warning(f"Device command retry failed id={row['id']}: {exc}")


async def _device_command_worker():
    while True:
        try:
            await retry_device_commands_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Device command worker error")
        await asyncio.sleep(30)


def start_device_command_worker():
    conn = get_db()
    try:
        conn.execute(
            """UPDATE device_commands SET status = 'failed', last_error = '服务重启后恢复'
               WHERE status = 'processing'"""
        )
        conn.commit()
    finally:
        conn.close()
    if state_mgr.device_worker_task is None or state_mgr.device_worker_task.done():
        state_mgr.device_worker_task = asyncio.create_task(_device_command_worker())


async def do_auto_close(room_ip: str, room_name: str, close_at_iso: str):
    while True:
        schedule_matches = state_mgr.auto_close_matches(
            room_name, room_ip, close_at_iso
        )
        if not schedule_matches:
            logger.info(
                f"[AutoClose skipped stale] {room_name} -> {close_at_iso} "
                f"schedule_matches={schedule_matches}"
            )
            current_task = asyncio.current_task()
            if state_mgr.auto_close_tasks.get(room_name) is current_task:
                state_mgr.auto_close_tasks.pop(room_name, None)
            return
        try:
            logger.info(f"[AutoClose] {room_name}")
            await execute_device_command(
                "auto_close", "/fangtai/close",
                [{"room_ip": room_ip, "room_name": room_name}],
                room_name=room_name,
                idempotency_key=f"auto-close:{room_name}:{close_at_iso}",
                retryable=True,
            )
            state_mgr.clear_auto_close_if_current(room_name, room_ip, close_at_iso)
            current_task = asyncio.current_task()
            if state_mgr.auto_close_tasks.get(room_name) is current_task:
                state_mgr.auto_close_tasks.pop(room_name, None)
            log_operation("auto_close", room_name, f"定时关台 IP={room_ip} 计划={close_at_iso}")
            logger.info(f"[AutoClose OK] {room_name}")
            return
        except asyncio.CancelledError:
            raise
        except StaleAutoCloseCommand as exc:
            state_mgr.clear_auto_close_if_current(
                room_name, room_ip, close_at_iso
            )
            logger.info(f"[AutoClose cancelled stale] {room_name}: {exc}")
            return
        except Exception as exc:
            logger.error(f"[AutoClose FAIL] {room_name}: {exc}, retry in 30s")
            await asyncio.sleep(30)

def schedule_auto_close(room_ip: str, room_name: str, close_at_iso: str):
    if room_name in state_mgr.auto_close_tasks:
        state_mgr.auto_close_tasks[room_name].cancel()
    close_at = datetime.fromisoformat(close_at_iso)
    delay = (close_at - state_mgr.now).total_seconds()
    if delay <= 0:
        logger.info(f"[AutoClose overdue] {room_name}")
        state_mgr.auto_close_tasks[room_name] = asyncio.create_task(
            do_auto_close(room_ip, room_name, close_at_iso)
        )
        return

    async def _wait_and_close():
        await asyncio.sleep(delay)
        await do_auto_close(room_ip, room_name, close_at_iso)

    state_mgr.auto_close_tasks[room_name] = asyncio.create_task(_wait_and_close())
    logger.info(f"[Scheduled] {room_name} -> {close_at_iso}")


def cancel_auto_close(
    room_ip: str, room_name: str, reason: str = "自动关台任务已取消"
):
    """Cancel every deferred auto-close path while keeping the room powered on."""
    task = state_mgr.auto_close_tasks.pop(room_name, None)
    if task:
        task.cancel()
    state_mgr.set_auto_close(room_name, room_ip, None)

    # Failed auto-close commands must never be retried against a later room session.
    conn = get_db()
    try:
        conn.execute(
            """UPDATE device_commands
               SET retryable = 0, status = 'cancelled',
                   last_error = ?, updated_at = datetime('now', 'localtime')
               WHERE action = 'auto_close' AND room_no = ?
                 AND status IN ('pending', 'failed', 'processing')""",
            (reason, room_name),
        )
        conn.commit()
    finally:
        conn.close()

async def do_booking_open(booking: dict):
    bid, rip, rname = booking["id"], booking["room_ip"], booking["room_name"]
    try:
        conn = get_db()
        try:
            existing = conn.execute(
                "SELECT id FROM billing_records WHERE booking_id = ? LIMIT 1", (bid,)
            ).fetchone()
            conflict = conn.execute(
                """SELECT id FROM billing_records
                   WHERE room_no = ? AND status = 'open'
                     AND (booking_id IS NULL OR booking_id <> ?)
                   LIMIT 1""",
                (rname, bid),
            ).fetchone()
        finally:
            conn.close()

        if conflict:
            raise RuntimeError("房间存在未结账账单，预订未执行")

        if not existing:
            logger.info(f"[Booking] {rname}")
            await execute_device_command(
                "booking_open", "/fangtai/open",
                [{"room_ip": rip, "room_name": rname}],
                room_name=rname,
                idempotency_key=f"booking-open:{bid}",
                retryable=False,
                immediate_attempts=2,
            )
            duration = booking.get("duration_minutes") or 0
            conn = get_db()
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO billing_records
                       (room_no, room_ip, package_id, booking_id, customer_type,
                        member_id, open_at, duration_minutes, room_fee, status)
                       VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?, 0, 'open')""",
                    (
                        rname, rip, booking.get("package_id"), bid,
                        booking.get("customer_type", "retail"), booking.get("member_id"), duration,
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        if booking.get("duration_type") == "timed" and booking.get("duration_minutes"):
            close_at = (state_mgr.now + timedelta(minutes=booking["duration_minutes"])).isoformat()
            state_mgr.set_auto_close(rname, rip, close_at)
            schedule_auto_close(rip, rname, close_at)

        state_mgr.mark_booking(bid, "completed")
        state_mgr.booking_tasks.pop(bid, None)
        log_operation("booking_open", rname, f"预订开台 IP={rip} duration={booking.get('duration_minutes', 0)}min")
        logger.info(f"[Booking OK] {rname}")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        state_mgr.mark_booking(bid, "failed")
        state_mgr.booking_tasks.pop(bid, None)
        log_operation("booking_failed", rname, str(exc))
        logger.error(f"[Booking FAIL] {rname}: {exc}")


def schedule_booking(booking: dict):
    open_at = datetime.fromisoformat(booking["open_at"])
    delay = (open_at - state_mgr.now).total_seconds()
    if delay <= 0:
        logger.info(f"[Booking overdue] {booking['room_name']}")
        state_mgr.booking_tasks[booking["id"]] = asyncio.create_task(do_booking_open(booking))
        return

    async def _wait_and_open():
        await asyncio.sleep(delay)
        await do_booking_open(booking)

    state_mgr.booking_tasks[booking["id"]] = asyncio.create_task(_wait_and_open())
    logger.info(f"[Booking scheduled] {booking['room_name']} -> {booking['open_at']}")


def restore_all_schedules():
    logger.info("Restoring schedules...")
    for room_name, info in list(state_mgr.get_all_auto_close().items()):
        try:
            schedule_auto_close(info["room_ip"], room_name, info["close_at"])
        except Exception as exc:
            logger.error(f"[Restore] invalid auto-close for {room_name}: {exc}")

    for booking in state_mgr.get_active_bookings():
        try:
            schedule_booking(booking)
        except Exception as exc:
            state_mgr.mark_booking(booking.get("id", ""), "failed")
            logger.error(f"[Restore] invalid booking: {exc}")