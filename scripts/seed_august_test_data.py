"""Create realistic, removable August test data in the local KTV database."""

from __future__ import annotations

import argparse
import calendar
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from database import DB_FILE, get_db, init_db  # noqa: E402


DATA_TAG = "cs"
RANDOM_SEED = 202608
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


def _phone(index: int) -> str:
    prefix = ZHOUKOU_PREFIXES[index % len(ZHOUKOU_PREFIXES)]
    suffix = 7000 + index // len(ZHOUKOU_PREFIXES)
    return f"{prefix}{suffix:04d}"


def _distributed_amounts(rng: random.Random, total: int, count: int, minimum: int) -> list[int]:
    weights = [rng.uniform(0.55, 1.65) for _ in range(count)]
    available = total - minimum * count
    amounts = [minimum + round(available * weight / sum(weights)) for weight in weights]
    amounts[-1] += total - sum(amounts)
    return amounts


def _event_time(rng: random.Random, year: int, month: int, *, recharge: bool) -> datetime:
    days = list(range(1, calendar.monthrange(year, month)[1] + 1))
    weights = []
    for day in days:
        weekday = datetime(year, month, day).weekday()
        weights.append(2.4 if weekday in (4, 5) else 1.0)
    day = rng.choices(days, weights=weights, k=1)[0]
    if recharge:
        return datetime(year, month, day, rng.randint(11, 22), rng.choice((0, 5, 10, 15, 20, 30, 40, 50)))
    hour = rng.choices((13, 15, 17, 19, 20, 21, 22, 23), weights=(1, 1, 1, 3, 4, 5, 5, 3), k=1)[0]
    return datetime(year, month, day, hour, rng.choice((0, 10, 20, 30, 40, 50)))


def seed(year: int, month: int, billing_total: int, recharge_total: int, replace: bool) -> dict:
    rng = random.Random(RANDOM_SEED)
    conn = get_db()
    conn.execute("BEGIN IMMEDIATE")
    try:
        existing = conn.execute(
            """SELECT
                 (SELECT COUNT(*) FROM members WHERE data_tag = ?) AS members,
                 (SELECT COUNT(*) FROM recharge_logs WHERE data_tag = ?) AS recharges,
                 (SELECT COUNT(*) FROM billing_records WHERE data_tag = ?) AS bills""",
            (DATA_TAG, DATA_TAG, DATA_TAG),
        ).fetchone()
        if any(existing) and not replace:
            raise RuntimeError("已存在 data_tag=cs 的测试数据；如需重建请加 --replace")
        removed = _remove_tagged_rows(conn) if any(existing) else {}

        members = []
        for index, surname in enumerate(SURNAMES[:36]):
            phone = _phone(index)
            created_at = datetime(year, month, 1) - timedelta(days=rng.randint(3, 60))
            cursor = conn.execute(
                """INSERT INTO members
                   (name, phone, password, balance, level, remark, data_tag, created_at)
                   VALUES (?, ?, ?, 0, '会员', '八月测试会员', ?, ?)""",
                (surname, phone, phone[-4:], DATA_TAG, created_at.strftime("%Y-%m-%d %H:%M:%S")),
            )
            members.append({"id": cursor.lastrowid, "name": surname, "phone": phone, "balance": 0.0})

        recharge_amounts = _distributed_amounts(rng, recharge_total, 24, 300)
        recharge_events = []
        for index, amount in enumerate(recharge_amounts):
            recharge_events.append({
                "kind": "recharge",
                "time": _event_time(rng, year, month, recharge=True),
                "member": members[index % 24],
                "amount": amount,
                "gift": rng.choice((0, 0, 0, 50, 100)),
                "method": rng.choices(("微信", "支付宝", "现金"), weights=(6, 2, 2), k=1)[0],
            })

        bill_amounts = _distributed_amounts(rng, billing_total, 68, 168)
        bill_events = []
        methods = ["微信"] * 31 + ["会员余额"] * 20 + ["支付宝"] * 10 + ["现金"] * 7
        rng.shuffle(methods)
        for amount, method in zip(bill_amounts, methods):
            opened = _event_time(rng, year, month, recharge=False)
            duration = rng.choice((120, 180, 240, 300, 360))
            bill_events.append({
                "kind": "bill",
                "time": opened,
                "close_time": opened + timedelta(minutes=duration),
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
                       VALUES (?, ?, ?, ?, ?, ?, ?, '会员充卡', '八月测试充值', ?, ?, ?)""",
                    (
                        member["id"], member["name"], member["phone"], event["amount"],
                        event["gift"], after, event["method"], event["time"].strftime("%Y-%m-%d"),
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
                    member = rng.choice(candidates)
                    member["balance"] = round(member["balance"] - amount, 2)
                    balance_after = member["balance"]
                else:
                    method = "微信"
            elif rng.random() < 0.55:
                member = rng.choice(members)
                balance_after = member["balance"]

            opened = event["time"].strftime("%Y-%m-%d %H:%M:%S")
            closed = event["close_time"].strftime("%Y-%m-%d %H:%M:%S")
            cursor = conn.execute(
                """INSERT INTO billing_records
                   (room_no, open_at, close_at, duration_minutes, room_fee, drinks_fee,
                    total, payment_method, status, customer_type, member_id,
                    settlement_member_id, settlement_member_name, settlement_member_phone,
                    member_balance_after, notes, data_tag, created_at)
                   VALUES (?, ?, ?, ?, ?, 0, ?, ?, 'closed', ?, ?, ?, ?, ?, ?,
                           '八月测试结账', ?, ?)""",
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
            "recharge_total": recharge_total,
            "bills": inserted_bills,
            "billing_total": billing_total,
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
    parser = argparse.ArgumentParser(description="导入带 cs 标记的八月测试数据")
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--month", type=int, default=8, choices=range(1, 13))
    parser.add_argument("--billing-total", type=int, default=30_000)
    parser.add_argument("--recharge-total", type=int, default=20_000)
    parser.add_argument("--replace", action="store_true", help="只删除并重建 data_tag=cs 的数据")
    parser.add_argument("--clean", action="store_true", help="只删除 data_tag=cs 的测试数据，不再导入")
    args = parser.parse_args()

    if args.billing_total < 68 * 168:
        parser.error("结账总额过低，至少需要 11424 元")
    if args.recharge_total < 24 * 300:
        parser.error("充值总额过低，至少需要 7200 元")

    backup = _backup_database()
    _ensure_seed_schema()
    if args.clean:
        removed = clean()
        print(f"备份: {backup or '新数据库，无需备份'}")
        print(f"已清理 data_tag={DATA_TAG}: {removed}")
        return
    result = seed(args.year, args.month, args.billing_total, args.recharge_total, args.replace)
    print(f"备份: {backup or '新数据库，无需备份'}")
    print(f"测试标记: data_tag={DATA_TAG}")
    print(f"新增会员: {result['members']}")
    print(f"新增充值: {result['recharges']} 笔，实充合计 {result['recharge_total']:.2f} 元")
    print(f"新增结账: {result['bills']} 笔，合计 {result['billing_total']:.2f} 元")
    print(f"结账方式: {result['payment_counts']}")


if __name__ == "__main__":
    main()
