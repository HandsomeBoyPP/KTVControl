"""KTV 前台控制系统 - FastAPI 后端"""

import asyncio
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import init_db, get_db, log_operation, verify_admin_password
from models import (
    AddDrinkRequest, BookingRequest, CreateInventoryRequest, CreateMemberRequest, CreateStaffRequest,
    CloseRequest, CreatePackageRequest, DeletePackageRequest, ExtendRequest, OpenRequest,
    RechargeRequest, ResetMemberPasswordRequest, SaveBillingDraftRequest, SettlementRequest,
    UpdateBillingRequest, UpdateInventoryRequest, UpdateMemberRequest, UpdatePackageRequest, UpdateStaffRequest,
    VerifyAdminRequest, VerifyMemberRequest,
)
from scheduler import (
    cancel_auto_close, execute_device_command, ktv_get, restore_all_schedules,
    schedule_auto_close, schedule_booking, start_device_command_worker,
)
from state_manager import state_mgr

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ktv")


def _get_package_price(pkg: dict) -> float:
    return float(pkg.get("price_normal", 0) or 0)


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

    if req.duration_type == "timed":
        close_at = (state_mgr.now + timedelta(minutes=duration)).isoformat()
        state_mgr.set_auto_close(req.room_name, req.room_ip, close_at)
        schedule_auto_close(req.room_ip, req.room_name, close_at)
    else:
        state_mgr.set_auto_close(req.room_name, req.room_ip, None)
    dur_str = "永久" if req.duration_type == "unlimited" else f"{duration}min"
    log_operation("open_room", req.room_name, f"开台 IP={req.room_ip} duration={dur_str} billing={billing_id}")
    return {"code": 0, "msg": "ok", "billing_id": billing_id}
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
    if req.room_name in state_mgr.auto_close_tasks:
        state_mgr.auto_close_tasks[req.room_name].cancel()
        del state_mgr.auto_close_tasks[req.room_name]
    state_mgr.set_auto_close(req.room_name, req.room_ip, None)
    conn = get_db()
    try:
        billing = conn.execute(
            "SELECT id FROM billing_records WHERE room_no = ? AND status = 'open' ORDER BY id DESC LIMIT 1",
            (req.room_name,),
        ).fetchone()
    finally:
        conn.close()
    return {"code": 0, "msg": "ok", "billing_id": billing["id"] if billing else None}


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
        rows = conn.execute("SELECT id, name, phone, balance, created_at FROM members ORDER BY id DESC").fetchall()
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
        conn.execute("INSERT INTO members (name, phone, password, level) VALUES (?, ?, ?, ?)",
                     (req.name, req.phone, pwd, "会员"))
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
    if not verify_admin_password(req.admin_password):
        raise HTTPException(403, "管理密码错误")
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
        new_balance = round(member["balance"] + req.amount, 2)
        conn.execute("UPDATE members SET balance = ? WHERE id = ?", (new_balance, member_id))
        conn.execute("INSERT INTO recharge_logs (member_id, amount, payment_method) VALUES (?, ?, ?)",
                     (member_id, req.amount, req.payment_method))
        conn.commit()
        log_operation("recharge_member", None, f"会员充值 {member['name']} +{req.amount}")
        return {"code": 0, "msg": "ok", "balance": new_balance}
    finally:
        conn.close()


# ---- Package Routes ----

@app.get("/api/packages")
async def list_packages():
    conn = get_db()
    try:
        rows = conn.execute("SELECT id, name, type, duration_minutes, price_normal, created_at FROM packages ORDER BY type, duration_minutes").fetchall()
        return {"code": 0, "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/api/packages")
async def create_package(req: CreatePackageRequest):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO packages (name, type, duration_minutes, price_normal) VALUES (?, ?, ?, ?)",
            (req.name, req.type, req.duration_minutes, req.price_normal)
        )
        conn.commit()
        pid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        log_operation("create_package", None, f"新增套餐 {req.name} type={req.type}")
        return {"code": 0, "msg": "ok", "id": pid}
    finally:
        conn.close()


@app.put("/api/packages/{package_id}")
async def update_package(package_id: int, req: UpdatePackageRequest):
    if not verify_admin_password(req.admin_password):
        raise HTTPException(403, "管理密码错误")
    conn = get_db()
    try:
        pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
        if not pkg:
            raise HTTPException(404, "套餐不存在")
        fields = []
        values = []
        for k in ["name", "type", "duration_minutes", "price_normal"]:
            v = getattr(req, k, None)
            if v is not None:
                fields.append(f"{k} = ?")
                values.append(v)
        if fields:
            values.append(package_id)
            conn.execute(f"UPDATE packages SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
        log_operation("update_package", None, f"修改套餐 id={package_id}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


@app.delete("/api/packages/{package_id}")
async def delete_package(package_id: int, req: DeletePackageRequest):
    if not verify_admin_password(req.admin_password):
        raise HTTPException(403, "管理密码错误")
    conn = get_db()
    try:
        pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
        if not pkg:
            raise HTTPException(404, "套餐不存在")
        conn.execute("DELETE FROM packages WHERE id = ?", (package_id,))
        conn.commit()
        log_operation("delete_package", None, f"删除套餐 {pkg['name']}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


# ---- Inventory Routes ----

@app.get("/api/inventory")
async def list_inventory():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM inventory ORDER BY category, name").fetchall()
        return {"code": 0, "data": [dict(r) for r in rows]}
    finally:
        conn.close()


@app.post("/api/inventory")
async def create_inventory(req: CreateInventoryRequest):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO inventory (category, name, unit_price, cost_price, stock) VALUES (?, ?, ?, ?, ?)",
            (req.category, req.name, req.unit_price, req.cost_price, req.stock)
        )
        conn.commit()
        iid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        log_operation("create_inventory", None, f"新增库存 {req.name} cat={req.category}")
        return {"code": 0, "msg": "ok", "id": iid}
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
        fields, values = [], []
        for field in ["category", "name", "unit_price", "cost_price", "stock"]:
            value = getattr(req, field, None)
            if value is not None:
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
            "SELECT id, name, phone, position, status, salary, notes, created_at FROM staff ORDER BY status, id DESC"
        ).fetchall()
        return {"code": 0, "data": [dict(row) for row in rows]}
    finally:
        conn.close()


@app.post("/api/staff")
async def create_staff(req: CreateStaffRequest):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO staff (name, phone, position, status, salary, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (req.name, req.phone, req.position, req.status, req.salary, req.notes),
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
        for field in ["name", "phone", "position", "status", "salary", "notes"]:
            if field not in req.model_fields_set:
                continue
            value = getattr(req, field)
            if value is None and field not in {"phone", "notes"}:
                continue
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
            raise HTTPException(404, "\u8d26\u5355\u4e0d\u5b58\u5728\u6216\u5df2\u7ed3\u8d26")
        package = conn.execute("SELECT * FROM packages WHERE id = ?", (req.package_id,)).fetchone()
        if not package or package["type"] != "open":
            raise HTTPException(400, "\u5f00\u53f0\u5957\u9910\u4e0d\u5b58\u5728")

        room_fee = _get_package_price(dict(package))
        drinks_fee = round(float(conn.execute(
            "SELECT COALESCE(SUM(qty * unit_price), 0) FROM drink_orders WHERE billing_id = ?",
            (billing_id,),
        ).fetchone()[0] or 0), 2)
        subtotal = round(room_fee + drinks_fee, 2)
        discount = round(req.discount, 2)
        max_discount = round(subtotal * 0.2, 2)
        if discount > max_discount:
            raise HTTPException(400, f"\u4f18\u60e0\u91d1\u989d\u4e0d\u80fd\u8d85\u8fc7\u603b\u989d\u768420% (\u6700\u591a{max_discount})")
        total = round(subtotal - discount, 2)

        conn.execute(
            """UPDATE billing_records
               SET package_id = ?, room_fee = ?, drinks_fee = ?, total = ?,
                   discount = ?, payment_method = ?
               WHERE id = ? AND status = 'open'""",
            (req.package_id, room_fee, drinks_fee, total, discount, req.payment_method, billing_id),
        )
        conn.commit()
        log_operation(
            "save_billing_draft", billing["room_no"],
            f"billing={billing_id} package={req.package_id} drinks_fee={drinks_fee} "
            f"discount={discount} total={total} payment={req.payment_method}",
        )
        return {
            "code": 0, "msg": "ok", "billing_id": billing_id,
            "package_id": req.package_id, "room_fee": room_fee,
            "drinks_fee": drinks_fee, "discount": discount,
            "total": total, "payment_method": req.payment_method,
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
        inv = conn.execute(
            "SELECT * FROM inventory WHERE name = ? AND stock >= ?", (req.item_name, req.qty)
        ).fetchone()
        if not inv:
            raise HTTPException(400, "库存不足或物品不存在")
        updated = conn.execute(
            "UPDATE inventory SET stock = stock - ? WHERE id = ? AND stock >= ?",
            (req.qty, inv["id"], req.qty),
        )
        if updated.rowcount != 1:
            raise HTTPException(409, "库存刚刚发生变化，请重试")
        price = float(inv["unit_price"] or 0)
        conn.execute(
            "INSERT INTO drink_orders (billing_id, item_name, qty, unit_price) VALUES (?, ?, ?, ?)",
            (req.billing_id, req.item_name, req.qty, price),
        )
        conn.execute(
            "UPDATE billing_records SET drinks_fee = drinks_fee + ? WHERE id = ?",
            (round(req.qty * price, 2), req.billing_id),
        )
        conn.commit()
        label = "赠送" if price == 0 else "添加"
        log_operation("add_drink", billing["room_no"], f"{label} {req.item_name} x{req.qty} @{price} billing={req.billing_id}")
        return {"code": 0, "msg": "ok"}
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
        billing = conn.execute(
            "SELECT * FROM billing_records WHERE id = ? AND status = 'open'", (drink["billing_id"],)
        ).fetchone()
        if not billing:
            raise HTTPException(400, "账单已结账，无法修改")
        amount = round(drink["qty"] * drink["unit_price"], 2)
        conn.execute(
            "UPDATE billing_records SET drinks_fee = MAX(0, drinks_fee - ?) WHERE id = ?",
            (amount, drink["billing_id"]),
        )
        conn.execute(
            "UPDATE inventory SET stock = stock + ? WHERE name = ?", (drink["qty"], drink["item_name"])
        )
        conn.execute("DELETE FROM drink_orders WHERE id = ?", (drink_id,))
        conn.commit()
        log_operation("delete_drink", billing["room_no"], f"删除明细 {drink['item_name']} x{drink['qty']}")
        return {"code": 0, "msg": "ok"}
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
        pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (req.package_id,)).fetchone()
        if not pkg or pkg["type"] != "open":
            raise HTTPException(400, "开台套餐不存在")

        room_fee = _get_package_price(dict(pkg))
        drinks_fee = float(
            conn.execute(
                "SELECT COALESCE(SUM(qty * unit_price), 0) FROM drink_orders WHERE billing_id = ?",
                (req.billing_id,),
            ).fetchone()[0] or 0
        )
        drinks_fee = round(drinks_fee, 2)
        subtotal = round(room_fee + drinks_fee, 2)
        discount = round(req.discount, 2)
        max_discount = round(subtotal * 0.2, 2)
        if discount > max_discount:
            raise HTTPException(400, f"优惠金额不能超过总额的20% (最多{max_discount})")
        total = round(subtotal - discount, 2)

        payment_method = req.payment_method
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
                   room_fee = ?, drinks_fee = ?, total = ?, discount = ?,
                   cash_supplement = 0, payment_method = ?,
                   settlement_member_id = ?, settlement_member_name = ?,
                   settlement_member_phone = ?, member_balance_after = ?,
                   status = 'closed'
               WHERE id = ?""",
            (
                req.package_id, room_fee, drinks_fee, total, discount, payment_method,
                settlement_member_id, settlement_member_name, settlement_member_phone,
                member_balance_after, req.billing_id,
            ),
        )
        conn.commit()

        room_name = billing["room_no"]
        cancel_auto_close(billing["room_ip"] or "", room_name)
        member_detail = ""
        if settlement_member_id is not None:
            member_detail = (
                f" member={settlement_member_name} phone={settlement_member_phone}"
                f" balance_before={member_balance_before:.2f}"
                f" balance_after={member_balance_after:.2f}"
            )
        log_operation(
            "settle_billing", room_name,
            f"结账 room_fee={room_fee} drinks_fee={drinks_fee} discount={discount} "
            f"total={total} payment={payment_method} room_kept_open=true{member_detail}",
        )
        return {
            "code": 0, "msg": "ok", "total": total, "room_fee": room_fee,
            "discount": discount, "cash_supplement": 0, "payment_method": payment_method,
            "room_kept_open": True,
            "settlement_member_name": settlement_member_name,
            "settlement_member_phone": settlement_member_phone,
            "member_balance_after": member_balance_after,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---- Billing History Routes ----

@app.get("/api/billing/history")
async def list_billing_history():
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM billing_records WHERE status = 'closed' ORDER BY close_at DESC LIMIT 200").fetchall()
        result = []
        for r in rows:
            bill = dict(r)
            drinks = conn.execute("SELECT * FROM drink_orders WHERE billing_id = ?", (r["id"],)).fetchall()
            bill["drinks"] = [dict(d) for d in drinks]
            result.append(bill)
        return {"code": 0, "data": result}
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
        conn.execute("DELETE FROM billing_records WHERE id = ?", (billing_id,))
        conn.commit()
        log_operation("delete_billing", billing["room_no"], f"删除账单 id={billing_id}")
        return {"code": 0, "msg": "ok"}
    finally:
        conn.close()


# ---- Admin Route ----

@app.post("/api/admin/verify")
async def verify_admin(req: VerifyAdminRequest):
    if verify_admin_password(req.admin_password):
        return {"code": 0, "msg": "ok"}
    raise HTTPException(403, "管理密码错误")


# ---- Operation Log Routes ----

@app.get("/api/operation-logs")
async def list_operation_logs(limit: int = 100):
    conn = get_db()
    try:
        rows = conn.execute("SELECT * FROM operation_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return {"code": 0, "data": [dict(r) for r in rows]}
    finally:
        conn.close()


# ---- Static Files ----

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(static_dir / "index.html"))