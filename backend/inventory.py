"""Inventory calculations and plain-language reorder explanations."""
from __future__ import annotations

import sqlite3
from typing import Any

OUTSTANDING_STATUSES = ("pending", "ordered", "in_transit")


def calculate_reorder_quantity(
    forecast_demand: float,
    safety_stock: float,
    current_stock: float,
    incoming_stock: float,
) -> float:
    """Apply the exact STOCKORA reorder formula."""
    return max(0.0, forecast_demand + safety_stock - current_stock - incoming_stock)


def get_inventory_summary(conn: sqlite3.Connection, product_id: str, forecast_demand: float, forecast_reliability: str | None = None) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT p.product_id, p.product_name, p.category, p.unit,
               i.current_stock, i.safety_stock
        FROM products p
        JOIN inventory i ON i.product_id = p.product_id
        WHERE p.product_id = ?
        """,
        (product_id,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Product '{product_id}' was not found in inventory.")

    incoming = conn.execute(
        """
        SELECT COALESCE(SUM(quantity), 0) AS total
        FROM incoming_stock
        WHERE product_id = ? AND LOWER(status) IN (?, ?, ?)
        """,
        (product_id, *OUTSTANDING_STATUSES),
    ).fetchone()["total"]

    current = float(row["current_stock"])
    safety = float(row["safety_stock"])
    incoming_total = float(incoming or 0)
    demand = max(0.0, float(forecast_demand))
    required = demand + safety
    available = current + incoming_total
    reorder = calculate_reorder_quantity(demand, safety, current, incoming_total)
    coverage = available / required if required > 0 else 1.0

    if reorder <= 0:
        risk = "normal"
        recommendation = "Stock is sufficient"
    elif coverage < 0.55:
        risk = "high"
        recommendation = "Reorder urgently"
    else:
        risk = "medium"
        recommendation = "Reorder recommended"

    unit = row["unit"]
    name = row["product_name"]
    if reorder <= 0:
        why = (
            f"{name} does not currently need a reorder. Available stock is {available:,.0f} {unit} "
            f"(current stock plus outstanding incoming stock), which covers the 7-day forecast "
            f"of {demand:,.0f} {unit} plus safety stock of {safety:,.0f} {unit}."
        )
    else:
        why = (
            f"{name} is recommended for reorder because expected demand for the next 7 days is "
            f"{demand:,.0f} {unit} and safety stock is {safety:,.0f} {unit}. Required stock is "
            f"{required:,.0f} {unit}. Available stock is {available:,.0f} {unit} after adding "
            f"{incoming_total:,.0f} {unit} of outstanding incoming stock to current stock "
            f"({current:,.0f} {unit}). The resulting shortfall is {reorder:,.0f} {unit}."
        )
    reliability = forecast_reliability or "Not evaluated"
    reliability_note = (
        f" Forecast reliability is {reliability}; use this as confidence context when reviewing the order. "
        "Reliability does not change the exact stock-quantity formula."
    )
    if reliability == "Low Reliability":
        reliability_note += " Review recent sales and the expected order before confirming because forecast error is relatively high."
    why += reliability_note

    return {
        "product_id": row["product_id"],
        "product_name": name,
        "category": row["category"],
        "unit": unit,
        "current_stock": current,
        "safety_stock": safety,
        "incoming_stock": incoming_total,
        "forecast_demand": demand,
        "forecast_reliability": reliability,
        "required_stock": required,
        "available_stock": available,
        "reorder_quantity": reorder,
        "coverage_ratio": coverage,
        "risk": risk,
        "recommendation": recommendation,
        "why": why,
    }
