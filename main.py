"""KTV 前台控制系统 - FastAPI 后端"""

import asyncio
import json
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import init_db, get_db, log_operation, verify_admin_password, verify_records_password
from models import (
    AddDrinkRequest, BillingHistoryWriteRequest, BookingRequest, CreateInventoryRequest, CreateMemberRequest, CreateStaffRequest,
    CloseRequest, CreatePackageRequest, DeletePackageRequest, ExtendRequest, OpenRequest,
    ExpireMemberDrinkRequest, RechargeLogWriteRequest, RechargeRequest, ResetMemberPasswordRequest, RetrieveMemberDrinkRequest, SaveBillingDraftRequest, SettlementRequest,
    StoreMemberDrinkRequest, UpdateBillingRequest, UpdateInventoryRequest, UpdateMemberRequest, UpdatePackageRequest, UpdateStaffRequest,
    VerifyAdminRequest, VerifyMemberRequest, VerifyRecordsRequest, StaffCommissionRule,
)
from scheduler import (
    cancel_auto_close, execute_device_command, ktv_get, ktv_post, restore_all_schedules,
    schedule_auto_close, schedule_booking, start_device_command_worker,
)
from state_manager import state_mgr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ktv")


_INVENTORY_UNITS = {"酒水": "瓶", "饮料": "瓶", "零食": "份", "水果": "份"}


def _inventory_unit(category: str) -> str:
    return _INVENTORY_UNITS.get(category, "份")


def _inventory_tracks_stock(category: str) -> bool:
    return category in {"酒水", "饮料"}

def _get_package_price(pkg: dict) -> float:
    return float(pkg.get("price_normal", 0) or 0)


def _resolve_actual_total(subtotal: float, requested_total: float | None, notes: str | None):
    total = round(subtotal if requested_total is None else requested_total, 2)
    normalized_notes = (notes or "").strip() or None
    price_modified = abs(total - subtotal) >= 0.01
    if price_modified and len(normalized_notes or "") < 10:
        raise HTTPException(400, "修改实际收银价格后，备注必须填写且至少10个字")
    return total, normalized_notes, price_modified


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    state_mgr.migrate_legacy_state()
    restore_all_schedules()
    start_device_command_worker()
    try:
        yield
    finally:
        tasks = list(state_mgr.auto_close_tasks.values()) + list(state_mgr.booking_tasks.values())
        if state_mgr.device_worker_task:
            tasks.append(state_mgr.device_worker_task)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        state_mgr.auto_close_tasks.clear()
        state_mgr.booking_tasks.clear()
        state_mgr.device_worker_task = None



app = FastAPI(title="KTV Control", lifespan=lifespan)

# ---- Room Routes ----

@app.get("/api/rooms")
async def get_rooms():
    using_cache = False
    warning = None
    try:
        list_data = await ktv_get("/rooms/list", {"mdata": "{}"})
        all_rooms = list_data.get("result", {}).get("matches", [])
        rooms = [r for r in all_rooms if r.get("room_no", "").startswith("T")]
        ip_map = {r["room_ip"]: r["room_no"] for r in all_rooms if r.get("room_ip") and r.get("room_no")}
        state_mgr.save_ip_map(ip_map)
    except Exception as e:
        logger.warning(f"Cannot reach KTV room list, using cached room map: {e}")
        using_cache = True
        warning = "设备服务器暂时无法连接，当前显示缓存房间；设备恢复后会自动补全"
        conn = get_db()
        try:
            known_rooms = conn.execute(
                """SELECT room_ip, room_no FROM billing_records
                   WHERE room_ip IS NOT NULL AND room_ip <> '' AND room_no LIKE 'T%'
                   GROUP BY room_ip, room_no"""
            ).fetchall()
        finally:
            conn.close()
        recovered = {row["room_ip"]: row["room_no"] for row in known_rooms}
        if recovered:
            state_mgr.save_ip_map(recovered)
        rooms = [
            {
                "room_no": room_no, "room_name": room_no, "room_ip": room_ip,
                "room_mac": "", "room_state": 0, "room_type": 0,
                "stb_product": "", "stb_version": "",
            }
            for room_ip, room_no in state_mgr.ip_map.items()
            if room_no.startswith("T")
        ]
        if not rooms:
            raise HTTPException(502, f"无法连接 KTV 服务器，且没有房间缓存: {e}")
    try:
        status_data = await ktv_get("/rooms/status")
        powered_ips = set(status_data.get("result", []))
    except Exception:
        powered_ips = set()
    auto_close_map = state_mgr.get_all_auto_close()
    result = []
    for r in rooms:
        rn = r.get("room_no", "")
        ac_info = auto_close_map.get(rn, {})
        result.append({
            "room_no": rn, "room_name": r.get("room_name", ""),
            "room_ip": r.get("room_ip", ""), "room_mac": r.get("room_mac", ""),
            "room_state": r.get("room_state", 0), "room_type": r.get("room_type", 0),
            "stb_product": r.get("stb_product", ""), "stb_version": r.get("stb_version", ""),
            "powered_on": r.get("room_ip", "") in powered_ips,
            "auto_close_at": ac_info.get("close_at") if isinstance(ac_info, dict) else ac_info,
        })
    result.sort(key=lambda x: x["room_no"])
    return {"code": 0, "data": result, "source": "cache" if using_cache else "live", "warning": warning}


@app.get("/api/rooms/status")
async def get_room_status():
    try:
        status_data = await ktv_get("/rooms/status")
        powered_ips = status_data.get("result", [])
    except Exception as e:
        logger.warning(f"Cannot reach KTV status service: {e}")
        powered_ips = []
    mapped = [{"ip": ip, "room_no": state_mgr.ip_map.get(ip, "未知")} for ip in powered_ips]
    return {"code": 0, "data": mapped}


@app.post("/api/rooms/open")
async def open_room(req: OpenRequest):
    member_id = None
    customer_type = req.customer_type
    if customer_type != "retail":
        if not req.member_phone or not req.member_password:
            raise HTTPException(400, "会员消费需要手机号和密码")
        conn = get_db()
        try:
            member = conn.execute(
                "SELECT id, password FROM members WHERE phone = ?", (req.member_phone,)
            ).fetchone()
            if not member:
                raise HTTPException(404, "手机号未注册")
            if member["password"] != req.member_password:
                raise HTTPException(403, "会员密码错误")
            member_id = member["id"]
            customer_type = "member"
        finally:
            conn.close()

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT id FROM billing_records WHERE room_no = ? AND status = 'open' LIMIT 1", (req.room_name,)
        ).fetchone()
    finally:
        conn.close()
    if existing:
        raise HTTPException(409, "该房间存在未结账账单，请先结账")

    try:
        await execute_device_command(
            "open_room", "/fangtai/open",
            [{"room_ip": req.room_ip, "room_name": req.room_name}],
            room_name=req.room_name,
            idempotency_key=f"manual-open:{req.room_name}:{state_mgr.now.isoformat()}",
            retryable=False,
            immediate_attempts=2,
        )
    except Exception as e:
        raise HTTPException(502, f"开台设备指令失败: {e}")

    duration = req.duration_minutes if req.duration_type == "timed" else 0
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO billing_records
               (room_no, room_ip, customer_type, member_id, open_at, duration_minutes, room_fee, status)
               VALUES (?, ?, ?, ?, datetime('now', 'localtime'), ?, 0, 'open')""",
            (req.room_name, req.room_ip, customer_type, member_id, duration),
        )
        conn.commit()
        billing_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    except Exception as e:
        conn.rollback()
        try:
            await execute_device_command(
                "compensating_close", "/fangtai/close",
                [{"room_ip": req.room_ip, "room_name": req.room_name}],
                room_name=req.room_name,
                idempotency_key=f"compensating-close:{req.room_name}:{state_mgr.now.isoformat()}",
                retryable=True,
            )
        except Exception:
            logger.exception("Compensating close failed after billing creation error")
        raise HTTPException(500, f"创建开台账单失败: {e}")
    finally:
        conn.close()

    cancel_auto_close(req.room_ip, req.room_name, "房间重新开台，旧定时任务已失效")
    auto_close_at = None
    if req.duration_type == "timed":
        auto_close_at = (state_mgr.now + timedelta(minutes=duration)).isoformat()
        state_mgr.set_auto_close(req.room_name, req.room_ip, auto_close_at)
        schedule_auto_close(req.room_ip, req.room_name, auto_close_at)
    dur_str = "永久" if req.duration_type == "unlimited" else f"{duration}min"
    log_operation(
        "open_room", req.room_name,
        f"开台 IP={req.room_ip} duration={dur_str} auto_close_at={auto_close_at or '无'} billing={billing_id}",
    )
    return {
        "code": 0, "msg": "ok", "billing_id": billing_id,
        "duration_minutes": duration, "auto_close_at": auto_close_at,
    }
@app.post("/api/rooms/close")
async def close_room(req: CloseRequest):
    try:
        await execute_device_command(
            "close_room", "/fangtai/close",
            [{"room_ip": req.room_ip, "room_name": req.room_name}],
            room_name=req.room_name,
            idempotency_key=f"manual-close:{req.room_name}:{state_mgr.now.isoformat()}",
            retryable=True,
            immediate_attempts=2,
        )
    except Exception as e:
        raise HTTPException(502, f"关台设备指令已记录，将继续重试: {e}")
    log_operation("close_room", req.room_name, f"关台 IP={req.room_ip} (账单保留待结账)")
    cancel_auto_close(req.room_ip, req.room_name, "房间已手动关台")
    conn = get_db()
    try:
        billing = conn.execute(
            "SELECT id FROM billing_records WHERE room_no = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (req.room_name,),
        ).fetchone()
    finally:
        conn.close()
    return {"code": 0, "msg": "ok", "billing_id": billing["id"] if billing else None}


@app.post("/api/rooms/device-close")
async def device_close_room(req: CloseRequest):
    """Call the KTV close endpoint once without changing billing or timer state."""
    try:
        device_response = await ktv_post(
            "/fangtai/close",
            [{"room_ip": req.room_ip, "room_name": req.room_name}],
        )
    except Exception as e:
        raise HTTPException(502, f"设备关台失败: {e}")
    return {"code": 0, "msg": "ok", "device_response": device_response}


@app.post("/api/rooms/extend")
async def extend_room(req: ExtendRequest):
    try:
        await execute_device_command(
            "extend_room", "/fangtai/open",
            [{"room_ip": req.room_ip, "room_name": req.room_name}],
            room_name=req.room_name,
            idempotency_key=f"extend-room:{req.room_name}:{state_mgr.now.isoformat()}",
            retryable=True,
            immediate_attempts=2,
        )
    except Exception as e:
        logger.warning(f"续时设备指令已记录，将后台重试: {e}")

    duration = req.duration_minutes or 0
    conn = get_db()
    try:
        billing = conn.execute(
            "SELECT id, customer_type, member_id FROM billing_records WHERE room_no = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (req.room_name,)
        ).fetchone()
        if billing:
            conn.execute(
                "UPDATE billing_records SET duration_minutes = duration_minutes + ? WHERE id = ?",
                (duration, billing["id"])
            )
            conn.commit()
    finally:
        conn.close()

    existing = state_mgr.get_auto_close(req.room_name)
    base = state_mgr.now
    if existing and isinstance(existing, dict) and existing.get("close_at"):
        existing_dt = datetime.fromisoformat(existing["close_at"])
        if existing_dt > state_mgr.now:
            base = existing_dt
    close_at = (base + timedelta(minutes=duration)).isoformat()
    state_mgr.set_auto_close(req.room_name, req.room_ip, close_at)
    schedule_auto_close(req.room_ip, req.room_name, close_at)

    log_operation("extend_room", req.room_name, f"续时 IP={req.room_ip} +{duration}min")
    return {"code": 0, "msg": "ok", "auto_close_at": close_at}


# ---- Booking Routes ----

@app.get("/api/bookings")
async def list_bookings():
    return {"code": 0, "data": state_mgr.get_bookings()}


@app.post("/api/bookings")
async def create_booking(req: BookingRequest):
    try:
        open_at = datetime.fromisoformat(req.open_at)
        if open_at.tzinfo is None:
            open_at = open_at.replace(tzinfo=state_mgr.now.tzinfo)
    except ValueError:
        raise HTTPException(400, "预订时间格式无效")
    if open_at <= state_mgr.now:
        raise HTTPException(400, "预订时间必须晚于当前时间")

    member_id = None
    customer_type = req.customer_type
    if customer_type != "retail":
        if not req.member_phone or not req.member_password:
            raise HTTPException(400, "会员预订需要手机号和密码")
        conn = get_db()
        try:
            member = conn.execute(
                "SELECT id, password FROM members WHERE phone = ?", (req.member_phone,)
            ).fetchone()
            if not member:
                raise HTTPException(404, "手机号未注册")
            if member["password"] != req.member_password:
                raise HTTPException(403, "会员密码错误")
            member_id = member["id"]
            customer_type = "member"
        finally:
            conn.close()

    if req.package_id is not None:
        conn = get_db()
        try:
            package = conn.execute("SELECT id, type FROM packages WHERE id = ?", (req.package_id,)).fetchone()
            if not package or package["type"] != "open":
                raise HTTPException(400, "预订套餐不存在或不是开台套餐")
        finally:
            conn.close()

    booking = {
        "room_ip": req.room_ip,
        "room_name": req.room_name,
        "open_at": open_at.isoformat(),
        "duration_type": req.duration_type,
        "duration_minutes": req.duration_minutes,
        "package_id": req.package_id,
        "customer_type": customer_type,
        "member_id": member_id,
    }
    bid = state_mgr.add_booking(booking)
    schedule_booking(booking)
    log_operation("create_booking", req.room_name, f"预订开台时间={open_at.isoformat()}")
    return {"code": 0, "msg": "ok", "booking_id": bid}
@app.delete("/api/bookings/{booking_id}")
async def cancel_booking(booking_id: str):
    booking = state_mgr.get_booking(booking_id)

    if not booking:
        raise HTTPException(404, "预订不存在")
    state_mgr.mark_booking(booking_id, "cancelled")
    if booking_id in state_mgr.booking_tasks:
        state_mgr.booking_tasks[booking_id].cancel()
        del state_mgr.booking_tasks[booking_id]
    log_operation("cancel_booking", booking["room_name"], f"取消预订")
    return {"code": 0, "msg": "ok"}


# ---- Member Routes ----

@app.get("/api/members")
async def list_members():
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, name, phone, balance, remark, created_at FROM members ORDER BY id DESC").fetchall()
        return {"code": 0, "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/api/members")
async def create_member(req: CreateMemberRequest):
    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM members WHERE phone = ?", (req.phone,)).fetchone()
        if existing:
            raise HTTPException(400, "手机号已注册")
        pwd = req.phone[-4:] if len(req.phone) >= 4 else req.phone
        remark = (req.remark or "").strip() or None
        conn.execute(
            "INSERT INTO members (name, phone, password, level, remark) VALUES (?, ?, ?, ?, ?)",
            (req.name, req.phone, pwd, "会员", remark),
        )
        conn.commit()
        mid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        log_operation("create_member", None, f"新增会员 {req.name} phone={req.phone}")
        return {"code": 0, "msg": "ok", "id": mid}
    finally:
        conn.close()


@app.put("/api/members/{member_id}")
async def update_member(member_id: int, req: UpdateMemberRequest):
    conn = get_db()
    try:
        member = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        if not member:
            raise HTTPException(404, "会员不存在")
        if req.phone is not None and req.phone != member["phone"]:
            duplicate = conn.execute(
                "SELECT id FROM members WHERE phone = ? AND id <> ?", (req.phone, member_id)
            ).fetchone()
            if duplicate:
                raise HTTPException(400, "手机号已被其他会员使用")
        fields, values = [], []
        for field in ["name", "phone", "balance"]:
            if field not in req.model_fields_set:
                continue
            value = getattr(req, field)
            if value is None:
                continue
            fields.append(f"{field} = ?")
            values.append(round(value, 2) if field == "balance" else value)
        if "remark" in req.model_fields_set:
            fields.append("remark = ?")
            values.append((req.remark or "").strip() or None)
        if fields:
            values.append(member_id)
            conn.execute(f"UPDATE members SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        detail = f"修改会员 id={member_id}"
        if req.balance is not None and round(float(member["balance"] or 0), 2) != round(req.balance, 2):
            detail += f" 余额={float(member['balance'] or 0):.2f}->{req.balance:.2f}"
        log_operation("update_member", None, detail)
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


@app.post("/api/members/{member_id}/reset-password")
async def reset_member_password(member_id: int, req: ResetMemberPasswordRequest):
    conn = get_db()
    try:
        member = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        if not member:
            raise HTTPException(404, "会员不存在")
        conn.execute("UPDATE members SET password = ? WHERE id = ?", (req.new_password, member_id))
        conn.commit()
        log_operation("reset_member_password", None, f"重置会员密码 id={member_id}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


@app.post("/api/members/verify")
async def verify_member(req: VerifyMemberRequest):
    conn = get_db()
    try:
        member = conn.execute("SELECT id, name, phone, balance, password FROM members WHERE phone = ?", (req.phone,)).fetchone()
        if not member:
            raise HTTPException(404, "手机号未注册")
        if req.password and member["password"] != req.password:
            raise HTTPException(403, "密码错误")
        return {"code": 0, "data": {"id": member["id"], "name": member["name"], "balance": member["balance"], "member_type": "会员"}}
    finally:
        conn.close()


@app.post("/api/members/{member_id}/recharge")
async def recharge_member(member_id: int, req: RechargeRequest):
    conn = get_db()
    try:
        member = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
        if not member:
            raise HTTPException(404, "会员不存在")
        credited_total = round(req.amount + req.gift_amount, 2)
        new_balance = round(member["balance"] + credited_total, 2)
        conn.execute("UPDATE members SET balance = ? WHERE id = ?", (new_balance, member_id))
        conn.execute(
            """INSERT INTO recharge_logs
               (member_id, member_name, member_phone, amount, gift_amount,
                balance_after, payment_method, detail, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, '会员充卡', ?)""",
            (
                member_id, member["name"], member["phone"], req.amount, req.gift_amount,
                new_balance, req.payment_method, (req.notes or "").strip() or None,
            ),
        )
        conn.commit()
        log_operation(
            "recharge_member", None,
            f"会员充值 {member['name']} amount={req.amount:.2f} gift={req.gift_amount:.2f} "
            f"credited_total={credited_total:.2f} balance_after={new_balance:.2f}",
        )
        return {
            "code": 0, "msg": "ok", "balance": new_balance,
            "amount": round(req.amount, 2), "gift_amount": round(req.gift_amount, 2),
            "credited_total": credited_total,
        }
    finally:
        conn.close()


def _recharge_log_time(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M:%S")


@app.get("/api/recharge-logs")
async def list_recharge_logs(x_records_password: str = Header(default="")):
    if not verify_records_password(x_records_password):
        raise HTTPException(403, "记录查看密码错误")
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, member_id, member_name, member_phone, amount, gift_amount,
                      balance_after, payment_method, detail, notes, created_at
               FROM recharge_logs
               ORDER BY datetime(created_at) DESC, id DESC
               LIMIT 1000"""
        ).fetchall()
        return {"code": 0, "data": [dict(row) for row in rows]}
    finally:
        conn.close()


@app.post("/api/recharge-logs")
async def create_recharge_log(req: RechargeLogWriteRequest):
    if not verify_admin_password(req.admin_password):
        raise HTTPException(403, "管理密码错误")
    conn = get_db()
    try:
        member = conn.execute("SELECT id FROM members WHERE id = ?", (req.member_id,)).fetchone()
        if not member:
            raise HTTPException(404, "会员不存在")
        created_at = _recharge_log_time(req.created_at)
        conn.execute(
            """INSERT INTO recharge_logs
               (member_id, member_name, member_phone, amount, gift_amount,
                balance_after, payment_method, detail, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                req.member_id, req.member_name, req.member_phone,
                round(req.amount, 2), round(req.gift_amount, 2), round(req.balance_after, 2),
                req.payment_method, req.detail, (req.notes or "").strip() or None, created_at,
            ),
        )
        log_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        log_operation("create_recharge_log", None, f"手工新增充卡流水 id={log_id} member={req.member_name} amount={req.amount}")
        return {"code": 0, "msg": "ok", "id": log_id}
    finally:
        conn.close()


@app.put("/api/recharge-logs/{log_id}")
async def update_recharge_log(log_id: int, req: RechargeLogWriteRequest):
    if not verify_admin_password(req.admin_password):
        raise HTTPException(403, "管理密码错误")
    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM recharge_logs WHERE id = ?", (log_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "充卡流水不存在")
        member = conn.execute("SELECT id FROM members WHERE id = ?", (req.member_id,)).fetchone()
        if not member:
            raise HTTPException(404, "会员不存在")
        conn.execute(
            """UPDATE recharge_logs
               SET member_id = ?, member_name = ?, member_phone = ?, amount = ?, gift_amount = ?,
                   balance_after = ?, payment_method = ?, detail = ?, notes = ?, created_at = ?
               WHERE id = ?""",
            (
                req.member_id, req.member_name, req.member_phone,
                round(req.amount, 2), round(req.gift_amount, 2), round(req.balance_after, 2),
                req.payment_method, req.detail, (req.notes or "").strip() or None,
                _recharge_log_time(req.created_at), log_id,
            ),
        )
        conn.commit()
        log_operation("update_recharge_log", None, f"修改充卡流水 id={log_id} member={req.member_name} amount={req.amount}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


@app.delete("/api/recharge-logs/{log_id}")
async def delete_recharge_log(log_id: int, admin_password: str = ""):
    if not verify_admin_password(admin_password):
        raise HTTPException(403, "管理密码错误")
    conn = get_db()
    try:
        existing = conn.execute("SELECT * FROM recharge_logs WHERE id = ?", (log_id,)).fetchone()
        if not existing:
            raise HTTPException(404, "充卡流水不存在")
        conn.execute("DELETE FROM recharge_logs WHERE id = ?", (log_id,))
        conn.commit()
        log_operation("delete_recharge_log", None, f"删除充卡流水 id={log_id}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


def _stored_drink_dict(row, now: datetime | None = None) -> dict:
    data = dict(row)
    now = now or datetime.now()
    expires_at = datetime.fromisoformat(data["expires_at"])
    data["is_expired"] = expires_at < now
    data["days_remaining"] = max(0, (expires_at.date() - now.date()).days)
    return data


@app.get("/api/members/{member_id}/stored-drinks")
async def list_member_stored_drinks(member_id: int):
    conn = get_db()
    try:
        member = conn.execute(
            "SELECT id, name, phone FROM members WHERE id = ?", (member_id,)
        ).fetchone()
        if not member:
            raise HTTPException(404, "会员不存在")
        rows = conn.execute(
            """SELECT * FROM member_stored_drinks
               WHERE member_id = ? AND status = 'active' AND quantity > 0
               ORDER BY expires_at, id""",
            (member_id,),
        ).fetchall()
        logs = conn.execute(
            """SELECT id, storage_id, action, item_name, storage_kind, quantity,
                      remaining_level, before_quantity, after_quantity, detail, created_at
               FROM member_storage_logs WHERE member_id = ? ORDER BY id DESC LIMIT 100""",
            (member_id,),
        ).fetchall()
        now = datetime.now()
        return {
            "code": 0,
            "member": dict(member),
            "data": [_stored_drink_dict(row, now) for row in rows],
            "logs": [dict(row) for row in logs],
        }
    finally:
        conn.close()


@app.post("/api/members/{member_id}/stored-drinks")
async def store_member_drink(member_id: int, req: StoreMemberDrinkRequest):
    conn = get_db()
    try:
        member = conn.execute("SELECT id, name FROM members WHERE id = ?", (member_id,)).fetchone()
        if not member:
            raise HTTPException(404, "会员不存在")
        expired = conn.execute(
            """SELECT id FROM member_stored_drinks
               WHERE member_id = ? AND status = 'active' AND quantity > 0
                 AND datetime(expires_at) < datetime('now', 'localtime')
               LIMIT 1""",
            (member_id,),
        ).fetchone()
        if expired:
            raise HTTPException(409, "该会员存在过期存酒，请先完成过期处理")
        stored_at = datetime.now().replace(microsecond=0)
        expires_at = stored_at + timedelta(days=30)
        cursor = conn.execute(
            """INSERT INTO member_stored_drinks
               (member_id, item_name, storage_kind, quantity, remaining_level,
                storage_location, notes, stored_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                member_id, req.item_name, req.storage_kind, req.quantity,
                req.remaining_level if req.storage_kind == "opened" else None,
                req.storage_location or None, req.notes or None,
                stored_at.isoformat(sep=" "), expires_at.isoformat(sep=" "),
            ),
        )
        storage_id = cursor.lastrowid
        kind_label = "已开封" if req.storage_kind == "opened" else "未开封"
        detail = f"{kind_label}；位置={req.storage_location or '未填写'}；有效期30天"
        if req.notes:
            detail += f"；备注={req.notes}"
        conn.execute(
            """INSERT INTO member_storage_logs
               (member_id, storage_id, action, item_name, storage_kind, quantity,
                remaining_level, before_quantity, after_quantity, detail)
               VALUES (?, ?, 'store', ?, ?, ?, ?, 0, ?, ?)""",
            (
                member_id, storage_id, req.item_name, req.storage_kind, req.quantity,
                req.remaining_level if req.storage_kind == "opened" else None,
                req.quantity, detail,
            ),
        )
        conn.commit()
        log_operation(
            "store_member_drink", None,
            f"会员存酒 member={member['name']} id={member_id} 酒水={req.item_name} 数量={req.quantity} 到期={expires_at:%Y-%m-%d}",
        )
        return {
            "code": 0,
            "msg": "存酒成功",
            "id": storage_id,
            "expires_at": expires_at.isoformat(sep=" "),
        }
    finally:
        conn.close()


@app.post("/api/members/{member_id}/stored-drinks/{storage_id}/retrieve")
async def retrieve_member_drink(member_id: int, storage_id: int, req: RetrieveMemberDrinkRequest):
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        member = conn.execute("SELECT id, name FROM members WHERE id = ?", (member_id,)).fetchone()
        if not member:
            raise HTTPException(404, "会员不存在")
        stored = conn.execute(
            """SELECT * FROM member_stored_drinks
               WHERE id = ? AND member_id = ? AND status = 'active'""",
            (storage_id, member_id),
        ).fetchone()
        if not stored or stored["quantity"] <= 0:
            raise HTTPException(404, "存酒记录不存在或已全部取走")
        if stored["storage_kind"] == "opened" and req.quantity != stored["quantity"]:
            raise HTTPException(400, "已开封酒需要整条取出")
        if req.quantity > stored["quantity"]:
            raise HTTPException(400, f"取酒数量不能超过当前剩余 {stored['quantity']} 瓶")
        before_quantity = stored["quantity"]
        after_quantity = before_quantity - req.quantity
        status = "retrieved" if after_quantity == 0 else "active"
        conn.execute(
            """UPDATE member_stored_drinks
               SET quantity = ?, status = ?, updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (after_quantity, status, storage_id),
        )
        detail = req.notes or "会员到店取酒"
        conn.execute(
            """INSERT INTO member_storage_logs
               (member_id, storage_id, action, item_name, storage_kind, quantity,
                remaining_level, before_quantity, after_quantity, detail)
               VALUES (?, ?, 'retrieve', ?, ?, ?, ?, ?, ?, ?)""",
            (
                member_id, storage_id, stored["item_name"], stored["storage_kind"],
                req.quantity, stored["remaining_level"], before_quantity, after_quantity, detail,
            ),
        )
        conn.commit()
        log_operation(
            "retrieve_member_drink", None,
            f"会员取酒 member={member['name']} id={member_id} 酒水={stored['item_name']} 数量={req.quantity} 剩余={after_quantity}",
        )
        return {"code": 0, "msg": "取酒成功", "remaining_quantity": after_quantity}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@app.post("/api/members/{member_id}/stored-drinks/{storage_id}/expire")
async def process_expired_member_drink(
    member_id: int, storage_id: int, req: ExpireMemberDrinkRequest
):
    conn = get_db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        member = conn.execute(
            "SELECT id, name FROM members WHERE id = ?", (member_id,)
        ).fetchone()
        if not member:
            raise HTTPException(404, "会员不存在")
        stored = conn.execute(
            """SELECT * FROM member_stored_drinks
               WHERE id = ? AND member_id = ? AND status = 'active'""",
            (storage_id, member_id),
        ).fetchone()
        if not stored or stored["quantity"] <= 0:
            raise HTTPException(404, "存酒记录不存在或已处理")
        if datetime.fromisoformat(stored["expires_at"]) >= datetime.now():
            raise HTTPException(409, "存酒尚未过期，不能进行过期处理")

        quantity = int(stored["quantity"])
        if req.action == "inventory":
            inventory = conn.execute(
                "SELECT id, name, category, stock FROM inventory WHERE id = ?",
                (req.inventory_id,),
            ).fetchone()
            if not inventory:
                raise HTTPException(404, "库存商品不存在")
            if inventory["category"] != "酒水":
                raise HTTPException(400, "过期存酒只能转入酒水分类库存")
            before_stock = int(inventory["stock"] or 0)
            after_stock = before_stock + quantity
            conn.execute(
                "UPDATE inventory SET stock = ? WHERE id = ?",
                (after_stock, inventory["id"]),
            )
            conn.execute(
                """UPDATE member_stored_drinks
                   SET quantity = 0, status = 'expired_to_inventory',
                       updated_at = datetime('now', 'localtime')
                   WHERE id = ?""",
                (storage_id,),
            )
            detail = (
                f"过期处理：转入库存 {inventory['name']}；"
                f"库存 {before_stock}->{after_stock}"
            )
            conn.execute(
                """INSERT INTO member_storage_logs
                   (member_id, storage_id, action, item_name, storage_kind,
                    quantity, remaining_level, before_quantity, after_quantity, detail)
                   VALUES (?, ?, 'expire_to_inventory', ?, ?, ?, ?, ?, 0, ?)""",
                (
                    member_id, storage_id, stored["item_name"],
                    stored["storage_kind"], quantity, stored["remaining_level"],
                    quantity, detail,
                ),
            )
            conn.commit()
            log_operation(
                "expire_drink_to_inventory", None,
                f"过期存酒转库存 member={member['name']} 酒水={stored['item_name']} "
                f"数量={quantity} 库存商品={inventory['name']} 库存={before_stock}->{after_stock}",
            )
            return {
                "code": 0,
                "msg": "已转入库存",
                "inventory_id": inventory["id"],
                "stock": after_stock,
            }

        now = datetime.now().replace(microsecond=0)
        new_expires_at = now + timedelta(days=req.extend_days)
        conn.execute(
            """UPDATE member_stored_drinks
               SET expires_at = ?, updated_at = datetime('now', 'localtime')
               WHERE id = ?""",
            (new_expires_at.isoformat(sep=" "), storage_id),
        )
        detail = f"过期处理：从处理日起延长 {req.extend_days} 天，到期={new_expires_at:%Y-%m-%d}"
        conn.execute(
            """INSERT INTO member_storage_logs
               (member_id, storage_id, action, item_name, storage_kind,
                quantity, remaining_level, before_quantity, after_quantity, detail)
               VALUES (?, ?, 'expire_extend', ?, ?, ?, ?, ?, ?, ?)""",
            (
                member_id, storage_id, stored["item_name"], stored["storage_kind"],
                quantity, stored["remaining_level"], quantity, quantity, detail,
            ),
        )
        conn.commit()
        log_operation(
            "extend_expired_drink", None,
            f"过期存酒延期 member={member['name']} 酒水={stored['item_name']} "
            f"延长={req.extend_days}天 到期={new_expires_at:%Y-%m-%d}",
        )
        return {
            "code": 0,
            "msg": "有效期已延长",
            "expires_at": new_expires_at.isoformat(sep=" "),
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---- Package Routes ----

def _package_items_for(conn, package_id: int) -> list[dict]:
    rows = conn.execute(
        """SELECT id, package_id, item_type, inventory_id, item_name, qty, unit_label
           FROM package_items WHERE package_id = ? ORDER BY item_type, id""",
        (package_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def _replace_package_items(conn, package_id: int, items: list):
    conn.execute("DELETE FROM package_items WHERE package_id = ?", (package_id,))
    for item in items:
        if item.item_type == "drink":
            inventory = conn.execute(
                "SELECT id, category, name, unit_name FROM inventory WHERE id = ?",
                (item.inventory_id,),
            ).fetchone()
            if not inventory:
                raise HTTPException(400, "套餐酒水对应的库存商品不存在")
            if inventory["category"] not in {"酒水", "饮料"}:
                raise HTTPException(400, f"{inventory['name']}不是酒水或饮料分类，不能加入套餐酒水")
            inventory_id = inventory["id"]
            item_name = inventory["name"]
            unit_label = inventory["unit_name"] or "瓶"
        else:
            inventory_id = None
            item_name = (item.item_name or "").strip()
            unit_label = "份"
        conn.execute(
            """INSERT INTO package_items
               (package_id, item_type, inventory_id, item_name, qty, unit_label)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (package_id, item.item_type, inventory_id, item_name, item.qty, unit_label),
        )


def _sync_billing_package_items(conn, billing_id: int, package_id: int):
    old_rows = conn.execute(
        """SELECT inventory_id, stock_qty FROM drink_orders
           WHERE billing_id = ? AND source = 'package'""",
        (billing_id,),
    ).fetchall()
    for row in old_rows:
        if row["inventory_id"] and int(row["stock_qty"] or 0) > 0:
            conn.execute(
                "UPDATE inventory SET stock = stock + ? WHERE id = ?",
                (int(row["stock_qty"]), row["inventory_id"]),
            )
    conn.execute(
        "DELETE FROM drink_orders WHERE billing_id = ? AND source = 'package'",
        (billing_id,),
    )

    package_items = _package_items_for(conn, package_id)
    inventory_needs: dict[int, int] = {}
    inventories: dict[int, dict] = {}
    for item in package_items:
        if item["item_type"] != "drink":
            continue
        inventory_id = item["inventory_id"]
        inventory_needs[inventory_id] = inventory_needs.get(inventory_id, 0) + int(item["qty"])

    for inventory_id, needed in inventory_needs.items():
        inventory = conn.execute("SELECT * FROM inventory WHERE id = ?", (inventory_id,)).fetchone()
        if not inventory:
            raise HTTPException(400, "套餐中的酒水库存商品已被删除，请先修改套餐")
        if int(inventory["stock"] or 0) < needed:
            raise HTTPException(
                409,
                f"套餐酒水库存不足：{inventory['name']}需要{needed}{inventory['unit_name'] or '瓶'}，"
                f"当前仅有{inventory['stock']}{inventory['unit_name'] or '瓶'}",
            )
        inventories[inventory_id] = dict(inventory)

    for inventory_id, needed in inventory_needs.items():
        updated = conn.execute(
            "UPDATE inventory SET stock = stock - ? WHERE id = ? AND stock >= ?",
            (needed, inventory_id, needed),
        )
        if updated.rowcount != 1:
            raise HTTPException(409, "套餐酒水库存刚刚发生变化，请重试")

    for item in package_items:
        if item["item_type"] == "drink":
            inventory = inventories[item["inventory_id"]]
            stock_qty = int(item["qty"])
            unit_label = inventory["unit_name"] or item["unit_label"] or "瓶"
        else:
            stock_qty = 0
            unit_label = item["unit_label"] or "份"
        conn.execute(
            """INSERT INTO drink_orders
               (billing_id, inventory_id, item_name, qty, unit_price, source,
                package_item_id, sale_unit, unit_label, unit_size, stock_qty)
               VALUES (?, ?, ?, ?, 0, 'package', ?, 'unit', ?, 1, ?)""",
            (
                billing_id, item["inventory_id"], item["item_name"], item["qty"],
                item["id"], unit_label, stock_qty,
            ),
        )

    drinks_fee = round(float(conn.execute(
        "SELECT COALESCE(SUM(qty * unit_price), 0) FROM drink_orders WHERE billing_id = ?",
        (billing_id,),
    ).fetchone()[0] or 0), 2)
    conn.execute(
        "UPDATE billing_records SET package_id = ?, drinks_fee = ? WHERE id = ? AND status = 'open'",
        (package_id, drinks_fee, billing_id),
    )
    return drinks_fee


@app.get("/api/packages")
async def list_packages():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, type, duration_minutes, price_normal, created_at FROM packages ORDER BY type, duration_minutes"
        ).fetchall()
        result = []
        for row in rows:
            package = dict(row)
            package["items"] = _package_items_for(conn, row["id"])
            result.append(package)
        return {"code": 0, "data": result}
    finally:
        conn.close()


@app.post("/api/packages")
async def create_package(req: CreatePackageRequest):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO packages (name, type, duration_minutes, price_normal) VALUES (?, ?, ?, ?)",
            (req.name, req.type, req.duration_minutes, req.price_normal),
        )
        package_id = cursor.lastrowid
        _replace_package_items(conn, package_id, req.items)
        conn.commit()
        log_operation("create_package", None, f"新增套餐 {req.name} type={req.type} items={len(req.items)}")
        return {"code": 0, "msg": "ok", "id": package_id}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.put("/api/packages/{package_id}")
async def update_package(package_id: int, req: UpdatePackageRequest):
    conn = get_db()
    try:
        package = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
        if not package:
            raise HTTPException(404, "套餐不存在")
        fields, values = [], []
        for field in ["name", "type", "duration_minutes", "price_normal"]:
            value = getattr(req, field, None)
            if value is not None:
                fields.append(f"{field} = ?")
                values.append(value)
        if fields:
            values.append(package_id)
            conn.execute(f"UPDATE packages SET {', '.join(fields)} WHERE id = ?", values)
        if req.items is not None:
            _replace_package_items(conn, package_id, req.items)
        conn.commit()
        log_operation(
            "update_package", None,
            f"修改套餐 id={package_id}" + (f" items={len(req.items)}" if req.items is not None else ""),
        )
        return {"code": 0, "msg": "ok"}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.delete("/api/packages/{package_id}")
async def delete_package(package_id: int, req: DeletePackageRequest):
    if not verify_admin_password(req.admin_password):
        raise HTTPException(403, "管理密码错误")
    conn = get_db()
    try:
        package = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
        if not package:
            raise HTTPException(404, "套餐不存在")
        conn.execute("DELETE FROM packages WHERE id = ?", (package_id,))
        conn.commit()
        log_operation("delete_package", None, f"删除套餐 {package['name']}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()

# ---- Inventory Routes ----

@app.get("/api/inventory")
async def list_inventory():
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT i.*,
                      CASE WHEN i.category = '酒水'
                           THEN COALESCE(s.stored_quantity, 0)
                           ELSE 0
                      END AS stored_quantity
               FROM inventory i
               LEFT JOIN (
                   SELECT LOWER(TRIM(item_name)) AS normalized_name,
                          SUM(quantity) AS stored_quantity
                   FROM member_stored_drinks
                   WHERE status = 'active' AND quantity > 0
                   GROUP BY LOWER(TRIM(item_name))
               ) s ON s.normalized_name = LOWER(TRIM(i.name))
               ORDER BY i.category, i.name"""
        ).fetchall()
        return {"code": 0, "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/api/inventory")
async def create_inventory(req: CreateInventoryRequest):
    conn = get_db()
    try:
        unit_name = _inventory_unit(req.category)
        case_size = req.case_size if req.category == "酒水" and req.case_size >= 2 else 0
        case_price = req.case_price if case_size else 0
        cursor = conn.execute(
            """INSERT INTO inventory
               (category, name, unit_name, unit_price, case_size, case_price,
                cost_price, stock, low_stock)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                req.category, req.name.strip(), unit_name, req.unit_price,
                case_size, case_price, req.cost_price, req.stock, req.low_stock,
            ),
        )
        conn.commit()
        item_id = cursor.lastrowid
        log_operation(
            "create_inventory", None,
            f"新增库存 {req.name} 单位={unit_name} 箱规={case_size} 库存={req.stock}",
        )
        return {"code": 0, "msg": "ok", "id": item_id}
    finally:
        conn.close()

@app.put("/api/inventory/{item_id}")
async def update_inventory(item_id: int, req: UpdateInventoryRequest):
    conn = get_db()
    try:
        item = conn.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(404, "物品不存在")
        stock_changed = req.stock is not None and req.stock != item["stock"]
        if stock_changed and not verify_admin_password(req.admin_password or ""):
            raise HTTPException(403, "手动修改库存量需要正确的管理密码")

        updates = req.model_dump(exclude_unset=True, exclude_none=True)
        updates.pop("admin_password", None)
        if "name" in updates:
            updates["name"] = updates["name"].strip()
        effective_category = updates.get("category", item["category"])
        updates["unit_name"] = _inventory_unit(effective_category)
        if effective_category != "酒水":
            updates["case_size"] = 0
            updates["case_price"] = 0
        elif "case_size" in updates and updates["case_size"] < 2:
            updates["case_size"] = 0
            updates["case_price"] = 0
        allowed_fields = {
            "category", "name", "unit_name", "unit_price", "case_size",
            "case_price", "cost_price", "stock", "low_stock",
        }
        fields, values = [], []
        for field, value in updates.items():
            if field not in allowed_fields:
                continue
            fields.append(f"{field} = ?")
            values.append(value)
        if fields:
            values.append(item_id)
            conn.execute(f"UPDATE inventory SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        detail = f"修改库存 id={item_id}"
        if stock_changed:
            detail += f" 数量={item['stock']}->{req.stock}"
        log_operation("update_inventory", None, detail)
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()

@app.delete("/api/inventory/{item_id}")
async def delete_inventory(item_id: int):
    conn = get_db()
    try:
        item = conn.execute("SELECT * FROM inventory WHERE id = ?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(404, "库存物品不存在")
        package_use = conn.execute(
            "SELECT package_id FROM package_items WHERE inventory_id = ? LIMIT 1", (item_id,)
        ).fetchone()
        if package_use:
            raise HTTPException(409, "该酒水正在套餐中使用，请先修改相关套餐后再删除")
        conn.execute("DELETE FROM inventory WHERE id = ?", (item_id,))
        conn.commit()
        log_operation("delete_inventory", None, f"删除库存 {item['name']}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


# ---- Staff Routes ----

@app.get("/api/staff")
async def list_staff():
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM staff ORDER BY status, id DESC"
        ).fetchall()
        result = []
        for row in rows:
            person = dict(row)
            person["commission_rule"] = json.loads(person.get("commission_rule") or "{}")
            result.append(person)
        return {"code": 0, "data": result}
    finally:
        conn.close()


@app.post("/api/staff")
async def create_staff(req: CreateStaffRequest):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO staff (name, phone, position, status, salary, notes, commission_rule) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (req.name, req.phone, req.position, req.status, req.salary, req.notes,
             json.dumps(req.commission_rule.model_dump(), ensure_ascii=False)),
        )
        conn.commit()
        staff_id = cursor.lastrowid
        log_operation("create_staff", None, f"新增店内人员 {req.name} 岗位={req.position}")
        return {"code": 0, "msg": "ok", "id": staff_id}
    finally:
        conn.close()


@app.put("/api/staff/{staff_id}")
async def update_staff(staff_id: int, req: UpdateStaffRequest):
    conn = get_db()
    try:
        if not conn.execute("SELECT id FROM staff WHERE id = ?", (staff_id,)).fetchone():
            raise HTTPException(404, "店内人员不存在")
        fields, values = [], []
        for field in ["name", "phone", "position", "status", "salary", "notes", "commission_rule"]:
            if field not in req.model_fields_set:
                continue
            value = getattr(req, field)
            if value is None and field not in {"phone", "notes"}:
                continue
            if field == "commission_rule":
                value = json.dumps(value.model_dump(), ensure_ascii=False)
            fields.append(f"{field} = ?")
            values.append(value)
        if fields:
            values.append(staff_id)
            conn.execute(f"UPDATE staff SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        log_operation("update_staff", None, f"修改店内人员 id={staff_id}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


@app.delete("/api/staff/{staff_id}")
async def delete_staff(staff_id: int):
    conn = get_db()
    try:
        staff = conn.execute("SELECT name FROM staff WHERE id = ?", (staff_id,)).fetchone()
        if not staff:
            raise HTTPException(404, "店内人员不存在")
        conn.execute("DELETE FROM staff WHERE id = ?", (staff_id,))
        conn.commit()
        log_operation("delete_staff", None, f"删除店内人员 {staff['name']}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()

# ---- Billing / Settlement Routes ----

def _resolve_performance_staff(conn, staff_id: int, *, allow_inactive=False, existing=None):
    """Snapshot ownership and rules; bill.total is the performance amount."""
    if staff_id == 0:
        return 0, None, None
    person = conn.execute("SELECT * FROM staff WHERE id = ?", (staff_id,)).fetchone()
    if not person:
        if allow_inactive and existing and existing["performance_staff_id"] == staff_id:
            return staff_id, existing["performance_staff_name"], existing["performance_commission_rule"]
        raise HTTPException(400, "业绩归属人员不存在，请重新选择或选择无")
    rule = json.loads(person["commission_rule"] or "{}")
    if rule.get("type") not in {"marketing", "manager"}:
        raise HTTPException(400, "业绩只能归属营销人员或经理")
    if not allow_inactive and person["status"] != "在职":
        raise HTTPException(400, "业绩归属人员已离职，请重新选择或选择无")
    return staff_id, person["name"], json.dumps(rule, ensure_ascii=False)

@app.get("/api/billing/active")
async def list_active_billing():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM billing_records WHERE status = 'open' ORDER BY id DESC").fetchall()
        result = []
        for r in rows:
            bill = dict(r)
            drinks = conn.execute("SELECT * FROM drink_orders WHERE billing_id = ?", (r["id"],)).fetchall()
            bill["drinks"] = [dict(d) for d in drinks]
            payments = conn.execute(
                """SELECT payment_method AS method, amount
                   FROM billing_payments WHERE billing_id = ? ORDER BY id""",
                (r["id"],),
            ).fetchall()
            bill["payment_breakdown"] = [dict(payment) for payment in payments]
            result.append(bill)
        return {"code": 0, "data": result}
    finally:
        conn.close()


@app.put("/api/billing/{billing_id}/draft")
async def save_billing_draft(billing_id: int, req: SaveBillingDraftRequest):
    conn = get_db()
    try:
        billing = conn.execute(
            "SELECT * FROM billing_records WHERE id = ? AND status = 'open'", (billing_id,)
        ).fetchone()
        if not billing:
            raise HTTPException(404, "账单不存在或已结账")
        performance_id, performance_name, performance_rule = _resolve_performance_staff(conn, req.performance_staff_id)
        package = conn.execute("SELECT * FROM packages WHERE id = ?", (req.package_id,)).fetchone()
        if not package or package["type"] != "open":
            raise HTTPException(400, "开台套餐不存在")

        room_fee = _get_package_price(dict(package))
        drinks_fee = _sync_billing_package_items(conn, billing_id, req.package_id)
        subtotal = round(room_fee + drinks_fee, 2)
        total, notes, price_modified = _resolve_actual_total(subtotal, req.actual_total, req.notes)

        if req.payment_splits:
            payment_breakdown = [
                {"method": item.payment_method, "amount": round(item.amount, 2)}
                for item in req.payment_splits
            ]
            split_total = round(sum(item["amount"] for item in payment_breakdown), 2)
            if abs(split_total - total) >= 0.01:
                raise HTTPException(
                    400, f"组合支付合计{split_total:.2f}元，与实收金额{total:.2f}元不一致"
                )
            saved_payment_method = "+".join(item["method"] for item in payment_breakdown)
        else:
            saved_payment_method = req.payment_method
            payment_breakdown = (
                [{"method": saved_payment_method, "amount": total}]
                if saved_payment_method else []
            )

        conn.execute(
            """UPDATE billing_records
               SET package_id = ?, room_fee = ?, drinks_fee = ?, total = ?,
                   discount = 0, payment_method = ?, notes = ?,
                   performance_staff_id = ?, performance_staff_name = ?, performance_commission_rule = ?
               WHERE id = ? AND status = 'open'""",
            (req.package_id, room_fee, drinks_fee, total, saved_payment_method, notes,
             performance_id, performance_name, performance_rule, billing_id),
        )
        drinks = [dict(row) for row in conn.execute(
            "SELECT * FROM drink_orders WHERE billing_id = ? ORDER BY id", (billing_id,)
        ).fetchall()]
        conn.execute("DELETE FROM billing_payments WHERE billing_id = ?", (billing_id,))
        if payment_breakdown:
            conn.executemany(
                """INSERT INTO billing_payments (billing_id, payment_method, amount)
                   VALUES (?, ?, ?)""",
                [
                    (billing_id, item["method"], item["amount"])
                    for item in payment_breakdown
                ],
            )
        conn.commit()
        log_operation(
            "save_billing_draft", billing["room_no"],
            f"billing={billing_id} package={req.package_id} drinks_fee={drinks_fee} "
            f"calculated_total={subtotal} actual_total={total} price_modified={price_modified} "
            f"payment={payment_breakdown} performance_staff={performance_name or '无'} performance_amount={total} notes={notes or ''}",
        )
        return {
            "code": 0, "msg": "ok", "billing_id": billing_id,
            "package_id": req.package_id, "room_fee": room_fee,
            "drinks_fee": drinks_fee, "calculated_total": subtotal,
            "total": total, "price_modified": price_modified,
            "payment_method": saved_payment_method,
            "payment_breakdown": payment_breakdown,
            "notes": notes, "drinks": drinks,
            "performance_staff_id": performance_id,
            "performance_staff_name": performance_name,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@app.put("/api/billing/{billing_id}")
async def update_active_billing(billing_id: int, req: UpdateBillingRequest):
    conn = get_db()
    try:
        billing = conn.execute(
            "SELECT * FROM billing_records WHERE id = ? AND status = 'open'", (billing_id,)
        ).fetchone()
        if not billing:
            raise HTTPException(404, "账单不存在或已结账")
        fields, values = [], []
        if "duration_minutes" in req.model_fields_set and req.duration_minutes is not None:
            fields.append("duration_minutes = ?")
            values.append(req.duration_minutes)
        if "notes" in req.model_fields_set:
            fields.append("notes = ?")
            values.append(req.notes)
        if fields:
            values.append(billing_id)
            conn.execute(f"UPDATE billing_records SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        log_operation(
            "update_billing", billing["room_no"],
            f"编辑账单 id={billing_id} duration={req.duration_minutes} notes={req.notes or ''}",
        )
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()

@app.post("/api/billing/add-drink")
async def add_drink(req: AddDrinkRequest):
    conn = get_db()
    try:
        billing = conn.execute(
            "SELECT * FROM billing_records WHERE id = ? AND status = 'open'", (req.billing_id,)
        ).fetchone()
        if not billing:
            raise HTTPException(404, "账单不存在或已结账")
        inv = conn.execute("SELECT * FROM inventory WHERE id = ?", (req.inventory_id,)).fetchone()
        if not inv:
            raise HTTPException(404, "库存物品不存在")

        if req.sale_unit == "case":
            if inv["category"] != "酒水":
                raise HTTPException(400, "只有酒水分类可以整箱销售")
            unit_size = int(inv["case_size"] or 0)
            if unit_size < 2 or float(inv["case_price"] or 0) <= 0:
                raise HTTPException(400, "该物品没有设置有效的整箱规格和价格")
            unit_price = round(float(inv["case_price"] or 0), 2)
            unit_label = "箱"
        else:
            unit_size = 1
            unit_price = round(float(inv["unit_price"] or 0), 2)
            unit_label = inv["unit_name"] or _inventory_unit(inv["category"])

        stock_qty = req.qty * unit_size if _inventory_tracks_stock(inv["category"]) else 0
        if stock_qty > 0:
            updated = conn.execute(
                "UPDATE inventory SET stock = stock - ? WHERE id = ? AND stock >= ?",
                (stock_qty, inv["id"], stock_qty),
            )
            if updated.rowcount != 1:
                raise HTTPException(409, f"库存不足，需要{stock_qty}{inv['unit_name'] or _inventory_unit(inv['category'])}")

        amount = round(req.qty * unit_price, 2)
        cursor = conn.execute(
            """INSERT INTO drink_orders
               (billing_id, inventory_id, item_name, qty, unit_price, sale_unit,
                unit_label, unit_size, stock_qty)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                req.billing_id, inv["id"], inv["name"], req.qty, unit_price,
                req.sale_unit, unit_label, unit_size, stock_qty,
            ),
        )
        conn.execute(
            "UPDATE billing_records SET drinks_fee = drinks_fee + ? WHERE id = ?",
            (amount, req.billing_id),
        )
        conn.commit()
        label = "赠送" if unit_price == 0 else "添加"
        stock_detail = f"{stock_qty}{inv['unit_name'] or _inventory_unit(inv['category'])}" if stock_qty > 0 else "不联动库存"
        log_operation(
            "add_drink", billing["room_no"],
            f"{label} {inv['name']} x{req.qty}{unit_label} @{unit_price} "
            f"扣库={stock_detail} billing={req.billing_id}",
        )
        return {
            "code": 0, "msg": "ok", "id": cursor.lastrowid,
            "stock_deducted": stock_qty, "amount": amount,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
@app.delete("/api/billing/drink/{drink_id}")
async def delete_drink(drink_id: int):
    conn = get_db()
    try:
        drink = conn.execute("SELECT * FROM drink_orders WHERE id = ?", (drink_id,)).fetchone()
        if not drink:
            raise HTTPException(404, "明细不存在")
        if drink["source"] == "package":
            raise HTTPException(400, "套餐内含项目不能单独删除，请更换或修改套餐")
        billing = conn.execute(
            "SELECT * FROM billing_records WHERE id = ? AND status = 'open'", (drink["billing_id"],)
        ).fetchone()
        if not billing:
            raise HTTPException(400, "账单已结账，无法修改")

        amount = round(drink["qty"] * drink["unit_price"], 2)
        stock_qty = int(drink["stock_qty"] if drink["stock_qty"] is not None else drink["qty"])
        conn.execute(
            "UPDATE billing_records SET drinks_fee = MAX(0, drinks_fee - ?) WHERE id = ?",
            (amount, drink["billing_id"]),
        )
        if stock_qty > 0 and drink["inventory_id"]:
            conn.execute(
                "UPDATE inventory SET stock = stock + ? WHERE id = ?",
                (stock_qty, drink["inventory_id"]),
            )
        elif stock_qty > 0:
            conn.execute(
                "UPDATE inventory SET stock = stock + ? WHERE name = ?",
                (stock_qty, drink["item_name"]),
            )
        conn.execute("DELETE FROM drink_orders WHERE id = ?", (drink_id,))
        conn.commit()
        log_operation(
            "delete_drink", billing["room_no"],
            f"删除明细 {drink['item_name']} x{drink['qty']}{drink['unit_label'] or ''} "
            f"退库={stock_qty}",
        )
        return {"code": 0, "msg": "ok", "stock_returned": stock_qty}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
@app.post("/api/billing/settle")
async def settle_billing(req: SettlementRequest):
    conn = get_db()
    try:
        billing = conn.execute(
            "SELECT * FROM billing_records WHERE id = ? AND status = 'open'", (req.billing_id,)
        ).fetchone()
        if not billing:
            raise HTTPException(404, "账单不存在或已结账")
        performance_id, performance_name, performance_rule = _resolve_performance_staff(conn, req.performance_staff_id)
        pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (req.package_id,)).fetchone()
        if not pkg or pkg["type"] != "open":
            raise HTTPException(400, "开台套餐不存在")

        room_fee = _get_package_price(dict(pkg))
        drinks_fee = _sync_billing_package_items(conn, req.billing_id, req.package_id)
        subtotal = round(room_fee + drinks_fee, 2)
        total, notes, price_modified = _resolve_actual_total(subtotal, req.actual_total, req.notes)

        if req.payment_splits:
            payment_breakdown = [
                {"method": item.payment_method, "amount": round(item.amount, 2)}
                for item in req.payment_splits
            ]
            split_total = round(sum(item["amount"] for item in payment_breakdown), 2)
            if abs(split_total - total) >= 0.01:
                raise HTTPException(
                    400, f"组合支付合计{split_total:.2f}元，与实收金额{total:.2f}元不一致"
                )
            payment_method = "+".join(item["method"] for item in payment_breakdown)
        else:
            payment_method = req.payment_method
            payment_breakdown = [{"method": payment_method, "amount": total}]

        member = None
        member_balance_before = None
        member_balance_after = None
        settlement_member_id = None
        settlement_member_name = None
        settlement_member_phone = None
        if payment_method == "会员余额":
            if req.member_phone:
                member = conn.execute("SELECT * FROM members WHERE phone = ?", (req.member_phone,)).fetchone()
            elif billing["member_id"]:
                member = conn.execute("SELECT * FROM members WHERE id = ?", (billing["member_id"],)).fetchone()
            else:
                raise HTTPException(400, "请输入会员手机号")
            if not member:
                raise HTTPException(404, "会员不存在")
            if not req.member_password or member["password"] != req.member_password:
                raise HTTPException(403, "会员密码错误")
            balance = round(float(member["balance"] or 0), 2)
            member_balance_before = balance
            if balance < total:
                raise HTTPException(400, f"会员余额不足，当前余额{balance:.2f}元，请先充值或选择其他支付方式")
            member_balance_after = round(balance - total, 2)
            settlement_member_id = member["id"]
            settlement_member_name = member["name"]
            settlement_member_phone = member["phone"]
            conn.execute(
                "UPDATE members SET balance = ? WHERE id = ?", (member_balance_after, member["id"])
            )

        if payment_method != "\u4f1a\u5458\u4f59\u989d" and billing["member_id"]:
            member = conn.execute("SELECT * FROM members WHERE id = ?", (billing["member_id"],)).fetchone()
            if member:
                settlement_member_id = member["id"]
                settlement_member_name = member["name"]
                settlement_member_phone = member["phone"]
                member_balance_before = round(float(member["balance"] or 0), 2)
                member_balance_after = member_balance_before


        conn.execute(
            """UPDATE billing_records
               SET package_id = ?, close_at = datetime('now', 'localtime'),
                   room_fee = ?, drinks_fee = ?, total = ?, discount = 0,
                   cash_supplement = 0, payment_method = ?, notes = ?,
                   settlement_member_id = ?, settlement_member_name = ?,
                   settlement_member_phone = ?, member_balance_after = ?,
                   performance_staff_id = ?, performance_staff_name = ?, performance_commission_rule = ?,
                   status = 'closed'
               WHERE id = ?""",
            (
                req.package_id, room_fee, drinks_fee, total, payment_method, notes,
                settlement_member_id, settlement_member_name, settlement_member_phone,
                member_balance_after, performance_id, performance_name, performance_rule, req.billing_id,
            ),
        )
        conn.execute("DELETE FROM billing_payments WHERE billing_id = ?", (req.billing_id,))
        conn.executemany(
            """INSERT INTO billing_payments (billing_id, payment_method, amount)
               VALUES (?, ?, ?)""",
            [
                (req.billing_id, item["method"], item["amount"])
                for item in payment_breakdown
            ],
        )
        conn.commit()

        room_name = billing["room_no"]
        member_detail = ""
        if settlement_member_id is not None:
            member_detail = (
                f" member={settlement_member_name} phone={settlement_member_phone}"
                f" balance_before={member_balance_before:.2f}"
                f" balance_after={member_balance_after:.2f}"
            )
        log_operation(
            "settle_billing", room_name,
            f"结账 room_fee={room_fee} drinks_fee={drinks_fee} calculated_total={subtotal} "
            f"actual_total={total} price_modified={price_modified} payment={payment_breakdown} "
            f"notes={notes or ''} performance_staff={performance_name or '无'} performance_amount={total} room_kept_open=true{member_detail}",
        )
        return {
            "code": 0, "msg": "ok", "total": total, "room_fee": room_fee,
            "calculated_total": subtotal, "cash_supplement": 0,
            "payment_method": payment_method, "payment_breakdown": payment_breakdown,
            "price_modified": price_modified,
            "notes": notes, "room_kept_open": True,
            "settlement_member_name": settlement_member_name,
            "settlement_member_phone": settlement_member_phone,
            "performance_staff_id": performance_id,
            "performance_staff_name": performance_name,
            "member_balance_after": member_balance_after,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _attach_billing_payment_breakdowns(conn, bills: list[dict]) -> None:
    """Attach split payments; legacy bills fall back to their single payment method."""
    billing_ids = [bill["id"] for bill in bills if bill.get("id") is not None]
    payment_map = {}
    if billing_ids:
        placeholders = ",".join("?" for _ in billing_ids)
        rows = conn.execute(
            f"""SELECT billing_id, payment_method, amount
                FROM billing_payments
                WHERE billing_id IN ({placeholders})
                ORDER BY billing_id, id""",
            billing_ids,
        ).fetchall()
        for row in rows:
            payment_map.setdefault(row["billing_id"], []).append({
                "method": row["payment_method"],
                "amount": round(float(row["amount"] or 0), 2),
            })
    for bill in bills:
        payments = payment_map.get(bill.get("id"), [])
        if not payments:
            method = (bill.get("payment_method") or "未填写").strip() or "未填写"
            payments = [{
                "method": method,
                "amount": round(float(bill.get("total") or 0), 2),
            }]
        bill["payment_breakdown"] = payments

# ---- Business Report Routes ----

def _business_day_bounds(date: str = "") -> tuple[datetime, datetime]:
    now = datetime.now()
    if date:
        try:
            business_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "日期格式应为 YYYY-MM-DD")
    else:
        business_date = now if now.hour >= 6 else now - timedelta(days=1)
    start_at = business_date.replace(hour=6, minute=0, second=0, microsecond=0)
    return start_at, start_at + timedelta(days=1)


def _build_daily_business_report(date: str = "") -> dict:
    """Build one live business day from source billing and recharge records."""
    start_at, end_at = _business_day_bounds(date)

    start_text = start_at.strftime("%Y-%m-%d %H:%M:%S")
    end_text = end_at.strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT b.id, b.room_no, b.package_id, b.room_fee, b.drinks_fee,
                      b.total, b.payment_method, b.settlement_member_name,
                      b.settlement_member_phone, b.notes, b.open_at, b.close_at,
                      p.name AS package_name
               FROM billing_records b
               LEFT JOIN packages p ON p.id = b.package_id
               WHERE b.status = 'closed'
                 AND COALESCE(NULLIF(b.open_at, ''), b.close_at) >= ?
                 AND COALESCE(NULLIF(b.open_at, ''), b.close_at) < ?
               ORDER BY COALESCE(NULLIF(b.open_at, ''), b.close_at) DESC, b.id DESC""",
            (start_text, end_text),
        ).fetchall()
        bills = [dict(row) for row in rows]
        _attach_billing_payment_breakdowns(conn, bills)

        payment_totals = {}
        business_total = 0.0
        checkout_received_total = 0.0
        member_balance_total = 0.0
        for bill in bills:
            business_total += float(bill.get("total") or 0)
            for payment in bill["payment_breakdown"]:
                amount = float(payment.get("amount") or 0)
                method = (payment.get("method") or "未填写").strip() or "未填写"
                payment_totals[method] = payment_totals.get(method, 0.0) + amount
                if method == "会员余额":
                    member_balance_total += amount
                else:
                    checkout_received_total += amount

        recharge_row = conn.execute(
            """SELECT COALESCE(SUM(amount), 0) AS total
               FROM recharge_logs
               WHERE created_at >= ? AND created_at < ?""",
            (start_text, end_text),
        ).fetchone()
        recharge_total = float(recharge_row["total"] or 0)

        preferred_methods = ["现金", "微信", "支付宝", "美团", "会员余额"]
        payment_breakdown = [
            {"method": method, "amount": round(payment_totals.pop(method, 0.0), 2)}
            for method in preferred_methods
        ]
        payment_breakdown.extend(
            {"method": method, "amount": round(amount, 2)}
            for method, amount in sorted(payment_totals.items())
        )

        return {
            "code": 0,
            "data": {
                "business_date": start_at.strftime("%Y-%m-%d"),
                "start_at": start_text,
                "end_at": end_text,
                "summary": {
                    "business_total": round(business_total, 2),
                    "checkout_received_total": round(checkout_received_total, 2),
                    "recharge_total": round(recharge_total, 2),
                    "actual_income_total": round(checkout_received_total + recharge_total, 2),
                    "member_balance_total": round(member_balance_total, 2),
                    "bill_count": len(bills),
                },
                "payment_breakdown": payment_breakdown,
                "bills": bills,
            },
        }
    finally:
        conn.close()


@app.get("/api/reports/daily")
async def get_daily_business_report(date: str = "", x_records_password: str = Header(default="")):
    if not verify_records_password(x_records_password):
        raise HTTPException(403, "记录查看密码错误")
    return _build_daily_business_report(date)



def _month_business_bounds(month: str = "") -> tuple[datetime, datetime]:
    if month:
        try:
            month_start = datetime.strptime(month, "%Y-%m")
        except ValueError:
            raise HTTPException(400, "月份格式应为 YYYY-MM")
    else:
        current_business_date = datetime.now()
        if current_business_date.hour < 6:
            current_business_date -= timedelta(days=1)
        month_start = current_business_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    start_at = month_start.replace(hour=6)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    return start_at, next_month.replace(hour=6)


def _calculate_staff_commission(amount, rule: dict) -> dict:
    """Apply one monthly rule to cumulative performance, never per payment/order."""
    rule = StaffCommissionRule.model_validate(rule).model_dump()
    total = max(Decimal("0"), Decimal(str(amount))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    segments = {"first": Decimal("0"), "second": Decimal("0"), "third": Decimal("0"), "fixed": Decimal("0")}
    if rule["type"] == "marketing":
        first, second = Decimal(str(rule["first_limit"])), Decimal(str(rule["second_limit"]))
        segments["first"] = min(total, first)
        segments["second"] = min(max(total - first, Decimal("0")), second - first)
        segments["third"] = max(total - second, Decimal("0"))
    elif rule["type"] == "manager":
        segments["fixed"] = total
    result = {}
    commission = Decimal("0")
    for key, base in segments.items():
        rate = Decimal(str(rule[key + "_rate"]))
        paid = (base * rate / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        result[key + "_amount"] = float(base)
        result[key + "_commission"] = float(paid)
        commission += paid
    result["commission_total"] = float(commission)
    return result


@app.get("/api/reports/commissions")
async def get_staff_commission_report(month: str = "", staff_id: int = 0, x_records_password: str = Header(default="")):
    if not verify_records_password(x_records_password):
        raise HTTPException(403, "记录查看密码错误")
    if staff_id < 0:
        raise HTTPException(400, "人员筛选无效")
    start_at, end_at = _month_business_bounds(month)
    start_text, end_text = start_at.strftime("%Y-%m-%d %H:%M:%S"), end_at.strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        bills = [dict(row) for row in conn.execute(
            """SELECT id, room_no, open_at, close_at, total, payment_method, notes,
                      performance_staff_id, performance_staff_name, performance_commission_rule
               FROM billing_records WHERE status = 'closed'
                 AND COALESCE(NULLIF(open_at, ''), close_at) >= ?
                 AND COALESCE(NULLIF(open_at, ''), close_at) < ?
               ORDER BY close_at DESC, id DESC""", (start_text, end_text)
        ).fetchall()]
        staff = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM staff").fetchall()}
    finally:
        conn.close()

    grouped = {}
    for person in staff.values():
        rule = json.loads(person["commission_rule"] or "{}")
        if person["status"] == "在职" and rule.get("type") in {"marketing", "manager"}:
            grouped[person["id"]] = []
    unassigned_count = 0
    for bill in bills:
        owner = bill["performance_staff_id"]
        if not owner:
            unassigned_count += 1
            continue
        grouped.setdefault(owner, []).append(bill)

    options, people = [], []
    for owner, orders in grouped.items():
        person = staff.get(owner)
        name = person["name"] if person else (orders[0]["performance_staff_name"] or "历史人员")
        status = person["status"] if person else "已移除"
        options.append({"id": owner, "name": name, "status": status})
        if staff_id and owner != staff_id:
            continue
        current_rule = json.loads(person["commission_rule"] or "{}") if person else {}
        rules = []
        for bill in orders:
            snapshot = json.loads(bill["performance_commission_rule"] or "{}")
            rules.append(StaffCommissionRule.model_validate(snapshot or current_rule).model_dump())
        rule = rules[0] if rules else StaffCommissionRule.model_validate(current_rule).model_dump()
        changed = len({json.dumps(item, sort_keys=True) for item in rules}) > 1
        amount = sum((Decimal(str(bill["total"] or 0)) for bill in orders), Decimal("0"))
        people.append({
            "staff_id": owner, "name": name, "status": status, "rule": rule,
            "performance_total": float(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "bill_count": len(orders), "rule_changed": changed,
            "warning": "当月订单规则有变化，暂按最后一笔结账保存的规则计算，请核对。" if changed else "",
            "rule_source": "订单保存的规则" if rules else "人员当前规则（暂无订单）",
            **_calculate_staff_commission(amount, rule),
        })
    options.sort(key=lambda item: (item["name"], item["id"]))
    people.sort(key=lambda item: (-item["performance_total"], item["staff_id"]))
    if staff_id and not any(item["id"] == staff_id for item in options):
        raise HTTPException(400, "该月份没有此业绩归属人员")
    orders = [bill for bill in bills if bill["performance_staff_id"] and (not staff_id or bill["performance_staff_id"] == staff_id)]
    orders.sort(key=lambda bill: (bill["open_at"] or bill["close_at"] or "", bill["id"]), reverse=True)
    for bill in orders:
        person = staff.get(bill["performance_staff_id"])
        bill["staff_name"] = bill["performance_staff_name"] or (person["name"] if person else "历史人员")
        bill.pop("performance_commission_rule", None)
    return {"code": 0, "data": {
        "month": start_at.strftime("%Y-%m"), "start_at": start_text, "end_at": end_text,
        "staff_options": options, "people": people, "orders": orders,
        "unassigned_count": unassigned_count,
        "summary": {
            "performance_total": float(sum((Decimal(str(item["performance_total"])) for item in people), Decimal("0"))),
            "commission_total": float(sum((Decimal(str(item["commission_total"])) for item in people), Decimal("0"))),
            "bill_count": len(orders), "staff_count": len(people),
            "changed_rule_count": sum(item["rule_changed"] for item in people),
        },
    }}


def _actual_payment_category(method: str) -> str:
    value = (method or "").strip()
    for category in ("美团", "微信", "支付宝", "现金"):
        if category in value:
            return category
    return "其他"


@app.get("/api/reports/monthly")
async def get_monthly_business_report(month: str = "", x_records_password: str = Header(default="")):
    if not verify_records_password(x_records_password):
        raise HTTPException(403, "记录查看密码错误")
    start_at, end_at = _month_business_bounds(month)
    start_text = start_at.strftime("%Y-%m-%d %H:%M:%S")
    end_text = end_at.strftime("%Y-%m-%d %H:%M:%S")

    daily = {}
    cursor = start_at
    while cursor < end_at:
        date_text = cursor.strftime("%Y-%m-%d")
        daily[date_text] = {
            "business_date": date_text, "actual_income_total": 0.0,
            "美团": 0.0, "微信": 0.0, "支付宝": 0.0, "现金": 0.0, "其他": 0.0,
            "recharge_total": 0.0, "member_balance_total": 0.0, "bill_count": 0,
        }
        cursor += timedelta(days=1)

    summary = {
        "actual_income_total": 0.0,
        "美团": 0.0, "微信": 0.0, "支付宝": 0.0, "现金": 0.0, "其他": 0.0,
        "recharge_total": 0.0, "member_balance_total": 0.0, "bill_count": 0,
    }
    conn = get_db()
    try:
        bills = conn.execute(
            """SELECT id, total, payment_method,
                      strftime(
                          '%Y-%m-%d',
                          datetime(COALESCE(NULLIF(open_at, ''), close_at), '-6 hours')
                      ) AS business_date
               FROM billing_records
               WHERE status = 'closed'
                 AND COALESCE(NULLIF(open_at, ''), close_at) >= ?
                 AND COALESCE(NULLIF(open_at, ''), close_at) < ?""",
            (start_text, end_text),
        ).fetchall()
        bills = [dict(row) for row in bills]
        _attach_billing_payment_breakdowns(conn, bills)
        recharges = conn.execute(
            """SELECT amount, payment_method,
                      strftime('%Y-%m-%d', datetime(created_at, '-6 hours')) AS business_date
               FROM recharge_logs
               WHERE created_at >= ? AND created_at < ?""",
            (start_text, end_text),
        ).fetchall()
    finally:
        conn.close()

    for row in bills:
        date_text = row["business_date"]
        if date_text not in daily:
            continue
        daily[date_text]["bill_count"] += 1
        summary["bill_count"] += 1
        for payment in row["payment_breakdown"]:
            amount = round(float(payment["amount"] or 0), 2)
            method = (payment["method"] or "").strip()
            if method == "会员余额":
                daily[date_text]["member_balance_total"] += amount
                summary["member_balance_total"] += amount
                continue
            category = _actual_payment_category(method)
            daily[date_text][category] += amount
            daily[date_text]["actual_income_total"] += amount
            summary[category] += amount
            summary["actual_income_total"] += amount

    for row in recharges:
        date_text = row["business_date"]
        if date_text not in daily:
            continue
        amount = round(float(row["amount"] or 0), 2)
        category = _actual_payment_category(row["payment_method"])
        daily[date_text][category] += amount
        daily[date_text]["actual_income_total"] += amount
        daily[date_text]["recharge_total"] += amount
        summary[category] += amount
        summary["actual_income_total"] += amount
        summary["recharge_total"] += amount

    for values in [summary, *daily.values()]:
        for key, value in values.items():
            if key not in ("business_date", "bill_count"):
                values[key] = round(value, 2)

    return {
        "code": 0,
        "data": {
            "month": start_at.strftime("%Y-%m"),
            "start_at": start_text,
            "end_at": end_text,
            "summary": summary,
            "days": list(daily.values()),
        },
    }
# ---- Billing History Routes ----

@app.get("/api/billing/history")
async def list_billing_history(date: str = ""):
    start_at, end_at = _business_day_bounds(date)
    start_text = start_at.strftime("%Y-%m-%d %H:%M:%S")
    end_text = end_at.strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM billing_records
               WHERE status = 'closed'
                 AND COALESCE(NULLIF(open_at, ''), close_at) >= ?
                 AND COALESCE(NULLIF(open_at, ''), close_at) < ?
               ORDER BY COALESCE(NULLIF(open_at, ''), close_at) DESC, id DESC""",
            (start_text, end_text),
        ).fetchall()
        result = []
        for r in rows:
            bill = dict(r)
            drinks = conn.execute("SELECT * FROM drink_orders WHERE billing_id = ?", (r["id"],)).fetchall()
            bill["drinks"] = [dict(d) for d in drinks]
            result.append(bill)
        _attach_billing_payment_breakdowns(conn, result)
        return {
            "code": 0, "data": result,
            "business_date": start_at.strftime("%Y-%m-%d"),
            "start_at": start_text, "end_at": end_text,
        }
    finally:
        conn.close()


@app.post("/api/billing/history")
async def create_billing_history(req: BillingHistoryWriteRequest):
    if not verify_admin_password(req.admin_password):
        raise HTTPException(403, "管理密码错误")
    conn = get_db()
    try:
        performance_id, performance_name, performance_rule = _resolve_performance_staff(
            conn, req.performance_staff_id or 0, allow_inactive=True
        )
        close_at = _recharge_log_time(req.close_at)
        open_at = _recharge_log_time(req.open_at or req.close_at)
        conn.execute(
            """INSERT INTO billing_records
               (room_no, open_at, close_at, room_fee, drinks_fee, total, discount,
                payment_method, settlement_member_name, settlement_member_phone,
                notes, performance_staff_id, performance_staff_name, performance_commission_rule, status)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, 'closed')""",
            (
                req.room_no, open_at, close_at, round(req.room_fee, 2),
                round(req.drinks_fee, 2), round(req.total, 2), req.payment_method,
                (req.settlement_member_name or "").strip() or None,
                (req.settlement_member_phone or "").strip() or None,
                (req.notes or "").strip() or None,
                performance_id, performance_name, performance_rule,
            ),
        )
        billing_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.commit()
        log_operation("create_billing_history", req.room_no, f"手工新增结账记录 id={billing_id} total={req.total}")
        return {"code": 0, "msg": "ok", "id": billing_id}
    finally:
        conn.close()


@app.put("/api/billing/history/{billing_id}")
async def update_billing_history(billing_id: int, req: BillingHistoryWriteRequest):
    if not verify_admin_password(req.admin_password):
        raise HTTPException(403, "管理密码错误")
    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT * FROM billing_records WHERE id = ? AND status = 'closed'", (billing_id,)
        ).fetchone()
        if not existing:
            raise HTTPException(404, "结账记录不存在")
        if req.performance_staff_id is None or req.performance_staff_id == existing["performance_staff_id"]:
            performance_id, performance_name, performance_rule = (
                existing["performance_staff_id"], existing["performance_staff_name"], existing["performance_commission_rule"]
            )
        else:
            performance_id, performance_name, performance_rule = _resolve_performance_staff(
                conn, req.performance_staff_id, allow_inactive=True, existing=existing
            )
        open_at = _recharge_log_time(req.open_at) if req.open_at else (existing["open_at"] or _recharge_log_time(req.close_at))
        conn.execute(
            """UPDATE billing_records
               SET room_no = ?, room_fee = ?, drinks_fee = ?, total = ?, discount = 0,
                   payment_method = ?, settlement_member_name = ?,
                   settlement_member_phone = ?, notes = ?, open_at = ?, close_at = ?,
                   performance_staff_id = ?, performance_staff_name = ?, performance_commission_rule = ?
               WHERE id = ?""",
            (
                req.room_no, round(req.room_fee, 2), round(req.drinks_fee, 2),
                round(req.total, 2), req.payment_method,
                (req.settlement_member_name or "").strip() or None,
                (req.settlement_member_phone or "").strip() or None,
                (req.notes or "").strip() or None,
                open_at, _recharge_log_time(req.close_at), performance_id, performance_name, performance_rule, billing_id,
            ),
        )
        conn.execute("DELETE FROM billing_payments WHERE billing_id = ?", (billing_id,))
        conn.commit()
        log_operation("update_billing_history", req.room_no, f"修改结账记录 id={billing_id} total={req.total}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


@app.delete("/api/billing/{billing_id}")
async def delete_billing(billing_id: int, admin_password: str = ""):
    if not verify_admin_password(admin_password):
        raise HTTPException(403, "管理密码错误")
    conn = get_db()
    try:
        billing = conn.execute("SELECT * FROM billing_records WHERE id = ?", (billing_id,)).fetchone()
        if not billing:
            raise HTTPException(404, "账单不存在")
        conn.execute("DELETE FROM drink_orders WHERE billing_id = ?", (billing_id,))
        conn.execute("DELETE FROM billing_payments WHERE billing_id = ?", (billing_id,))
        conn.execute("DELETE FROM billing_records WHERE id = ?", (billing_id,))
        conn.commit()
        log_operation("delete_billing", billing["room_no"], f"删除账单 id={billing_id}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


# ---- Admin Route ----

@app.post("/api/records/verify")
async def verify_records_access(req: VerifyRecordsRequest):
    if verify_records_password(req.records_password):
        return {"code": 0, "msg": "ok"}
    raise HTTPException(403, "记录查看密码错误")


@app.post("/api/admin/verify")
async def verify_admin(req: VerifyAdminRequest):
    if verify_admin_password(req.admin_password):
        return {"code": 0, "msg": "ok"}
    raise HTTPException(403, "管理密码错误")


# ---- Operation Log Routes ----

@app.get("/api/operation-logs")
async def list_operation_logs(date: str = "", limit: int = 1000, x_records_password: str = Header(default="")):
    if not verify_records_password(x_records_password):
        raise HTTPException(403, "记录查看密码错误")
    start_at, end_at = _business_day_bounds(date)
    start_text = start_at.strftime("%Y-%m-%d %H:%M:%S")
    end_text = end_at.strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM operation_logs
               WHERE created_at >= ? AND created_at < ?
               ORDER BY created_at DESC, id DESC LIMIT ?""",
            (start_text, end_text, limit),
        ).fetchall()
        return {
            "code": 0, "data": [dict(r) for r in rows],
            "business_date": start_at.strftime("%Y-%m-%d"),
            "start_at": start_text, "end_at": end_text,
        }
    finally:
        conn.close()


# ---- Static Files ----

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))
