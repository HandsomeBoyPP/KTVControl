"""Database initialization, connection helper, operation logging, and config."""

import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger("ktv")

DATA_DIR = Path(__file__).parent / "data"
DB_FILE = DATA_DIR / "ktv.db"
CONFIG_FILE = DATA_DIR / "config.json"

# ---- Config ----
def load_config() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
    defaults = {"admin_password": "admin123"}
    save_config(defaults)
    return defaults

def save_config(cfg: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

def verify_admin_password(password: str) -> bool:
    cfg = load_config()
    return cfg.get("admin_password", "admin123") == password

# ---- Database Init & Migration ----
def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_FILE))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL UNIQUE,
            password TEXT DEFAULT '0000',
            balance REAL DEFAULT 0,
            level TEXT DEFAULT '会员',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS recharge_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT DEFAULT '现金',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE TABLE IF NOT EXISTS member_stored_drinks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            storage_kind TEXT NOT NULL DEFAULT 'sealed',
            quantity INTEGER NOT NULL DEFAULT 1,
            remaining_level TEXT,
            storage_location TEXT,
            notes TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            stored_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (member_id) REFERENCES members(id)
        );
        CREATE TABLE IF NOT EXISTS member_storage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            member_id INTEGER NOT NULL,
            storage_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            item_name TEXT NOT NULL,
            storage_kind TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            remaining_level TEXT,
            before_quantity INTEGER NOT NULL,
            after_quantity INTEGER NOT NULL,
            detail TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (member_id) REFERENCES members(id),
            FOREIGN KEY (storage_id) REFERENCES member_stored_drinks(id)
        );
        CREATE TABLE IF NOT EXISTS packages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'open',
            duration_minutes INTEGER NOT NULL,
            price_normal REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS package_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            package_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            inventory_id INTEGER,
            item_name TEXT NOT NULL,
            qty INTEGER NOT NULL DEFAULT 1,
            unit_label TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL DEFAULT '酒水',
            name TEXT NOT NULL,
            unit_name TEXT NOT NULL DEFAULT '瓶',
            unit_price REAL DEFAULT 0,
            case_size INTEGER DEFAULT 0,
            case_price REAL DEFAULT 0,
            cost_price REAL DEFAULT 0,
            stock INTEGER DEFAULT 0,
            low_stock INTEGER DEFAULT 5,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS billing_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_no TEXT NOT NULL,
            room_ip TEXT,
            package_id INTEGER,
            booking_id TEXT,
            customer_type TEXT DEFAULT 'retail',
            member_id INTEGER,
            open_at TEXT,
            close_at TEXT,
            duration_minutes INTEGER,
            room_fee REAL DEFAULT 0,
            drinks_fee REAL DEFAULT 0,
            total REAL DEFAULT 0,
            discount REAL DEFAULT 0,
            cash_supplement REAL DEFAULT 0,
            payment_method TEXT,
            notes TEXT,
            settlement_member_id INTEGER,
            settlement_member_name TEXT,
            settlement_member_phone TEXT,
            member_balance_after REAL,
            status TEXT DEFAULT 'open',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS drink_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            billing_id INTEGER NOT NULL,
            inventory_id INTEGER,
            item_name TEXT NOT NULL,
            qty INTEGER DEFAULT 1,
            unit_price REAL DEFAULT 0,
            source TEXT DEFAULT 'manual',
            package_item_id INTEGER,
            sale_unit TEXT DEFAULT 'unit',
            unit_label TEXT DEFAULT '瓶',
            unit_size INTEGER DEFAULT 1,
            stock_qty INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (billing_id) REFERENCES billing_records(id)
        );
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            room_no TEXT,
            detail TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS auto_close_schedules (
            room_name TEXT PRIMARY KEY,
            room_ip TEXT NOT NULL,
            close_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS bookings (
            id TEXT PRIMARY KEY,
            room_ip TEXT NOT NULL,
            room_name TEXT NOT NULL,
            open_at TEXT NOT NULL,
            duration_type TEXT NOT NULL DEFAULT 'timed',
            duration_minutes INTEGER,
            package_id INTEGER,
            customer_type TEXT NOT NULL DEFAULT 'retail',
            member_id INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS device_commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            action TEXT NOT NULL,
            api_path TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            room_no TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            retryable INTEGER NOT NULL DEFAULT 1,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            response_json TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS staff (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            position TEXT NOT NULL DEFAULT '员工',
            status TEXT NOT NULL DEFAULT '在职',
            salary REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_members_phone ON members(phone);
        CREATE INDEX IF NOT EXISTS idx_operation_logs_created ON operation_logs(created_at);
        CREATE INDEX IF NOT EXISTS idx_billing_records_status ON billing_records(status);
        CREATE INDEX IF NOT EXISTS idx_bookings_status_open_at ON bookings(status, open_at);
        CREATE INDEX IF NOT EXISTS idx_device_commands_status ON device_commands(status, id);
        CREATE INDEX IF NOT EXISTS idx_staff_status ON staff(status, id);
        CREATE INDEX IF NOT EXISTS idx_package_items_package ON package_items(package_id, id);
        CREATE INDEX IF NOT EXISTS idx_member_stored_drinks_member ON member_stored_drinks(member_id, status, expires_at);
        CREATE INDEX IF NOT EXISTS idx_member_storage_logs_member ON member_storage_logs(member_id, id);
    """)

    _migrate_members_password(conn)
    _migrate_unified_membership(conn)
    _migrate_billing_columns(conn)
    _migrate_device_command_columns(conn)
    _migrate_management_columns(conn)
    load_config()
    conn.commit()
    conn.close()
    logger.info(f"Database initialized: {DB_FILE}")

def _migrate_members_password(conn: sqlite3.Connection):
    cursor = conn.execute("PRAGMA table_info(members)")
    columns = {row[1] for row in cursor.fetchall()}
    if "password" not in columns:
        conn.execute("ALTER TABLE members ADD COLUMN password TEXT DEFAULT '0000'")
        rows = conn.execute("SELECT id, phone FROM members").fetchall()
        for row in rows:
            phone = row["phone"]
            pwd = phone[-4:] if len(phone) >= 4 else phone
            conn.execute("UPDATE members SET password = ? WHERE id = ?", (pwd, row["id"]))
        logger.info("Migration: added password column to members")

def _migrate_unified_membership(conn: sqlite3.Connection):
    """Keep the legacy level column compatible while treating everyone as a member."""
    conn.execute("UPDATE members SET level = '会员' WHERE level IS NULL OR level <> '会员'")

def _migrate_billing_columns(conn: sqlite3.Connection):
    cursor = conn.execute("PRAGMA table_info(billing_records)")
    columns = {row[1] for row in cursor.fetchall()}
    required_columns = [
        ("package_id", "INTEGER"),
        ("booking_id", "TEXT"),
        ("customer_type", "TEXT DEFAULT 'retail'"),
        ("member_id", "INTEGER"),
        ("discount", "REAL DEFAULT 0"),
        ("cash_supplement", "REAL DEFAULT 0"),
        ("notes", "TEXT"),
        ("settlement_member_id", "INTEGER"),
        ("settlement_member_name", "TEXT"),
        ("settlement_member_phone", "TEXT"),
        ("member_balance_after", "REAL"),
    ]
    for col_name, col_type in required_columns:
        if col_name not in columns:
            conn.execute(f"ALTER TABLE billing_records ADD COLUMN {col_name} {col_type}")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_billing_records_booking_id
                    ON billing_records(booking_id) WHERE booking_id IS NOT NULL""")
    logger.info("Migration: billing_records columns up to date")


def _migrate_management_columns(conn: sqlite3.Connection):
    inventory_columns = {row[1] for row in conn.execute("PRAGMA table_info(inventory)").fetchall()}
    inventory_required = [
        ("cost_price", "REAL DEFAULT 0"),
        ("unit_name", "TEXT DEFAULT '瓶'"),
        ("case_size", "INTEGER DEFAULT 0"),
        ("case_price", "REAL DEFAULT 0"),
        ("low_stock", "INTEGER DEFAULT 5"),
    ]
    for column_name, column_type in inventory_required:
        if column_name not in inventory_columns:
            conn.execute(f"ALTER TABLE inventory ADD COLUMN {column_name} {column_type}")
    conn.execute("UPDATE inventory SET unit_name = '瓶' WHERE unit_name IS NULL OR TRIM(unit_name) = ''")
    conn.execute("UPDATE inventory SET case_size = 0 WHERE case_size IS NULL OR case_size < 2")
    conn.execute("UPDATE inventory SET case_price = 0 WHERE case_price IS NULL")
    conn.execute("UPDATE inventory SET low_stock = 5 WHERE low_stock IS NULL OR low_stock < 0")

    drink_columns = {row[1] for row in conn.execute("PRAGMA table_info(drink_orders)").fetchall()}
    drink_required = [
        ("inventory_id", "INTEGER"),
        ("source", "TEXT DEFAULT 'manual'"),
        ("package_item_id", "INTEGER"),
        ("sale_unit", "TEXT DEFAULT 'unit'"),
        ("unit_label", "TEXT DEFAULT '瓶'"),
        ("unit_size", "INTEGER DEFAULT 1"),
        ("stock_qty", "INTEGER DEFAULT 1"),
    ]
    added_drink_columns = set()
    for column_name, column_type in drink_required:
        if column_name not in drink_columns:
            conn.execute(f"ALTER TABLE drink_orders ADD COLUMN {column_name} {column_type}")
            added_drink_columns.add(column_name)
    if "inventory_id" in added_drink_columns:
        conn.execute(
            """UPDATE drink_orders
               SET inventory_id = (
                   SELECT inventory.id FROM inventory
                   WHERE inventory.name = drink_orders.item_name
                   ORDER BY inventory.id LIMIT 1
               )
               WHERE inventory_id IS NULL"""
        )
    if "stock_qty" in added_drink_columns:
        conn.execute("UPDATE drink_orders SET stock_qty = qty")
    conn.execute("UPDATE drink_orders SET source = 'manual' WHERE source IS NULL OR source = ''")
    conn.execute("UPDATE drink_orders SET sale_unit = 'unit' WHERE sale_unit IS NULL OR sale_unit = ''")
    conn.execute("UPDATE drink_orders SET unit_label = '瓶' WHERE unit_label IS NULL OR unit_label = ''")
    conn.execute("UPDATE drink_orders SET unit_size = 1 WHERE unit_size IS NULL OR unit_size < 1")
    conn.execute("UPDATE drink_orders SET stock_qty = 0 WHERE source = 'package' AND inventory_id IS NULL")
    conn.execute("UPDATE drink_orders SET stock_qty = qty WHERE source <> 'package' AND (stock_qty IS NULL OR stock_qty < 1)")

    staff_columns = {row[1] for row in conn.execute("PRAGMA table_info(staff)").fetchall()}
    if "salary" not in staff_columns:
        conn.execute("ALTER TABLE staff ADD COLUMN salary REAL DEFAULT 0")
def _migrate_device_command_columns(conn: sqlite3.Connection):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(device_commands)").fetchall()}
    if "retryable" not in columns:
        conn.execute("ALTER TABLE device_commands ADD COLUMN retryable INTEGER NOT NULL DEFAULT 1")

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def log_operation(action: str, room_no: str | None = None, detail: str | None = None):
    try:
        conn = get_db()
        conn.execute("INSERT INTO operation_logs (action, room_no, detail) VALUES (?, ?, ?)", (action, room_no, detail))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log operation: {e}")
