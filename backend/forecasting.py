"""Statsmodels-based daily demand forecasting for STOCKORA."""
from __future__ import annotations

import math
import sqlite3
import warnings
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

MIN_HISTORY_DAYS = 28
FORECAST_HORIZON_DAYS = 7


def classify_reliability(mae: float, historical_average: float) -> tuple[str, float, str]:
    """Classify forecast reliability using MAE relative to average daily demand.

    Reliable: normalized MAE <= 15%; Moderate: <= 30%; otherwise Low Reliability.
    The normalized error and thresholds are exposed to the UI for transparency.
    """
    scale = max(float(historical_average), 1.0)
    normalized_error = float(mae) / scale
    if normalized_error <= 0.15:
        return (
            "Reliable",
            normalized_error,
            f"MAE is {normalized_error:.1%} of average daily demand (at or below the 15% Reliable threshold).",
        )
    if normalized_error <= 0.30:
        return (
            "Moderate",
            normalized_error,
            f"MAE is {normalized_error:.1%} of average daily demand (above 15% and at or below the 30% Moderate threshold).",
        )
    return (
        "Low Reliability",
        normalized_error,
        f"MAE is {normalized_error:.1%} of average daily demand (above the 30% threshold). Review the demand history before relying on this forecast.",
    )


def _fit_ets(values: np.ndarray, steps: int) -> np.ndarray:
    """Fit a weekly seasonal Holt-Winters model and forecast ``steps`` days."""
    values = np.asarray(values, dtype=float)
    if values.size < 14:
        raise ValueError("At least 14 training observations are required for the time-series model.")

    # A weekly seasonal component is enabled when there are at least three weeks
    # of training history. The fallback still uses Statsmodels, without seasonality.
    use_seasonal = values.size >= 21
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = ExponentialSmoothing(
            values,
            trend="add",
            damped_trend=True,
            seasonal="add" if use_seasonal else None,
            seasonal_periods=7 if use_seasonal else None,
            initialization_method="estimated",
        )
        fitted = model.fit(optimized=True, use_brute=False)
        predictions = np.asarray(fitted.forecast(steps), dtype=float)

    if predictions.size != steps or not np.all(np.isfinite(predictions)):
        raise ValueError("The forecasting model returned invalid predictions.")
    return np.maximum(predictions, 0.0)


def build_forecast(conn: sqlite3.Connection, product_id: str) -> dict[str, Any]:
    """Train, evaluate and persist a seven-day forecast for one product."""
    product = conn.execute(
        "SELECT product_id, product_name, unit FROM products WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    if product is None:
        raise KeyError(f"Product '{product_id}' was not found.")

    rows = conn.execute(
        "SELECT date, quantity_sold FROM sales WHERE product_id = ? ORDER BY date ASC",
        (product_id,),
    ).fetchall()
    if len(rows) < MIN_HISTORY_DAYS:
        raise ValueError(
            f"Insufficient historical data for {product['product_name']}. "
            f"At least {MIN_HISTORY_DAYS} daily observations are required; found {len(rows)}."
        )

    frame = pd.DataFrame([dict(row) for row in rows])
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["quantity_sold"] = pd.to_numeric(frame["quantity_sold"], errors="coerce")
    frame = frame.dropna(subset=["date", "quantity_sold"])
    if frame.empty:
        raise ValueError("No valid sales history is available for this product.")
    daily = (
        frame.groupby("date", as_index=True)["quantity_sold"]
        .sum()
        .sort_index()
        .asfreq("D", fill_value=0.0)
    )
    values = daily.to_numpy(dtype=float)
    if len(values) < MIN_HISTORY_DAYS:
        raise ValueError(
            f"Insufficient daily history after cleaning. At least {MIN_HISTORY_DAYS} days are required; found {len(values)}."
        )

    # Chronological holdout: the final 20% (at least seven days) is never used
    # during fitting for the evaluation metrics.
    test_size = min(max(7, int(math.ceil(len(values) * 0.20))), len(values) - 21)
    train_values = values[:-test_size]
    actual_test = values[-test_size:]
    test_predictions = _fit_ets(train_values, test_size)
    errors = actual_test - test_predictions
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(np.square(errors))))

    # Refit on all available history for the production seven-day forecast.
    forecast_values = _fit_ets(values, FORECAST_HORIZON_DAYS)
    historical_average = float(np.mean(values))
    reliability, normalized_error, reliability_reason = classify_reliability(mae, historical_average)

    last_date = daily.index[-1].date()
    forecast_rows = []
    for offset, value in enumerate(forecast_values, start=1):
        forecast_date = last_date + timedelta(days=offset)
        forecast_rows.append(
            {
                "date": forecast_date.isoformat(),
                "predicted_quantity": round(float(value), 2),
            }
        )

    conn.execute("DELETE FROM forecasts WHERE product_id = ?", (product_id,))
    conn.executemany(
        """
        INSERT INTO forecasts(product_id, forecast_date, predicted_quantity, mae, rmse)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (product_id, item["date"], item["predicted_quantity"], mae, rmse)
            for item in forecast_rows
        ],
    )

    history = [
        {"date": index.date().isoformat(), "quantity_sold": round(float(value), 2)}
        for index, value in daily.items()
    ]
    return {
        "product_id": product_id,
        "product_name": product["product_name"],
        "unit": product["unit"],
        "model": "Statsmodels Holt-Winters Exponential Smoothing",
        "forecast_horizon_days": FORECAST_HORIZON_DAYS,
        "history": history,
        "forecast": forecast_rows,
        "historical_average": round(historical_average, 2),
        "historical_total": round(float(np.sum(values)), 2),
        "forecast_total": round(float(sum(item["predicted_quantity"] for item in forecast_rows)), 2),
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "normalized_mae": round(normalized_error, 4),
        "reliability": reliability,
        "reliability_reason": reliability_reason,
        "evaluation_days": int(test_size),
        "training_days": int(len(train_values)),
        "history_days": int(len(values)),
    }


def read_saved_forecast(conn: sqlite3.Connection, product_id: str) -> dict[str, Any] | None:
    """Return the latest persisted forecast joined to its actual sales history."""
    product = conn.execute(
        "SELECT product_id, product_name, unit FROM products WHERE product_id = ?",
        (product_id,),
    ).fetchone()
    if product is None:
        raise KeyError(f"Product '{product_id}' was not found.")

    forecast_rows = conn.execute(
        """
        SELECT forecast_date, predicted_quantity, mae, rmse
        FROM forecasts WHERE product_id = ? ORDER BY forecast_date ASC
        """,
        (product_id,),
    ).fetchall()
    if not forecast_rows:
        return None

    history_rows = conn.execute(
        "SELECT date, quantity_sold FROM sales WHERE product_id = ? ORDER BY date ASC",
        (product_id,),
    ).fetchall()
    if not history_rows:
        return None

    frame = pd.DataFrame([dict(row) for row in history_rows])
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    daily = (
        frame.dropna(subset=["date"])
        .groupby("date")["quantity_sold"]
        .sum()
        .sort_index()
        .asfreq("D", fill_value=0.0)
    )
    history = [
        {"date": index.date().isoformat(), "quantity_sold": round(float(value), 2)}
        for index, value in daily.items()
    ]
    forecast = [
        {"date": row["forecast_date"], "predicted_quantity": round(float(row["predicted_quantity"]), 2)}
        for row in forecast_rows
    ]
    mae = float(forecast_rows[0]["mae"])
    rmse = float(forecast_rows[0]["rmse"])
    average = float(daily.mean()) if len(daily) else 0.0
    reliability, normalized_error, reliability_reason = classify_reliability(mae, average)
    return {
        "product_id": product_id,
        "product_name": product["product_name"],
        "unit": product["unit"],
        "model": "Statsmodels Holt-Winters Exponential Smoothing",
        "forecast_horizon_days": FORECAST_HORIZON_DAYS,
        "history": history,
        "forecast": forecast,
        "historical_average": round(average, 2),
        "historical_total": round(float(daily.sum()), 2),
        "forecast_total": round(float(sum(item["predicted_quantity"] for item in forecast)), 2),
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "normalized_mae": round(normalized_error, 4),
        "reliability": reliability,
        "reliability_reason": reliability_reason,
        "evaluation_days": None,
        "training_days": None,
        "history_days": int(len(daily)),
    }
