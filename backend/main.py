"""STOCKORA FastAPI application.

Run from the backend folder with: uvicorn main:app --reload
"""
from __future__ import annotations

import io
import logging
import math
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

try:  # Supports both `uvicorn main:app` and `uvicorn backend.main:app`.
    from .database import BASE_DIR, DB_PATH, SALES_CSV, PRODUCTS, database_health, get_connection, init_db
    from .forecasting import build_forecast, read_saved_forecast
    from .inventory import get_inventory_summary
except ImportError:  # pragma: no cover - used when launched from backend/ directly
    from database import BASE_DIR, DB_PATH, SALES_CSV, PRODUCTS, database_health, get_connection, init_db
    from forecasting import build_forecast, read_saved_forecast
    from inventory import get_inventory_summary

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stockora")
FRONTEND_DIR = BASE_DIR / "frontend"


@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class InventoryUpdate(BaseModel):
    current_stock: float = Field(ge=0, allow_inf_nan=False)
    safety_stock: float = Field(ge=0, allow_inf_nan=False)


app = FastAPI(
    title="STOCKORA API",
    description="Adaptive demand forecasting and intelligent inventory planning.",
    version="1.0.0",
)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.exception_handler(Exception)
async def unexpected_error_handler(request, exc: Exception):
    """Return a safe API error instead of exposing server internals or tracebacks."""
    logger.exception("Unhandled application error at %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong while processing the request. Please try again."},
    )


PAGE_FILES = {
    "dashboard": "dashboard.html",
    "forecast": "forecast.html",
    "inventory": "inventory.html",
    "upload": "upload.html",
    "alerts": "alerts.html",
    "analytics": "analytics.html",
    "product": "product.html",
    "settings": "settings.html",
}


def _ensure_forecast(conn, product_id: str) -> dict[str, Any]:
    saved = read_saved_forecast(conn, product_id)
    if saved is not None:
        return saved
    return build_forecast(conn, product_id)


def _all_inventory_summaries(conn) -> list[dict[str, Any]]:
    products = conn.execute(
        "SELECT product_id, product_name FROM products ORDER BY product_name"
    ).fetchall()
    summaries = []
    for product in products:
        try:
            forecast = _ensure_forecast(conn, product["product_id"])
            summaries.append(
                get_inventory_summary(conn, product["product_id"], forecast["forecast_total"], forecast["reliability"])
                | {
                    "mae": forecast["mae"],
                    "rmse": forecast["rmse"],
                    "reliability": forecast["reliability"],
                }
            )
        except ValueError as exc:
            # A product with insufficient history is intentionally omitted from
            # reorder/alert calculations rather than treated as zero-demand.
            logger.warning("Inventory recommendation skipped for %s: %s", product["product_id"], exc)
    return summaries


def _page(name: str) -> FileResponse:
    file_name = PAGE_FILES.get(name)
    if not file_name:
        raise HTTPException(status_code=404, detail="Page not found")
    page_path = FRONTEND_DIR / file_name
    if not page_path.exists():
        raise HTTPException(status_code=404, detail="Page file is missing")
    return FileResponse(page_path)


@app.on_event("startup")
def startup_event() -> None:
    """Initialize SQLite, seed synthetic sample data and generate first forecasts."""
    init_db()
    with db_session() as conn:
        generated = 0
        for row in conn.execute("SELECT product_id FROM products").fetchall():
            try:
                build_forecast(conn, row["product_id"])
                generated += 1
            except Exception as exc:  # Keep service available if a product has insufficient data.
                logger.warning("Initial forecast skipped for %s: %s", row["product_id"], exc)
        logger.info("STOCKORA initialized; generated forecasts for %s products", generated)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard")


@app.get("/index", include_in_schema=False)
def index():
    return RedirectResponse(url="/dashboard")


@app.get("/sample-data.csv", include_in_schema=False)
def sample_data_file():
    if not SALES_CSV.exists():
        raise HTTPException(status_code=404, detail="Sample data file is not available")
    return FileResponse(SALES_CSV, filename="sales.csv", media_type="text/csv")


@app.get("/dashboard", include_in_schema=False)
def dashboard_page():
    return _page("dashboard")


@app.get("/forecast", include_in_schema=False)
def forecast_page():
    return _page("forecast")


@app.get("/inventory", include_in_schema=False)
def inventory_page():
    return _page("inventory")


@app.get("/upload", include_in_schema=False)
def upload_page():
    return _page("upload")


@app.get("/alerts", include_in_schema=False)
def alerts_page():
    return _page("alerts")


@app.get("/analytics", include_in_schema=False)
def analytics_page():
    return _page("analytics")


@app.get("/product", include_in_schema=False)
def product_page():
    return _page("product")


@app.get("/settings", include_in_schema=False)
def settings_page():
    return _page("settings")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "STOCKORA", "database": database_health()}


@app.get("/api/products")
def list_products():
    with db_session() as conn:
        rows = conn.execute(
            "SELECT product_id, product_name, category, unit, price FROM products ORDER BY product_name"
        ).fetchall()
        return {"products": [dict(row) for row in rows], "count": len(rows)}


@app.get("/api/dashboard")
def dashboard_data():
    with db_session() as conn:
        product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        forecasted_count = conn.execute(
            "SELECT COUNT(DISTINCT product_id) FROM forecasts"
        ).fetchone()[0]
        inventory_rows = _all_inventory_summaries(conn)
        reorder_rows = [row for row in inventory_rows if row["reorder_quantity"] > 0]
        at_risk_rows = [row for row in inventory_rows if row["risk"] in ("high", "medium")]

        performances = []
        for row in conn.execute(
            """
            SELECT f.product_id, MAX(f.mae) AS mae, AVG(s.quantity_sold) AS avg_demand
            FROM forecasts f JOIN sales s ON s.product_id = f.product_id
            GROUP BY f.product_id
            """
        ).fetchall():
            avg = float(row["avg_demand"] or 0)
            mae = float(row["mae"] or 0)
            performances.append(max(0.0, min(100.0, (1.0 - mae / max(avg, 1.0)) * 100.0)))
        overall_performance = round(float(np.mean(performances)), 1) if performances else None

        return {
            "total_products": product_count,
            "forecasted_products": forecasted_count,
            "products_at_risk": len(at_risk_rows),
            "reorder_required": len(reorder_rows),
            "overall_forecast_performance": overall_performance,
            "performance_definition": "Average of max(0, 1 − MAE / average daily demand) across forecasted products.",
            "inventory_preview": sorted(
                inventory_rows,
                key=lambda item: (0 if item["risk"] == "high" else 1 if item["risk"] == "medium" else 2, -item["reorder_quantity"]),
            )[:6],
            "risk_counts": {
                "high": sum(1 for row in inventory_rows if row["risk"] == "high"),
                "medium": sum(1 for row in inventory_rows if row["risk"] == "medium"),
                "normal": sum(1 for row in inventory_rows if row["risk"] == "normal"),
            },
        }


@app.get("/api/sales/{product_id}")
def sales_history(product_id: str):
    with db_session() as conn:
        product = conn.execute(
            "SELECT product_id, product_name, unit FROM products WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        rows = conn.execute(
            "SELECT date, quantity_sold FROM sales WHERE product_id = ? ORDER BY date ASC",
            (product_id,),
        ).fetchall()
        return {"product": dict(product), "sales": [dict(row) for row in rows], "count": len(rows)}


@app.get("/api/forecast/{product_id}")
def get_forecast(product_id: str):
    with db_session() as conn:
        try:
            data = _ensure_forecast(conn, product_id)
            inventory = get_inventory_summary(conn, product_id, data["forecast_total"], data["reliability"])
            data["inventory"] = inventory
            return data
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Forecast retrieval failed for %s", product_id)
            raise HTTPException(status_code=500, detail="Could not retrieve the forecast. Please try again.") from exc


@app.post("/api/forecast/{product_id}")
def generate_forecast(product_id: str):
    with db_session() as conn:
        try:
            data = build_forecast(conn, product_id)
            data["inventory"] = get_inventory_summary(conn, product_id, data["forecast_total"], data["reliability"])
            return data
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            logger.exception("Forecast generation failed for %s", product_id)
            raise HTTPException(status_code=500, detail="Forecast generation failed. Check the sales history and try again.") from exc


@app.get("/api/inventory")
def list_inventory():
    with db_session() as conn:
        try:
            items = _all_inventory_summaries(conn)
            return {"inventory": items, "count": len(items)}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/inventory/{product_id}")
def get_inventory(product_id: str):
    with db_session() as conn:
        try:
            forecast = _ensure_forecast(conn, product_id)
            return get_inventory_summary(conn, product_id, forecast["forecast_total"], forecast["reliability"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc).strip("'")) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/inventory/{product_id}")
def update_inventory(product_id: str, payload: InventoryUpdate):
    with db_session() as conn:
        exists = conn.execute("SELECT 1 FROM inventory WHERE product_id = ?", (product_id,)).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Inventory record not found for this product")
        conn.execute(
            "UPDATE inventory SET current_stock = ?, safety_stock = ? WHERE product_id = ?",
            (payload.current_stock, payload.safety_stock, product_id),
        )
        forecast = _ensure_forecast(conn, product_id)
        return get_inventory_summary(conn, product_id, forecast["forecast_total"], forecast["reliability"])


@app.get("/api/alerts")
def alerts():
    with db_session() as conn:
        items = _all_inventory_summaries(conn)
        ordered = sorted(
            items,
            key=lambda item: (0 if item["risk"] == "high" else 1 if item["risk"] == "medium" else 2, -item["reorder_quantity"]),
        )
        return {
            "alerts": [
                {
                    **item,
                    "title": "High risk — likely stock shortage" if item["risk"] == "high" else "Medium risk — stock may be insufficient" if item["risk"] == "medium" else "Normal — stock cover is sufficient",
                    "message": item["why"],
                }
                for item in ordered
            ],
            "count": len(ordered),
            "high": sum(1 for item in ordered if item["risk"] == "high"),
            "medium": sum(1 for item in ordered if item["risk"] == "medium"),
            "normal": sum(1 for item in ordered if item["risk"] == "normal"),
        }


@app.get("/api/analytics")
def analytics():
    with db_session() as conn:
        items = _all_inventory_summaries(conn)
        product_metrics = []
        for item in items:
            history = conn.execute(
                "SELECT AVG(quantity_sold) AS average, SUM(quantity_sold) AS total FROM sales WHERE product_id = ?",
                (item["product_id"],),
            ).fetchone()
            product_metrics.append(
                {
                    **item,
                    "historical_average": round(float(history["average"] or 0), 2),
                    "historical_total": round(float(history["total"] or 0), 2),
                    "forecast_accuracy": round(max(0.0, min(100.0, (1.0 - item["mae"] / max(float(history["average"] or 0), 1.0)) * 100.0)), 1),
                }
            )
        highest = sorted(product_metrics, key=lambda item: item["historical_average"], reverse=True)
        lowest = list(reversed(highest))
        return {
            "products": product_metrics,
            "highest_demand": highest[:5],
            "lowest_demand": lowest[:5],
            "reorder_required": [item for item in product_metrics if item["reorder_quantity"] > 0],
            "forecast_performance": sorted(product_metrics, key=lambda item: item["forecast_accuracy"], reverse=True),
        }


@app.get("/api/product/{product_id}")
def product_detail(product_id: str):
    with db_session() as conn:
        product = conn.execute(
            "SELECT product_id, product_name, category, unit, price FROM products WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        try:
            forecast = _ensure_forecast(conn, product_id)
            inventory = get_inventory_summary(conn, product_id, forecast["forecast_total"], forecast["reliability"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"product": dict(product), "forecast": forecast, "inventory": inventory}


def _normalize_column_name(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


@app.post("/api/upload")
async def upload_sales(file: UploadFile = File(...)):
    """Validate a CSV/XLSX upload, upsert daily sales and refresh model outputs."""
    filename = (file.filename or "").lower()
    if not filename.endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Upload a CSV or Excel file (.csv, .xlsx, .xls).")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(raw) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="The upload exceeds the 15 MB limit.")

    try:
        if filename.endswith(".csv"):
            frame = pd.read_csv(io.BytesIO(raw))
        else:
            frame = pd.read_excel(io.BytesIO(raw))
    except (pd.errors.EmptyDataError, ValueError, ImportError) as exc:
        raise HTTPException(status_code=400, detail="Could not read the file. Check that it is a valid CSV or Excel workbook.") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail="The file could not be parsed. Check its format and try again.") from exc

    if frame.empty:
        raise HTTPException(status_code=400, detail="The uploaded file contains no data rows.")

    normalized_to_original = {_normalize_column_name(column): column for column in frame.columns}
    required_keys = {"date": "date", "productid": "product_id", "quantitysold": "quantity_sold"}
    missing_columns = [label for key, label in required_keys.items() if key not in normalized_to_original]
    if missing_columns:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Required columns are missing.",
                "missing_columns": missing_columns,
                "expected_columns": ["Date", "Product ID", "Quantity Sold"],
            },
        )

    data = pd.DataFrame(
        {
            "date_raw": frame[normalized_to_original["date"]],
            "product_id_raw": frame[normalized_to_original["productid"]],
            "quantity_raw": frame[normalized_to_original["quantitysold"]],
        }
    )
    total_rows = len(data)
    missing_values = int(data.isna().sum().sum())
    duplicate_rows = int(data.duplicated(keep="first").sum())
    data = data.drop_duplicates(keep="first").copy()
    parsed_dates = pd.to_datetime(data["date_raw"], errors="coerce")
    quantities = pd.to_numeric(data["quantity_raw"], errors="coerce")
    product_ids = data["product_id_raw"].astype("string").str.strip()

    invalid_dates = parsed_dates.isna()
    invalid_quantities = quantities.isna() | ~np.isfinite(quantities.fillna(0)) | (quantities < 0)
    invalid_products = product_ids.isna() | (product_ids == "")
    valid_mask = ~(invalid_dates | invalid_quantities | invalid_products)

    validation = {
        "records": total_rows,
        "products": int(product_ids[valid_mask].nunique()),
        "date_range": None,
        "missing_values": missing_values,
        "duplicate_rows": duplicate_rows,
        "invalid_dates": int(invalid_dates.sum()),
        "invalid_quantities": int(invalid_quantities.sum()),
        "invalid_product_ids": int(invalid_products.sum()),
    }
    if valid_mask.any():
        validation["date_range"] = {
            "from": parsed_dates[valid_mask].min().date().isoformat(),
            "to": parsed_dates[valid_mask].max().date().isoformat(),
        }

    valid_data = pd.DataFrame(
        {
            "date": parsed_dates[valid_mask].dt.strftime("%Y-%m-%d"),
            "product_id": product_ids[valid_mask].astype(str),
            "quantity_sold": quantities[valid_mask].astype(float),
        }
    )

    with db_session() as conn:
        known = {row[0] for row in conn.execute("SELECT product_id FROM products").fetchall()}
        unknown_ids = sorted(set(valid_data["product_id"]) - known)
        validation["unknown_product_ids"] = unknown_ids
        invalid_count = int((~valid_mask).sum())
        if invalid_count or unknown_ids:
            detail = {
                "message": "The file did not pass validation. No rows were imported.",
                "validation": validation,
                "unknown_product_ids": unknown_ids,
            }
            raise HTTPException(status_code=422, detail=detail)

        grouped = (
            valid_data.groupby(["date", "product_id"], as_index=False)["quantity_sold"]
            .sum()
        )
        conn.executemany(
            """
            INSERT INTO sales(date, product_id, quantity_sold) VALUES (?, ?, ?)
            ON CONFLICT(date, product_id) DO UPDATE SET quantity_sold = excluded.quantity_sold
            """,
            [tuple(row) for row in grouped[["date", "product_id", "quantity_sold"]].itertuples(index=False, name=None)],
        )
        # Sales changed: discard stale metrics and regenerate all products from current DB history.
        conn.execute("DELETE FROM forecasts")
        refreshed = 0
        skipped = []
        for row in conn.execute("SELECT product_id FROM products").fetchall():
            try:
                build_forecast(conn, row["product_id"])
                refreshed += 1
            except Exception as exc:
                skipped.append({"product_id": row["product_id"], "reason": str(exc)})

    return {
        "message": "Sales data validated and imported successfully.",
        "imported_daily_records": int(len(grouped)),
        "forecasted_products": refreshed,
        "skipped_forecasts": skipped,
        "validation": validation,
    }


@app.get("/api/settings")
def settings():
    with db_session() as conn:
        health_data = database_health()
        product_count = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        sales_count = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    return {
        "app_name": "STOCKORA",
        "version": "1.0.0",
        "database": health_data,
        "product_count": product_count,
        "sales_records": sales_count,
        "forecast_model": "Statsmodels Holt-Winters Exponential Smoothing with weekly seasonality when history permits.",
        "forecast_horizon_days": 7,
        "minimum_history_days": 28,
        "reliability_thresholds": {
            "reliable": "normalized MAE <= 15%",
            "moderate": "normalized MAE > 15% and <= 30%",
            "low": "normalized MAE > 30%",
        },
        "synthetic_data_notice": "The included sample sales are deterministic synthetic data created for demonstration; they are not real retailer records.",
        "api_docs": "/docs",
    }
