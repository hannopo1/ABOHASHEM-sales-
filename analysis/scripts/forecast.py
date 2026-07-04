"""
Forecast model comparison and 7-month-ahead forecasting.

Honest caveat baked into the method: the company-level monthly series has
only n=18 observations (2025-01 .. 2026-06), which is far short of the 24+
points normally wanted for seasonal models. We therefore restrict the
candidate set to models that are identifiable at this sample size (naive
drift, linear trend, damped-trend Holt, non-seasonal ARIMA/SARIMA on small
orders, simple exponential smoothing) rather than fitting a 12-period
seasonal model that would just overfit 18 points. Model selection is done
by rolling-origin (walk-forward) one-step-ahead cross-validation, which is
the only CV scheme that respects time ordering at this sample size.
"""
import json
import warnings
import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing, SimpleExpSmoothing
from statsmodels.tsa.arima.model import ARIMA

warnings.filterwarnings("ignore")

OUT = "data/eda"
H = 7  # forecast horizon (months)


def naive_drift_forecast(y, h):
    n = len(y)
    drift = (y[-1] - y[0]) / (n - 1)
    return np.array([y[-1] + drift * (i + 1) for i in range(h)])


def fit_and_forecast(y, model_name, h):
    if model_name == "naive_drift":
        fc = naive_drift_forecast(y, h)
        resid_std = np.std(np.diff(y) - (y[-1] - y[0]) / (len(y) - 1)) if len(y) > 2 else np.std(y) * 0.1
        return fc, resid_std
    if model_name == "ses":
        m = SimpleExpSmoothing(y, initialization_method="estimated").fit()
        fc = m.forecast(h)
        resid_std = np.std(m.resid)
        return fc, resid_std
    if model_name == "holt_damped":
        m = ExponentialSmoothing(y, trend="add", damped_trend=True, initialization_method="estimated").fit()
        fc = m.forecast(h)
        resid_std = np.std(m.resid)
        return fc, resid_std
    if model_name == "holt_linear":
        m = ExponentialSmoothing(y, trend="add", damped_trend=False, initialization_method="estimated").fit()
        fc = m.forecast(h)
        resid_std = np.std(m.resid)
        return fc, resid_std
    if model_name.startswith("arima"):
        order = tuple(int(x) for x in model_name.split("_")[1])
        m = ARIMA(y, order=order).fit()
        fc_res = m.get_forecast(h)
        fc = fc_res.predicted_mean
        resid_std = np.std(m.resid)
        return np.asarray(fc), resid_std
    raise ValueError(model_name)


CANDIDATES = ["naive_drift", "ses", "holt_damped", "holt_linear", "arima_101", "arima_010", "arima_111"]


def rolling_cv(y, min_train=10):
    n = len(y)
    scores = {c: [] for c in CANDIDATES}
    for cut in range(min_train, n):
        train, actual = y[:cut], y[cut]
        for c in CANDIDATES:
            try:
                fc, _ = fit_and_forecast(train, c, 1)
                pred = fc[0]
                scores[c].append((pred - actual))
            except Exception:
                scores[c].append(np.nan)
    rows = []
    for c, errs in scores.items():
        errs = np.array(errs, dtype=float)
        valid = ~np.isnan(errs)
        if valid.sum() == 0:
            continue
        e = errs[valid]
        actuals = y[min_train:][valid]
        rmse = np.sqrt(np.mean(e ** 2))
        mae = np.mean(np.abs(e))
        mape = np.mean(np.abs(e / actuals)) * 100
        rows.append({"model": c, "n_folds": int(valid.sum()), "rmse": rmse, "mae": mae, "mape": mape})
    return pd.DataFrame(rows).sort_values("rmse")


def forecast_series(y, months, best_model, h=H):
    fc, resid_std = fit_and_forecast(y, best_model, h)
    z95 = 1.96
    lo = fc - z95 * resid_std * np.sqrt(np.arange(1, h + 1))
    hi = fc + z95 * resid_std * np.sqrt(np.arange(1, h + 1))
    last_month = pd.Period(months[-1], freq="M")
    future_months = [str(last_month + i) for i in range(1, h + 1)]
    df = pd.DataFrame({
        "month": future_months,
        "forecast_base": fc,
        "forecast_conservative": lo,
        "forecast_optimistic": hi,
        "ci95_lower": lo,
        "ci95_upper": hi,
    })
    return df


def main():
    m = pd.read_csv(f"{OUT}/monthly_sales.csv")
    y = m["revenue"].values
    months = m["month"].tolist()

    cv = rolling_cv(y)
    cv.to_csv(f"{OUT}/forecast_model_comparison.csv", index=False, encoding="utf-8-sig")
    best_model = cv.iloc[0]["model"]
    print("Model comparison (rolling-origin CV):")
    print(cv)
    print("Best model:", best_model)

    fc_df = forecast_series(y, months, best_model)
    fc_df.insert(0, "level", "company_total")
    fc_df.insert(1, "series_id", "TOTAL")
    fc_df.to_csv(f"{OUT}/forecast_company.csv", index=False, encoding="utf-8-sig")
    print(fc_df)

    with open(f"{OUT}/forecast_meta.json", "w", encoding="utf-8") as f:
        json.dump({"best_model": best_model, "n_obs": len(y), "horizon": H}, f, ensure_ascii=False, indent=2)

    # brand-level forecasts using same best model (fallback to naive_drift on short/sparse series)
    bm = pd.read_csv(f"{OUT}/brand_monthly.csv")
    brand_frames = []
    for brand, d in bm.groupby("brand"):
        d = d.sort_values("month")
        yy = d["line_total"].values
        if len(yy) < 6:
            continue
        try:
            fdf = forecast_series(yy, d["month"].tolist(), best_model)
        except Exception:
            fdf = forecast_series(yy, d["month"].tolist(), "naive_drift")
        fdf.insert(0, "level", "brand")
        fdf.insert(1, "series_id", brand)
        brand_frames.append(fdf)
    if brand_frames:
        pd.concat(brand_frames, ignore_index=True).to_csv(f"{OUT}/forecast_brand.csv", index=False, encoding="utf-8-sig")

    # top-10 customer level forecasts
    hcust = pd.read_csv("data/invoices_header_merged.csv", dtype={"customer_code": str})
    hcust["date"] = pd.to_datetime(hcust["date"], format="%Y/%m/%d")
    hcust["month"] = hcust["date"].dt.to_period("M").astype(str)
    top_custs = pd.read_csv(f"{OUT}/customer_ranking.csv").head(10)["customer_code"].astype(str).tolist()
    cust_frames = []
    for code in top_custs:
        d = hcust[hcust["customer_code"] == code].groupby("month")["invoice_total"].sum().reset_index()
        d = d.sort_values("month")
        yy = d["invoice_total"].values
        if len(yy) < 6:
            continue
        try:
            fdf = forecast_series(yy, d["month"].tolist(), best_model)
        except Exception:
            fdf = forecast_series(yy, d["month"].tolist(), "naive_drift")
        fdf.insert(0, "level", "customer")
        fdf.insert(1, "series_id", code)
        cust_frames.append(fdf)
    if cust_frames:
        pd.concat(cust_frames, ignore_index=True).to_csv(f"{OUT}/forecast_top_customers.csv", index=False, encoding="utf-8-sig")

    # top-10 item level forecasts
    litems = pd.read_csv("data/invoice_lines_merged.csv", dtype={"item_code": str})
    litems = litems.merge(hcust[["invoice_id", "month"]], on="invoice_id", how="left")
    top_items = pd.read_csv(f"{OUT}/item_ranking_abc_xyz.csv").head(10)["item_code"].astype(str).tolist()
    item_frames = []
    for code in top_items:
        d = litems[litems["item_code"] == code].groupby("month")["line_total"].sum().reset_index()
        d = d.sort_values("month")
        yy = d["line_total"].values
        if len(yy) < 6:
            continue
        try:
            fdf = forecast_series(yy, d["month"].tolist(), best_model)
        except Exception:
            fdf = forecast_series(yy, d["month"].tolist(), "naive_drift")
        fdf.insert(0, "level", "item")
        fdf.insert(1, "series_id", code)
        item_frames.append(fdf)
    if item_frames:
        pd.concat(item_frames, ignore_index=True).to_csv(f"{OUT}/forecast_top_items.csv", index=False, encoding="utf-8-sig")

    # top-10 item level forecasts IN UNITS (qty) - needed for carton/production planning,
    # kept separate from the revenue forecast above so currency and units are never mixed.
    item_qty_frames = []
    for code in top_items:
        d = litems[litems["item_code"] == code].groupby("month")["qty"].sum().reset_index()
        d = d.sort_values("month")
        yy = d["qty"].values
        if len(yy) < 6:
            continue
        try:
            fdf = forecast_series(yy, d["month"].tolist(), best_model)
        except Exception:
            fdf = forecast_series(yy, d["month"].tolist(), "naive_drift")
        fdf.insert(0, "level", "item_qty")
        fdf.insert(1, "series_id", code)
        item_qty_frames.append(fdf)
    if item_qty_frames:
        pd.concat(item_qty_frames, ignore_index=True).to_csv(f"{OUT}/forecast_top_items_qty.csv", index=False, encoding="utf-8-sig")

    print("\nDone. Forecast files written to data/eda/")


if __name__ == "__main__":
    main()
