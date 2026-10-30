"""SQLite setup and deterministic sample-data seeding for STOCKORA."""
from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(__file__).resolve().parent / "stockora.db"
SALES_CSV = BASE_DIR / "data" / "sales.csv"

PRODUCTS = [
    ("P001", "Milk", "Dairy", "litres", 58.00),
    ("P002", "Rice", "Staples", "kg", 62.00),
    ("P003", "Bread", "Bakery", "loaves", 40.00),
    ("P004", "Biscuits", "Snacks", "packs", 20.00),
    ("P005", "Cooking Oil", "Staples", "litres", 145.00),
    ("P006", "Sugar", "Staples", "kg", 48.00),
    ("P007", "Tea", "Beverages", "packs", 180.00),
    ("P008", "Coffee", "Beverages", "packs", 220.00),
    ("P009", "Soap", "Personal Care", "bars", 35.00),
    ("P010", "Shampoo", "Personal Care", "bottles", 110.00),
    ("P011", "Toothpaste", "Personal Care", "tubes", 65.00),
    ("P012", "Eggs", "Dairy & Eggs", "dozen", 75.00),
    ("P013", "Flour", "Staples", "kg", 45.00),
    ("P014", "Noodles", "Snacks", "packs", 15.00),
    ("P015", "Soft Drinks", "Beverages", "bottles", 25.00),
]


def get_connection() -> sqlite3.Connection:
    """Open a row-aware SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db_session() -> Iterator[sqlite3.Connection]:
    """Connection scope that commits on success and always closes the handle."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create the five operational tables and seed products, sales and stock."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_session() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                product_id TEXT PRIMARY KEY,
                product_name TEXT NOT NULL,
                category TEXT NOT NULL,
                unit TEXT NOT NULL,
                price REAL NOT NULL CHECK (price >= 0)
            );

            CREATE TABLE IF NOT EXISTS sales (
                date TEXT NOT NULL,
                product_id TEXT NOT NULL,
                quantity_sold REAL NOT NULL CHECK (quantity_sold >= 0),
                PRIMARY KEY (date, product_id),
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            );
            CREATE INDEX IF NOT EXISTS idx_sales_product_date ON sales(product_id, date);

            CREATE TABLE IF NOT EXISTS inventory (
                product_id TEXT PRIMARY KEY,
                current_stock REAL NOT NULL CHECK (current_stock >= 0),
                safety_stock REAL NOT NULL CHECK (safety_stock >= 0),
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            );

            CREATE TABLE IF NOT EXISTS incoming_stock (
                product_id TEXT NOT NULL,
                supplier TEXT NOT NULL,
                quantity REAL NOT NULL CHECK (quantity >= 0),
                expected_date TEXT NOT NULL,
                status TEXT NOT NULL,
                PRIMARY KEY (product_id, supplier, expected_date),
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            );
            CREATE INDEX IF NOT EXISTS idx_incoming_product_status ON incoming_stock(product_id, status);

            CREATE TABLE IF NOT EXISTS forecasts (
                product_id TEXT NOT NULL,
                forecast_date TEXT NOT NULL,
                predicted_quantity REAL NOT NULL CHECK (predicted_quantity >= 0),
                mae REAL NOT NULL CHECK (mae >= 0),
                rmse REAL NOT NULL CHECK (rmse >= 0),
                PRIMARY KEY (product_id, forecast_date),
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            );
            CREATE INDEX IF NOT EXISTS idx_forecasts_date ON forecasts(forecast_date);
            """
        )

        conn.executemany(
            "INSERT OR IGNORE INTO products(product_id, product_name, category, unit, price) VALUES (?, ?, ?, ?, ?)",
            PRODUCTS,
        )

        inventory_rows = [
            ("P001", 128, 34), ("P002", 420, 65), ("P003", 72, 24),
            ("P004", 160, 30), ("P005", 88, 22), ("P006", 115, 28),
            ("P007", 64, 18), ("P008", 42, 16), ("P009", 95, 25),
            ("P010", 38, 14), ("P011", 56, 18), ("P012", 78, 26),
            ("P013", 210, 48), ("P014", 180, 40), ("P015", 105, 32),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO inventory(product_id, current_stock, safety_stock) VALUES (?, ?, ?)",
            inventory_rows,
        )

        incoming_rows = [
            ("P001", "FreshFields Supply", 36, "2026-11-01", "in_transit"),
            ("P002", "Harvest Wholesale", 100, "2026-11-03", "ordered"),
            ("P003", "DailyBake Distributors", 24, "2026-10-31", "in_transit"),
            ("P005", "Prime Oils Ltd", 30, "2026-11-04", "ordered"),
            ("P007", "Hilltop Tea Traders", 16, "2026-11-02", "ordered"),
            ("P010", "CarePlus Wholesale", 12, "2026-11-05", "in_transit"),
            ("P012", "Golden Nest Farms", 30, "2026-10-31", "in_transit"),
            ("P014", "QuickBite Supply", 48, "2026-11-03", "ordered"),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO incoming_stock(product_id, supplier, quantity, expected_date, status) VALUES (?, ?, ?, ?, ?)",
            incoming_rows,
        )

        existing_sales = conn.execute("SELECT COUNT(*) AS n FROM sales").fetchone()["n"]
        if existing_sales == 0 and SALES_CSV.exists():
            with SALES_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                rows = []
                for row in reader:
                    rows.append((row["Date"], row["Product ID"], float(row["Quantity Sold"])))
            conn.executemany(
                "INSERT OR REPLACE INTO sales(date, product_id, quantity_sold) VALUES (?, ?, ?)",
                rows,
            )


def database_health() -> dict:
    with db_session() as conn:
        table_counts = {}
        for table in ("products", "sales", "inventory", "incoming_stock", "forecasts"):
            table_counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return {"database": "SQLite", "file": str(DB_PATH.name), "table_counts": table_counts}
