"""Create realistic, removable August test data in the local KTV database."""

from __future__ import annotations

import argparse
import calendar
import random
import sqlite3
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from database import DB_FILE, get_db, init_db  # noqa: E402


DATA_TAG = "cs"
RANDOM_SEED = 202608
BILL_AMOUNTS = [88] * 3 + [188] * 2 + [380] * 4 + [480] * 18 + [580] * 30 + [600] * 3
RECHARGE_PLANS = [(1000, 500)] * 5 + [(2000, 1200)] * 3
SURNAMES = list(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹姚邵湛汪祁毛禹狄米贝明臧计伏成戴谈宋茅庞熊纪舒屈项祝董梁杜阮蓝闵席季麻强贾路娄危江童颜郭梅盛林刁钟徐邱骆高夏蔡田樊胡凌霍虞万支柯昝管卢莫经房裘缪干解应宗丁宣邓郁单杭洪包诸左石崔吉龚程嵇邢裴陆荣翁荀羊甄魏家封芮羿储靳汲邴糜松井段富巫乌焦巴弓牧隗山谷车侯宓蓬全郗班仰秋仲伊宫宁仇栾暴甘厉戎祖武符刘景詹束龙叶幸司韶郜黎蓟薄印宿白怀蒲台从鄂索咸籍赖卓蔺屠蒙池乔阴胥能苍双闻莘党翟谭贡劳逄姬申扶堵冉宰郦雍却璩桑桂濮牛寿通边扈燕冀浦尚农温别庄晏柴瞿阎充慕连茹习宦艾鱼容向古易慎戈廖庾终暨居衡步都耿满弘匡国文寇广禄阙东欧沃利蔚越夔隆师巩厍聂晁勾敖融冷訾辛阚那简饶空曾毋沙乜养鞠须丰巢关蒯相查后荆红游竺权逯盖益桓公"
)
ZHOUKOU_PREFIXES = ("1340385", "1340386", "1340387", "1340388", "1340389", "1833944", "1762981")
ROOMS = ("T01", "T02", "T03", "T06", "T07", "T08", "T11", "T12", "T16", "T17", "T18", "T19")


def _backup_database() -> Path | None:
    if not DB_FILE.exists():
        return None
    backup_dir = DB_FILE.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_file = backup_dir / f"ktv-before-cs-{datetime.now():%Y%m%d-%H%M%S}.db"
    source = sqlite3.connect(str(DB_FILE))
    target = sqlite3.connect(str(backup_file))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return backup_file


def _ensure_seed_schema() -> None:
    """Add only columns needed by this script; never rewrite existing rows."""
    if not DB_FILE.exists():
        init_db()
        return
    conn = get_db()
    try:
        required = {
            "members": (("data_tag", "TEXT"),),
            "recharge_logs": (("business_date", "TEXT"), ("data_tag", "TEXT")),
            "billing_records": (("data_tag", "TEXT"),),
        }
        existing_tables = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        missing_tables = set(required) - existing_tables
        if missing_tables:
            raise RuntimeError(f"数据库缺少必要表: {', '.join(sorted(missing_tables))}")
        for table_name, columns in required.items():
            existing_columns = {
                row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            for column_name, column_type in columns:
                if column_name not in existing_columns:
                    conn.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
                    )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_data_tag "
                f"ON {table_name}(data_tag)"
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _remove_tagged_rows(conn: sqlite3.Connection) -> dict[str, int]:
    billing_ids = [
        row[0] for row in conn.execute(
            "SELECT id FROM billing_records WHERE data_tag = ?", (DATA_TAG,)
        ).fetchall()
    ]
    counts = {
        "billing_records": len(billing_ids),
        "recharge_logs": conn.execute(
            "SELECT COUNT(*) FROM recharge_logs WHERE data_tag = ?", (DATA_TAG,)
        ).fetchone()[0],
        "members": conn.execute(
            "SELECT COUNT(*) FROM members WHERE data_tag = ?", (DATA_TAG,)
        ).fetchone()[0],
    }
    if billing_ids:
        placeholders = ",".join("?" for _ in billing_ids)
        conn.execute(f"DELETE FROM billing_payments WHERE billing_id IN ({placeholders})", billing_ids)
        conn.execute(f"DELETE FROM drink_orders WHERE billing_id IN ({placeholders})", billing_ids)
    conn.execute("DELETE FROM billing_records WHERE data_tag = ?", (DATA_TAG,))
    conn.execute("DELETE FROM recharge_logs WHERE data_tag = ?", (DATA_TAG,))
    conn.execute("DELETE FROM members WHERE data_tag = ?", (DATA_TAG,))
    return counts


def _month_bounds(year: int, month: int) -> tuple[str, str, str, str]:
    start = datetime(year, month, 1, 6)
    if month == 12:
        end = datetime(year + 1, 1, 1, 6)
    else:
        end = datetime(year, month + 1, 1, 6)
    return (
        start.strftime("%Y-%m-%d %H:%M:%S"),
        end.strftime("%Y-%m-%d %H:%M:%S"),
        f"{year:04d}-{month:02d}-01",
        end.strftime("%Y-%m-%d"),
    )


def _tagged_month_counts(conn: sqlite3.Connection, year: int, month: int) -> dict[str, int]:
    start_at, end_at, start_date, end_date = _month_bounds(year, month)
    return {
        "billing_records": conn.execute(
            """SELECT COUNT(*) FROM billing_records
               WHERE data_tag = ? AND open_at >= ? AND open_at < ?""",
            (DATA_TAG, start_at, end_at),
        ).fetchone()[0],
        "recharge_logs": conn.execute(
            """SELECT COUNT(*) FROM recharge_logs
               WHERE data_tag = ? AND business_date >= ? AND business_date < ?""",
            (DATA_TAG, start_date, end_date),
        ).fetchone()[0],
    }


def _remove_tagged_month(conn: sqlite3.Connection, year: int, month: int) -> dict[str, int]:
    """Remove one generated month and reverse only its effects on test balances."""
    start_at, end_at, start_date, end_date = _month_bounds(year, month)
    counts = _tagged_month_counts(conn, year, month)
    balance_changes: dict[int, float] = {}
    for row in conn.execute(
        """SELECT member_id, COALESCE(SUM(amount + gift_amount), 0) AS credited
           FROM recharge_logs
           WHERE data_tag = ? AND business_date >= ? AND business_date < ?
           GROUP BY member_id""",
        (DATA_TAG, start_date, end_date),
    ).fetchall():
        balance_changes[row[0]] = balance_changes.get(row[0], 0.0) - float(row[1] or 0)
    for row in conn.execute(
        """SELECT settlement_member_id, COALESCE(SUM(total), 0) AS spent
           FROM billing_records
           WHERE data_tag = ? AND payment_method = '会员余额'
             AND open_at >= ? AND open_at < ? AND settlement_member_id IS NOT NULL
           GROUP BY settlement_member_id""",
        (DATA_TAG, start_at, end_at),
    ).fetchall():
        balance_changes[row[0]] = balance_changes.get(row[0], 0.0) + float(row[1] or 0)
    for member_id, change in balance_changes.items():
        conn.execute(
            "UPDATE members SET balance = ROUND(balance + ?, 2) WHERE id = ? AND data_tag = ?",
            (change, member_id, DATA_TAG),
        )

    billing_ids = [
        row[0] for row in conn.execute(
            """SELECT id FROM billing_records
               WHERE data_tag = ? AND open_at >= ? AND open_at < ?""",
            (DATA_TAG, start_at, end_at),
        ).fetchall()
    ]
    if billing_ids:
        placeholders = ",".join("?" for _ in billing_ids)
        conn.execute(f"DELETE FROM billing_payments WHERE billing_id IN ({placeholders})", billing_ids)
        conn.execute(f"DELETE FROM drink_orders WHERE billing_id IN ({placeholders})", billing_ids)
        conn.execute(f"DELETE FROM billing_records WHERE id IN ({placeholders})", billing_ids)
    conn.execute(
        """DELETE FROM recharge_logs
           WHERE data_tag = ? AND business_date >= ? AND business_date < ?""",
        (DATA_TAG, start_date, end_date),
    )
    return counts


def _phone(index: int) -> str:
    prefix = ZHOUKOU_PREFIXES[index % len(ZHOUKOU_PREFIXES)]
    suffix = 7000 + index // len(ZHOUKOU_PREFIXES)
    return f"{prefix}{suffix:04d}"


def _business_day(rng: random.Random, year: int, month: int, *, recharge: bool = False) -> datetime:
    days = list(range(1, calendar.monthrange(year, month)[1] + 1))
    if recharge:
        days = days[: min(24, len(days))]
    weights = []
    for day in days:
        weekday = datetime(year, month, day).weekday()
        weights.append(2.4 if weekday in (4, 5) else 1.0)
    day = rng.choices(days, weights=weights, k=1)[0]
    return datetime(year, month, day)


def _night_time(rng: random.Random, business_day: datetime, *, recharge: bool = False) -> datetime:
    """Return a natural late-night time belonging to the supplied business day."""
    if recharge:
        hour = rng.choices((22, 23, 24, 25, 26), weights=(3, 4, 3, 2, 1), k=1)[0]
    else:
        hour = rng.choices((22, 23, 24, 25, 26, 27, 28), weights=(2, 4, 5, 5, 4, 3, 2), k=1)[0]
    minute = rng.randint(2, 58)
    second = rng.choice((0, 0, 0, 12, 26, 38, 47))
    return business_day + timedelta(hours=hour, minutes=minute, seconds=second)


def _billing_times(rng: random.Random, business_day: datetime) -> tuple[datetime, datetime, int]:
    """Keep both opening and checkout in the 22:00-04:59 nightlife window."""
    open_hour = rng.choices((22, 23, 24), weights=(5, 4, 1), k=1)[0]
    opened = business_day + timedelta(
        hours=open_hour,
        minutes=rng.randint(2, 52),
        seconds=rng.choice((0, 0, 12, 26, 38, 47)),
    )
    last_close = business_day + timedelta(hours=28, minutes=58)
    max_duration = min(285, int((last_close - opened).total_seconds() // 60))
    duration = rng.randint(90, max_duration)
    return opened, opened + timedelta(minutes=duration), duration


def _parse_month(value: str) -> tuple[int, int]:
    value = value.strip()
    for fmt in ("%Y-%m", "%Y/%m"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.year, parsed.month
        except ValueError:
            pass
    if value.isdigit() and 1 <= int(value) <= 12:
        return 2026, int(value)
    raise ValueError("月份格式不正确，请输入 YYYY-MM，例如 2026-08")


def _build_bill_amounts(total: int, rng: random.Random) -> list[int]:
    """Build an exact, natural-looking mix from the allowed checkout prices."""
    if total < 3000:
        raise ValueError("月结账总额不能低于3000元")
    if total % 4:
        raise ValueError("受现有金额档位限制，月结账总额必须是4的倍数")
    base_copies, remainder = divmod(total, 30_000)
    if remainder and remainder < 3000 and base_copies:
        base_copies -= 1
        remainder += 30_000
    amounts = BILL_AMOUNTS * base_copies
    if remainder == 0:
        rng.shuffle(amounts)
        return amounts

    denominations = (580, 480, 600, 380, 188, 88)
    preferred_count = max(1, round(remainder / 500))
    candidate_counts = sorted(
        range(max(1, preferred_count - 18), preferred_count + 19),
        key=lambda count: abs(count - preferred_count),
    )
    for count in candidate_counts:
        if not 88 * count <= remainder <= 600 * count:
            continue

        @lru_cache(maxsize=None)
        def solve(remaining: int, slots: int) -> tuple[int, ...] | None:
            if slots == 0:
                return () if remaining == 0 else None
            if remaining < 88 * slots or remaining > 600 * slots:
                return None
            for amount in denominations:
                result = solve(remaining - amount, slots - 1)
                if result is not None:
                    return (amount,) + result
            return None

        result = solve(remainder, count)
        if result is not None:
            amounts.extend(result)
            rng.shuffle(amounts)
            return amounts
    raise ValueError("无法使用现有金额档位组合出该总额，请换一个4的倍数金额")


def seed(year: int, month: int, billing_total: int, replace: bool) -> dict:
    rng = random.Random(RANDOM_SEED + year * 100 + month + billing_total)
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = _tagged_month_counts(conn, year, month)
        if any(existing.values()) and not replace:
            raise RuntimeError(
                f"已存在 {year:04d}-{month:02d} 的 cs 测试数据；如需重建该月请加 --replace"
            )
        removed = _remove_tagged_month(conn, year, month) if any(existing.values()) else {}

        members = [dict(row) for row in conn.execute(
            """SELECT id, name, phone, balance FROM members
               WHERE data_tag = ? ORDER BY id LIMIT 36""",
            (DATA_TAG,),
        ).fetchall()]
        for member in members:
            member["balance"] = float(member["balance"] or 0)
            member["recharged"] = False
        for index in range(len(members), 36):
            surname = SURNAMES[index]
            phone = _phone(index)
            created_at = datetime(year, month, 1) - timedelta(days=rng.randint(3, 60))
            opening_balance = 0 if index < len(RECHARGE_PLANS) else rng.choice((1000, 1500, 2000, 3000))
            cursor = conn.execute(
                """INSERT INTO members
                   (name, phone, password, balance, level, remark, data_tag, created_at)
                   VALUES (?, ?, ?, ?, '会员', NULL, ?, ?)""",
                (
                    surname, phone, phone[-4:], opening_balance, DATA_TAG,
                    created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            members.append({
                "id": cursor.lastrowid, "name": surname, "phone": phone,
                "balance": float(opening_balance), "recharged": index < len(RECHARGE_PLANS),
            })

        for index, member in enumerate(members):
            member["recharged"] = index < len(RECHARGE_PLANS)

        recharge_events = []
        for index, (amount, gift) in enumerate(RECHARGE_PLANS):
            business_day = _business_day(rng, year, month, recharge=True)
            recharge_events.append({
                "kind": "recharge",
                "time": _night_time(rng, business_day, recharge=True),
                "business_date": business_day.strftime("%Y-%m-%d"),
                "member": members[index],
                "amount": amount,
                "gift": gift,
                "method": rng.choices(("微信", "支付宝", "现金"), weights=(6, 2, 2), k=1)[0],
            })

        bill_amounts = _build_bill_amounts(billing_total, rng)
        bill_events = []
        regular_count = sum(amount not in (88, 188) for amount in bill_amounts)
        wechat_count = round(regular_count * 0.4)
        regular_methods = ["微信"] * wechat_count + ["会员余额"] * (regular_count - wechat_count)
        rng.shuffle(regular_methods)
        methods = ["美团" if amount in (88, 188) else regular_methods.pop() for amount in bill_amounts]
        for amount, method in zip(bill_amounts, methods):
            business_day = _business_day(rng, year, month)
            opened, closed, duration = _billing_times(rng, business_day)
            bill_events.append({
                "kind": "bill",
                "time": closed,
                "open_time": opened,
                "close_time": closed,
                "duration": duration,
                "amount": amount,
                "method": method,
                "room": rng.choice(ROOMS),
            })

        events = sorted(recharge_events + bill_events, key=lambda item: item["time"])
        payment_counts: dict[str, int] = {}
        inserted_recharges = 0
        inserted_bills = 0
        for event in events:
            if event["kind"] == "recharge":
                member = event["member"]
                before = round(member["balance"], 2)
                credited = round(event["amount"] + event["gift"], 2)
                after = round(before + credited, 2)
                member["balance"] = after
                occurred = event["time"].strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    """INSERT INTO recharge_logs
                       (member_id, member_name, member_phone, amount, gift_amount,
                        balance_after, payment_method, detail, notes, business_date,
                        data_tag, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, '会员充卡', NULL, ?, ?, ?)""",
                    (
                        member["id"], member["name"], member["phone"], event["amount"],
                        event["gift"], after, event["method"], event["business_date"],
                        DATA_TAG, occurred,
                    ),
                )
                inserted_recharges += 1
                continue

            method = event["method"]
            amount = float(event["amount"])
            member = None
            balance_after = None
            if method == "会员余额":
                candidates = [item for item in members if item["balance"] >= amount]
                if candidates:
                    if amount >= 580:
                        recharged = [item for item in candidates if item["recharged"]]
                        member = rng.choice(recharged or candidates)
                    else:
                        non_recharged = [item for item in candidates if not item["recharged"]]
                        member = rng.choice(non_recharged or candidates)
                    member["balance"] = round(member["balance"] - amount, 2)
                    balance_after = member["balance"]
                else:
                    method = "微信"
            elif rng.random() < 0.55:
                member = rng.choice(members)
                balance_after = member["balance"]

            opened = event["open_time"].strftime("%Y-%m-%d %H:%M:%S")
            closed = event["close_time"].strftime("%Y-%m-%d %H:%M:%S")
            cursor = conn.execute(
                """INSERT INTO billing_records
                   (room_no, open_at, close_at, duration_minutes, room_fee, drinks_fee,
                    total, payment_method, status, customer_type, member_id,
                    settlement_member_id, settlement_member_name, settlement_member_phone,
                    member_balance_after, notes, data_tag, created_at)
                   VALUES (?, ?, ?, ?, ?, 0, ?, ?, 'closed', ?, ?, ?, ?, ?, ?,
                           NULL, ?, ?)""",
                (
                    event["room"], opened, closed, event["duration"], amount, amount, method,
                    "member" if member else "retail", member["id"] if member else None,
                    member["id"] if member else None, member["name"] if member else None,
                    member["phone"] if member else None, balance_after, DATA_TAG, opened,
                ),
            )
            conn.execute(
                "INSERT INTO billing_payments (billing_id, payment_method, amount, created_at) VALUES (?, ?, ?, ?)",
                (cursor.lastrowid, method, amount, closed),
            )
            payment_counts[method] = payment_counts.get(method, 0) + 1
            inserted_bills += 1

        for member in members:
            conn.execute(
                "UPDATE members SET balance = ? WHERE id = ?",
                (round(member["balance"], 2), member["id"]),
            )

        conn.commit()
        return {
            "removed": removed,
            "members": len(members),
            "recharges": inserted_recharges,
            "recharge_total": sum(item[0] for item in RECHARGE_PLANS),
            "gift_total": sum(item[1] for item in RECHARGE_PLANS),
            "bills": inserted_bills,
            "billing_total": sum(bill_amounts),
            "payment_counts": payment_counts,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def clean() -> dict[str, int]:
    """Delete only generated rows carrying the cs tag."""
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        counts = _remove_tagged_rows(conn)
        conn.commit()
        return counts
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="按月份导入带 cs 标记的测试数据")
    parser.add_argument("--month", help="测试月份，格式 YYYY-MM；不填写时运行后交互输入")
    parser.add_argument("--total", type=int, help="该月结账总额；不填写时运行后交互输入")
    parser.add_argument("--replace", action="store_true", help="只删除并重建 data_tag=cs 的数据")
    parser.add_argument("--clean", action="store_true", help="只删除 data_tag=cs 的测试数据，不再导入")
    args = parser.parse_args()

    if args.clean:
        backup = _backup_database()
        _ensure_seed_schema()
        removed = clean()
        print(f"备份: {backup or '新数据库，无需备份'}")
        print(f"已清理 data_tag={DATA_TAG}: {removed}")
        return
    month_value = args.month or input("请输入测试月份（YYYY-MM，例如 2026-08）：")
    try:
        year, month = _parse_month(month_value)
    except ValueError as exc:
        parser.error(str(exc))
    total_value = args.total
    if total_value is None:
        entered = input("请输入该月结账总额（元，直接回车默认30000）：").strip()
        try:
            total_value = int(entered) if entered else 30_000
        except ValueError:
            parser.error("结账总额必须是整数金额")
    try:
        _build_bill_amounts(total_value, random.Random(0))
    except ValueError as exc:
        parser.error(str(exc))
    backup = _backup_database()
    _ensure_seed_schema()
    result = seed(year, month, total_value, args.replace)
    print(f"备份: {backup or '新数据库，无需备份'}")
    print(f"测试标记: data_tag={DATA_TAG}")
    print(f"测试月份: {year:04d}-{month:02d}")
    print(f"新增会员: {result['members']}")
    print(
        f"新增充值: {result['recharges']} 笔，实充 {result['recharge_total']:.2f} 元，"
        f"赠送 {result['gift_total']:.2f} 元"
    )
    print(f"新增结账: {result['bills']} 笔，合计 {result['billing_total']:.2f} 元")
    print(f"结账方式: {result['payment_counts']}")


if __name__ == "__main__":
    main()
