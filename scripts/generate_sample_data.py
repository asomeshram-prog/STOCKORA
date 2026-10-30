"""Generate STOCKORA's clearly synthetic, reproducible supermarket sales dataset."""
from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sales.csv"
END_DATE = date(2026, 10, 29)
DAYS = 112

# Baselines are fictional daily unit volumes, not retailer data.
PRODUCTS = [
    ("P001", 54, 0.13, "dairy"),
    ("P002", 42, 0.10, "staples"),
    ("P003", 48, 0.16, "bakery"),
    ("P004", 35, 0.20, "snacks"),
    ("P005", 23, 0.14, "staples"),
    ("P006", 29, 0.12, "staples"),
    ("P007", 16, 0.18, "beverages"),
    ("P008", 11, 0.17, "beverages"),
    ("P009", 20, 0.16, "personal"),
    ("P010", 9, 0.20, "personal"),
    ("P011", 14, 0.15, "personal"),
    ("P012", 31, 0.14, "dairy"),
    ("P013", 19, 0.13, "staples"),
    ("P014", 39, 0.21, "snacks"),
    ("P015", 46, 0.22, "beverages"),
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    start = END_DATE - timedelta(days=DAYS - 1)
    random.seed(82461)
    rows = []
    for product_index, (product_id, baseline, noise, category) in enumerate(PRODUCTS):
        # Fixed per-product RNG streams keep data reproducible between runs.
        rng = random.Random(82461 + product_index * 101)
        for day_index in range(DAYS):
            current = start + timedelta(days=day_index)
            weekday = current.weekday()
            weekend_factor = 1.0
            if category in ("bakery", "snacks", "beverages") and weekday >= 5:
                weekend_factor = 1.18
            elif category == "dairy" and weekday == 6:
                weekend_factor = 1.08
            elif category == "staples" and weekday == 5:
                weekend_factor = 1.10

            # Gentle category-specific drift, weekly movement and two promotion windows.
            trend = 1.0 + (0.0009 * day_index)
            weekly_cycle = 1.0 + 0.035 * math.sin((2 * math.pi * day_index / 7) + product_index / 3)
            promotion = 1.0
            if 30 <= day_index <= 35 and product_index in (1, 4, 5, 12):
                promotion = 1.23
            if 72 <= day_index <= 77 and product_index in (3, 6, 7, 13, 14):
                promotion = 1.28
            if category == "beverages" and current.month in (9, 10):
                trend *= 1.035

            expected = baseline * weekend_factor * trend * weekly_cycle * promotion
            observed = max(0, int(round(rng.gauss(expected, max(1.0, baseline * noise)))))
            rows.append((current.isoformat(), product_id, observed))

    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Date", "Product ID", "Quantity Sold"])
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic sales rows to {OUT}")
    print(f"Date range: {start.isoformat()} through {END_DATE.isoformat()}")


if __name__ == "__main__":
    main()
