#!/usr/bin/env python3
"""
Brand / top-customer / top-item 7-month forecasts using Holt's linear-trend
method (the model class selected by the company-level rolling-origin CV in
07_forecasting.py). A full per-series CV+model-grid as in 07 is not repeated
for every brand/customer/item (disproportionate to the decision value at that
granularity); Holt is applied consistently and each series' own in-sample
residual standard deviation drives its 95% interval width.
"""
import json
import warnings
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import Holt
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
TX = ROOT / "data" / "processed" / "sales_transactions_enriched.csv"
OUT = ROOT / "data" / "processed" / "forecast_disaggregated.json"
FUTURE_MONTHS = ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12", "2027-01"]
H = 7


def holt_forecast(y):
    if len(y) < 6 or np.all(y == y[0]):
        # too short / degenerate for Holt -> flat naive with wide interval
        last = y[-1] if len(y) else 0.0
        resid_std = np.std(y) if len(y) > 1 else abs(last) * 0.3
        point = np.repeat(last, H)
        se = resid_std * np.sqrt(np.arange(1, H + 1))
        return point, se, "naive_fallback"
    m = Holt(y, initialization_method="estimated").fit()
    point = m.forecast(H)
    resid_std = np.std(m.resid, ddof=1) if len(m.resid) > 1 else abs(y[-1]) * 0.3
    se = resid_std * np.sqrt(np.arange(1, H + 1))
    return point, se, "holt"


def build_series(df, group_col, group_val, months):
    sub = df[df[group_col] == group_val]
    g = sub.groupby("month")["line_total"].sum().reindex(months, fill_value=0)
    return g.values


def main():
    df = pd.read_csv(TX, dtype={"customer_code": str})
    df["invoice_date_parsed"] = pd.to_datetime(df["invoice_date"], format="%Y/%m/%d")
    df["month"] = df["invoice_date_parsed"].dt.to_period("M").astype(str)
    months = sorted(df["month"].unique())

    results = {"brands": {}, "top_customers": {}, "top_items": {}}

    for brand in df["brand"].unique():
        y = build_series(df, "brand", brand, months)
        point, se, method = holt_forecast(y)
        results["brands"][brand] = dict(
            method=method, historical=y.tolist(),
            forecast=[dict(month=mth, base_case=float(point[i]),
                            conservative_case=float(max(point[i] - 1.96 * se[i], 0)),
                            optimistic_case=float(point[i] + 1.96 * se[i]))
                      for i, mth in enumerate(FUTURE_MONTHS)],
        )

    top_customers = df.groupby("customer_code")["line_total"].sum().sort_values(ascending=False).head(10).index
    name_map = df.groupby("customer_code")["customer_name_raw"].agg(lambda s: s.value_counts().index[0])
    for code in top_customers:
        y = build_series(df, "customer_code", code, months)
        point, se, method = holt_forecast(y)
        results["top_customers"][code] = dict(
            name=name_map[code], method=method, historical=y.tolist(),
            forecast=[dict(month=mth, base_case=float(point[i]),
                            conservative_case=float(max(point[i] - 1.96 * se[i], 0)),
                            optimistic_case=float(point[i] + 1.96 * se[i]))
                      for i, mth in enumerate(FUTURE_MONTHS)],
        )

    top_items = df.groupby("item_name_canonical")["line_total"].sum().sort_values(ascending=False).head(10).index
    for item in top_items:
        y = build_series(df, "item_name_canonical", item, months)
        point, se, method = holt_forecast(y)
        results["top_items"][item] = dict(
            method=method, historical=y.tolist(),
            forecast=[dict(month=mth, base_case=float(point[i]),
                            conservative_case=float(max(point[i] - 1.96 * se[i], 0)),
                            optimistic_case=float(point[i] + 1.96 * se[i]))
                      for i, mth in enumerate(FUTURE_MONTHS)],
        )

    results["months_historical"] = months
    results["months_future"] = FUTURE_MONTHS
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    for b, r in results["brands"].items():
        print(b, r["method"], [round(x["base_case"]) for x in r["forecast"][:3]])


if __name__ == "__main__":
    main()
