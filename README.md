# STOCKORA — Adaptive Demand Forecasting & Intelligent Inventory Planning

**Tagline:** Predict Demand. Plan Smarter.

STOCKORA is a local-first inventory planning web application for a small retail or supermarket business. It turns daily sales history into a seven-day product demand forecast, reports chronological holdout error metrics, classifies forecast reliability, and calculates explainable reorder quantities.

> **Sample-data notice:** The included 112-day, 15-product sales dataset is deterministic synthetic demonstration data. It is not real-world retailer data.

## 1. Features

- Responsive cream, forest-green and orange dashboard with live SQLite-backed KPI cards.
- 15 seeded example products and 112 days of synthetic daily sales.
- Product-level seven-day demand forecasting with Statsmodels Holt-Winters exponential smoothing and a weekly seasonal component when enough training history is available.
- Chronological holdout evaluation with MAE and RMSE.
- Transparent reliability indicator based on normalized MAE.
- One combined Plotly chart showing actual historical demand and the following seven predicted days.
- Inventory calculations that include current stock, safety stock and outstanding incoming stock.
- A **Why?** explanation on every reorder recommendation.
- Searchable inventory table, editable current/safety stock, and calculated high/medium/normal alerts.
- CSV, XLSX and XLS upload with validation before any database write.
- Demand and forecast-performance analytics, product detail view and system settings.
- FastAPI JSON API and interactive API documentation at `/docs`.

## 2. Technology and architecture

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | HTML, CSS, JavaScript | Responsive multi-page SaaS interface |
| Charts | Plotly.js | Actual-vs-forecast, demand and model-performance charts |
| API | Python, FastAPI | JSON endpoints, file upload and frontend serving |
| Data processing | Pandas, NumPy | Daily aggregation, date continuity, validation and metrics |
| Forecasting | Statsmodels | Holt-Winters exponential smoothing |
| Database | SQLite | Persistent operational and forecast data |

The browser calls the FastAPI endpoints with `fetch()`. FastAPI reads and writes `backend/stockora.db`. The user does not manually type forecast values.

## 3. Folder structure

```text
STOCKORA/
├── backend/
│   ├── __init__.py
│   ├── main.py                 # FastAPI routes and web page delivery
│   ├── database.py             # SQLite schema, connection and seed data
│   ├── forecasting.py          # Statsmodels model, MAE/RMSE, reliability
│   ├── inventory.py             # Reorder calculation and explanation
│   └── stockora.db              # Seeded SQLite database (created on first run if absent)
├── frontend/
│   ├── index.html
│   ├── dashboard.html
│   ├── forecast.html
│   ├── inventory.html
│   ├── upload.html
│   ├── alerts.html
│   ├── analytics.html
│   ├── product.html
│   ├── settings.html
│   ├── css/
│   │   ├── style.css
│   │   ├── dashboard.css
│   │   └── theme.css
│   └── js/
│       ├── plotly.min.js           # Local Plotly.js bundle for offline charts
│       ├── api.js
│       ├── app.js
│       ├── dashboard.js
│       ├── forecast.js
│       ├── inventory.js
│       ├── upload.js
│       ├── alerts.js
│       ├── analytics.js
│       ├── product.js
│       └── settings.js
├── data/
│   └── sales.csv                # 1,680 synthetic daily sales rows
├── scripts/
│   └── generate_sample_data.py  # Reproducible synthetic data generator
├── tests/
│   └── test_logic.py
├── requirements.txt
├── requirements-dev.txt
├── .gitignore
└── README.md
```

## 4. Database schema

The application creates the five requested main tables. Indexes and constraints support data integrity and lookup performance; no additional application tables are required.

### `products`
`product_id` (primary key), `product_name`, `category`, `unit`, `price`.

### `sales`
`date`, `product_id`, `quantity_sold`. The `(date, product_id)` pair is unique; multiple valid uploaded transactions for one product/date are aggregated before being saved.

### `inventory`
`product_id` (primary key), `current_stock`, `safety_stock`.

### `incoming_stock`
`product_id`, `supplier`, `quantity`, `expected_date`, `status`. An incoming delivery contributes to available stock while its status is `pending`, `ordered` or `in_transit`. `received` and `cancelled` records are not counted.

### `forecasts`
`product_id`, `forecast_date`, `predicted_quantity`, `mae`, `rmse`. A forecast run replaces the previous seven records for that product. MAE and RMSE are saved with each forecast date.

## 5. Sample data

- 15 example products covering dairy, staples, bakery, snacks, beverages and personal care.
- 112 continuous dates from **2026-07-10 to 2026-10-29**.
- 1,680 product-day records (15 products × 112 days).
- Demand has a baseline by product, weekly/weekend patterns, gentle drift, promotion windows and seeded random noise. Regenerate the same data with:

```bash
python scripts/generate_sample_data.py
```

The included CSV columns are exactly `Date`, `Product ID`, `Quantity Sold`. Product IDs must match the seeded catalogue when importing a file.

## 6. Forecasting logic

For a selected product, STOCKORA:

1. Reads its sales in chronological order.
2. Parses dates and quantities, aggregates any same-day rows and inserts missing calendar dates as zero sales.
3. Requires at least 28 daily observations after cleaning.
4. Splits the series chronologically: the final 20% (at least seven days) is held out for evaluation, while at least 21 days remain for fitting.
5. Fits a Statsmodels `ExponentialSmoothing` Holt-Winters model with additive trend, damped trend, and additive seven-day seasonality when the training history permits it. The model is fitted only on the training segment for evaluation.
6. Calculates errors over the held-out days, then refits on all history and forecasts seven future daily values.
7. Persists the seven output values and the product's evaluation metrics into `forecasts`.

Predictions are constrained to non-negative demand. No forecast quantities or metric values are hardcoded in the frontend. If the model cannot produce valid output, the API reports a user-friendly error instead of silently substituting invented values.

### MAE

`MAE = mean(abs(actual - predicted))`

MAE is the average absolute difference between held-out actual demand and model predictions. Lower MAE means the prediction is closer to actual demand, on average.

### RMSE

`RMSE = sqrt(mean((actual - predicted) ** 2))`

RMSE gives greater weight to larger prediction errors.

### Forecast reliability rule

STOCKORA calculates `normalized MAE = MAE / max(historical average daily demand, 1)` and classifies it using the following explicit thresholds:

| Status | Rule |
|---|---|
| Reliable | normalized MAE ≤ 15% |
| Moderate | normalized MAE > 15% and ≤ 30% |
| Low Reliability | normalized MAE > 30% |

The UI displays the measured normalized error and the reason for the status. Reliability is a rule-based indicator derived from the model's held-out error; it is not a guarantee of future accuracy.

## 7. Inventory and reorder logic

The exact calculation is:

```text
Reorder Quantity = max(
    0,
    Forecast Demand + Safety Stock - Current Stock - Incoming Stock
)
```

`Incoming Stock` is the sum of outstanding deliveries (`pending`, `ordered`, `in_transit`). Available stock is `current stock + incoming stock`. The recommendation is then explained using the actual forecast and database stock values. Forecast reliability is shown alongside the reorder quantity and included in the explanation as decision context (especially when reliability is low); it does not alter the exact requested quantity formula. The example numbers in the project brief are not used as application constants.

Alert classification uses the ratio `available stock / (forecast demand + safety stock)`:

- **High:** ratio below 0.55 and a reorder is required.
- **Medium:** reorder is required but the ratio is at least 0.55.
- **Normal:** no reorder is required.

The thresholds are a transparent operational prioritization rule and can be adjusted in `backend/inventory.py`.

## 8. Installation on Windows (VS Code)

Use Python 3.11, 3.12 or a compatible newer Python. Python 3.12 is a good default for a hackathon laptop.

Open the STOCKORA project folder in VS Code. In the integrated PowerShell terminal, from the project root, run:

```powershell
python -m venv venv
```

Activate the environment:

```powershell
venv\Scripts\activate
```

If PowerShell blocks script activation, use the Command Prompt terminal and run `venv\Scripts\activate.bat`, or allow the current PowerShell process to run the activation script with:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 9. Run the application

From the project root:

```powershell
cd backend
uvicorn main:app --reload
```

Open the application in a browser:

- Dashboard: <http://127.0.0.1:8000/dashboard>
- Forecast: <http://127.0.0.1:8000/forecast>
- Inventory: <http://127.0.0.1:8000/inventory>
- Upload: <http://127.0.0.1:8000/upload>
- Alerts: <http://127.0.0.1:8000/alerts>
- Analytics: <http://127.0.0.1:8000/analytics>
- API docs: <http://127.0.0.1:8000/docs>

The frontend is served by FastAPI; do not open the HTML files with `file://`. Stop the server with `Ctrl+C`.

On first startup, STOCKORA creates/opens `backend/stockora.db`, seeds any missing product/stock records, imports `data/sales.csv` if the sales table is empty, and generates initial forecasts for products with enough history. The included database already contains the seeded records, but initialization is safe to run again. Product prices are illustrative INR values.

To rebuild the database from the included sample CSV, stop the server, delete `backend/stockora.db` (and any `stockora.db-wal` / `stockora.db-shm` files if present), and start the server again. The seed routine will recreate it.

## 10. Uploading sales data

Use **Upload Data** and choose `.csv`, `.xlsx` or `.xls`. The file must contain:

```text
Date | Product ID | Quantity Sold
```

The validator reports row count, distinct products, date range, missing values, duplicate rows, invalid dates, invalid quantities and unknown product IDs. The complete upload is rejected without inserting rows if invalid values or unknown products are found. Exact duplicate rows are reported and deduplicated. Multiple legitimate quantities for the same product and date are summed. When import succeeds, all available product forecasts are recalculated against the updated data.

## 11. API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Service and database health |
| GET | `/api/products` | Product catalogue |
| GET | `/api/dashboard` | KPI and stock-risk summary |
| GET | `/api/sales/{product_id}` | Historical daily sales |
| GET | `/api/forecast/{product_id}` | Saved forecast or auto-generate if absent |
| POST | `/api/forecast/{product_id}` | Train/evaluate and save a fresh seven-day forecast |
| GET | `/api/inventory` | All product stock and reorder calculations |
| GET | `/api/inventory/{product_id}` | One product's inventory calculation |
| PUT | `/api/inventory/{product_id}` | Update current and safety stock |
| GET | `/api/alerts` | Calculated inventory risk alerts |
| GET | `/api/analytics` | Demand ranking and model metrics |
| GET | `/api/product/{product_id}` | Combined product, forecast and stock detail |
| POST | `/api/upload` | Validate and import CSV/Excel sales data |
| GET | `/api/settings` | Application and model configuration |

FastAPI's interactive Swagger interface is available at `/docs`.

## 12. Hackathon demo flow

1. Open the Dashboard and explain that the numbers are loaded from SQLite.
2. Show the 15-product sample catalogue and the demand chart.
3. Open Forecast, select **Milk**, and click **Generate forecast**.
4. Explain that the model uses chronological training/testing, then show MAE, RMSE and the reason for reliability.
5. Point out that the chart joins historical actual demand with the seven future predictions.
6. Open Inventory and show current stock, safety stock, outstanding incoming stock and forecast demand.
7. Click **Why?** to show the exact reorder calculation in plain language.
8. Open Alerts to show calculated high-, medium- and normal-risk products.
9. Optionally edit a product's current stock and demonstrate that reorder quantity and alert level recalculate.
10. Optionally upload a small valid sales CSV and demonstrate automatic model refresh.

## 13. Tests

Install development requirements and run from the project root:

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

The included unit tests verify the required reorder formula and reliability classification thresholds. The project was also checked with API startup, SQLite seeding, product forecast generation, CSV upload validation, inventory updates and the main frontend/API routes during build.

## 14. Notes and future scope

- Plotly.js is served locally from `frontend/js/plotly.min.js`, so charts work without internet access. Google Fonts are optional; system font fallbacks are used when offline.
- This is a single-workspace hackathon application and intentionally has no login, payments, checkout, hardware, IoT or microservices.
- Future enhancements could include supplier lead-time modeling, forecast intervals, configurable business calendars, multi-store support and scheduled forecast refreshes.
