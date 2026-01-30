
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import datetime as dt

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "app.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()

        cur.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'demo', -- admin / demo
            created_at TEXT NOT NULL,
            demo_expires_at TEXT, -- ISO date
            last_login_at TEXT
        );

        CREATE TABLE IF NOT EXISTS units(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS materials(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            unit_id INTEGER NOT NULL,
            stock_qty REAL NOT NULL DEFAULT 0,
            min_stock REAL NOT NULL DEFAULT 0,
            FOREIGN KEY(unit_id) REFERENCES units(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS dishes(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS recipe_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dish_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            qty_per_person REAL NOT NULL,
            FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE CASCADE,
            FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE RESTRICT,
            UNIQUE(dish_id, material_id)
        );

        CREATE TABLE IF NOT EXISTS menus(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_date TEXT NOT NULL, -- YYYY-MM-DD
            meal_type TEXT NOT NULL, -- breakfast/lunch/dinner/snack
            dish_id INTEGER NOT NULL,
            FOREIGN KEY(dish_id) REFERENCES dishes(id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_menus_date ON menus(menu_date);
        CREATE INDEX IF NOT EXISTS idx_menus_date_meal ON menus(menu_date, meal_type);

        CREATE TABLE IF NOT EXISTS invoices(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT NOT NULL UNIQUE,
            invoice_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS invoice_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            qty REAL NOT NULL,
            total_amount REAL NOT NULL,
            unit_price REAL NOT NULL, -- stored
            FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE,
            FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_invoice_items_material ON invoice_items(material_id);

        CREATE TABLE IF NOT EXISTS stock_moves(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            move_date TEXT NOT NULL, -- YYYY-MM-DD
            material_id INTEGER NOT NULL,
            direction TEXT NOT NULL, -- in/out
            qty REAL NOT NULL,
            ref_type TEXT,
            ref_id TEXT,
            note TEXT,
            FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE RESTRICT
        );

        CREATE INDEX IF NOT EXISTS idx_stock_moves_date ON stock_moves(move_date);

        CREATE TABLE IF NOT EXISTS orders(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_monday TEXT NOT NULL, -- YYYY-MM-DD
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS order_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            needed_qty REAL NOT NULL,
            current_qty REAL NOT NULL,
            order_qty REAL NOT NULL,
            FOREIGN KEY(order_id) REFERENCES orders(id) ON DELETE CASCADE,
            FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE RESTRICT
        );
        """)
        conn.commit()

        # --- lightweight migrations ---
        cur.execute("PRAGMA table_info(users)")
        cols = {r[1] for r in cur.fetchall()}
        if "is_active" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
            conn.commit()


def ensure_seed_admin(username: str = "admin", password_hash: str = ""):
    # called by auth on first run
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username=?", (username,))
        if cur.fetchone():
            return
        now = dt.datetime.utcnow().isoformat()
        cur.execute("""
            INSERT INTO users(first_name,last_name,email,username,password_hash,role,created_at,demo_expires_at,last_login_at)
            VALUES(?,?,?,?,?,'admin',?,NULL,NULL)
        """, ("Admin","User","admin@example.com",username,password_hash,now))
        conn.commit()
