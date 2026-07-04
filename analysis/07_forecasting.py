#!/usr/bin/env python3
"""
Forecasting model comparison and 7-month-ahead forecasts.

Data constraint that shapes every choice below: only 18 monthly observations
(2025-01 .. 2026-06) are available. Seasonal models with an annual period
(SARIMA(...,12), Holt-Winters seasonal, Prophet's default yearly-seasonality
prior) all require >= 2 full seasonal cycles (24 observations) to identify
the seasonal component; statsmodels raises this exact error if forced (see
06_timeseries_tests.py). We therefore compare the set of models that can be
honestly estimated at n=18: Naive, Drift, Simple Exponential Smoothing (SES),
Holt's linear trend (ETS-AAN, no seasonal), a grid of non-seasonal ARIMA(p,d,q)
models selected by AIC, and a trend+Fourier dynamic regression (a lightweight
stand-in for the seasonal signal that avoids the 24-observation requirement).
Prophet is not fitted: its default settings assume >= 1-2 years of daily/
weekly data for its changepoint and yearly-seasonality priors, and pulling in
the full Stan toolchain is not justified for an 18-point monthly series where
the statsmodels alternatives already span the same model space.
"""
import json
import warnings
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.holtwinters import SimpleExpSmoothing, Holt
from statsmodels.tsa.arima.model import ARIMA
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
M_CSV = ROOT / "data" / "processed" / "eda_monthly_series.csv"
TX = ROOT / "data" / "processed" / "sales_transactions_enriched.csv"
OUT = ROOT / "data" / "processed" / "forecast_results.json"

FUTURE_MONTHS = ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11", "2026-12", "2027-01"]


def mape(actual, pred):
    actual, pred = np.asarray(actual), np.asarray(pred)
    mask = actual != 0
    return float(np.mean(np.abs((actual[mask] - pred[mask]) / actual[mask])) * 100) if mask.any() else np.nan


def smape(actual, pred):
    actual, pred = np.asarray(actual), np.asarray(pred)
    denom = (np.abs(actual) + np.abs(pred))
    mask = denom != 0
    return float(np.mean(2 * np.abs(actual[mask] - pred[mask]) / denom[mask]) * 100) if mask.any() else np.nan


def fit_forecast_naive(y_train, h):
    return np.repeat(y_train[-1], h)


def fit_forecast_drift(y_train, h):
    n = len(y_train)
    slope = (y_train[-1] - y_train[0]) / (n - 1)
    return y_train[-1] + slope * np.arange(1, h + 1)


def fit_forecast_ses(y_train, h):
    m = SimpleExpSmoothing(y_train, initialization_method="estimated").fit()
    return m.forecast(h), m.aic


def fit_forecast_holt(y_train, h):
    m = Holt(y_train, initialization_method="estimated").fit()
    return m.forecast(h), m.aic


def fit_forecast_arima(y_train, h, order):
    m = ARIMA(y_train, order=order).fit()
    fc = m.get_forecast(h)
    return fc.predicted_mean, m.aic, m.bic, fc


def fit_forecast_fourier(y_train, h):
    n = len(y_train)
    t = np.arange(1, n + 1)
    X = sm.add_constant(pd.DataFrame({"trend": t, "sin12": np.sin(2 * np.pi * t / 12),
                                       "cos12": np.cos(2 * np.pi * t / 12)}))
    m = sm.OLS(y_train, X).fit()
    t_future = np.arange(n + 1, n + h + 1)
    Xf = sm.add_constant(pd.DataFrame({"trend": t_future, "sin12": np.sin(2 * np.pi * t_future / 12),
                                        "cos12": np.cos(2 * np.pi * t_future / 12)}), has_constant="add")
    pred = m.get_prediction(Xf)
    return pred.predicted_mean, m.aic, m.bic, pred


def rolling_origin_cv(y, min_train=10, h=1):
    """One-step-ahead expanding-window walk-forward CV."""
    models = {}
    errors = {name: [] for name in
              ["Naive", "Drift", "SES", "Holt", "ARIMA(1,1,0)", "ARIMA(0,1,1)", "ARIMA(1,1,1)", "Fourier-OLS"]}
    for origin in range(min_train, len(y) - h + 1):
        y_train, y_test = y[:origin], y[origin:origin + h]
        preds = {}
        preds["Naive"] = fit_forecast_naive(y_train, h)
        preds["Drift"] = fit_forecast_drift(y_train, h)
        try:
            preds["SES"], _ = fit_forecast_ses(y_train, h)
        except Exception:
            preds["SES"] = np.repeat(np.nan, h)
        try:
            preds["Holt"], _ = fit_forecast_holt(y_train, h)
        except Exception:
            preds["Holt"] = np.repeat(np.nan, h)
        for order in [(1, 1, 0), (0, 1, 1), (1, 1, 1)]:
            key = "ARIMA(" + ",".join(str(x) for x in order) + ")"
            try:
                pred, *_ = fit_forecast_arima(y_train, h, order)
                preds[key] = np.asarray(pred)
            except Exception:
                preds[key] = np.repeat(np.nan, h)
        try:
            preds["Fourier-OLS"], *_ = fit_forecast_fourier(y_train, h)
        except Exception:
            preds["Fourier-OLS"] = np.repeat(np.nan, h)

        for name in errors:
            key = name if name in preds else name.replace("ARIMA", "ARIMA")
            p = preds.get(name)
            if p is None or np.any(np.isnan(p)):
                continue
            errors[name].append(dict(actual=float(y_test[0]), pred=float(np.asarray(p)[0])))
    return errors


def summarize_cv(errors):
    summary = {}
    for name, recs in errors.items():
        if not recs:
            summary[name] = None
            continue
        actual = np.array([r["actual"] for r in recs])
        pred = np.array([r["pred"] for r in recs])
        summary[name] = dict(
            n_folds=len(recs),
            rmse=float(np.sqrt(np.mean((actual - pred) ** 2))),
            mae=float(np.mean(np.abs(actual - pred))),
            mape=mape(actual, pred),
            smape=smape(actual, pred),
        )
    return summary


def main():
    m = pd.read_csv(M_CSV)
    y = m["revenue"].values
    months = m["month"].tolist()

    cv_errors = rolling_origin_cv(y, min_train=10, h=1)
    cv_summary = summarize_cv(cv_errors)
    valid = {k: v for k, v in cv_summary.items() if v is not None}
    best_model = min(valid, key=lambda k: valid[k]["rmse"])

    # in-sample AIC/BIC for model classes fit on full data (for reference)
    in_sample = {}
    for order in [(1, 1, 0), (0, 1, 1), (1, 1, 1), (2, 1, 1), (1, 1, 2)]:
        try:
            mm = ARIMA(y, order=order).fit()
            in_sample[f"ARIMA{order}"] = dict(aic=float(mm.aic), bic=float(mm.bic))
        except Exception:
            pass
    ses_m = SimpleExpSmoothing(y, initialization_method="estimated").fit()
    in_sample["SES"] = dict(aic=float(ses_m.aic), bic=float(ses_m.bic))
    holt_m = Holt(y, initialization_method="estimated").fit()
    in_sample["Holt"] = dict(aic=float(holt_m.aic), bic=float(holt_m.bic))

    # 7-month forecast using the CV-selected best model (fallback: Holt, a robust
    # trend model, if the CV winner cannot produce a valid prediction interval)
    h = 7
    if best_model.startswith("ARIMA"):
        order = eval(best_model.replace("ARIMA", ""))
        model_fit = ARIMA(y, order=order).fit()
        fc = model_fit.get_forecast(h)
        point = fc.predicted_mean
        ci95 = fc.conf_int(alpha=0.05)
        se = fc.se_mean
    elif best_model == "Holt":
        model_fit = Holt(y, initialization_method="estimated").fit()
        fc_res = model_fit.forecast(h)
        resid_std = np.std(model_fit.resid, ddof=1)
        se = resid_std * np.sqrt(np.arange(1, h + 1))
        point = fc_res
        ci95 = np.column_stack([point - 1.96 * se, point + 1.96 * se])
    elif best_model == "SES":
        model_fit = SimpleExpSmoothing(y, initialization_method="estimated").fit()
        fc_res = model_fit.forecast(h)
        resid_std = np.std(model_fit.resid, ddof=1)
        se = resid_std * np.sqrt(np.arange(1, h + 1))
        point = fc_res
        ci95 = np.column_stack([point - 1.96 * se, point + 1.96 * se])
    else:  # Naive / Drift / Fourier-OLS fallback -> use Holt as the production model
        best_model = best_model + " (production model: Holt, for a usable trend + interval)"
        model_fit = Holt(y, initialization_method="estimated").fit()
        fc_res = model_fit.forecast(h)
        resid_std = np.std(model_fit.resid, ddof=1)
        se = resid_std * np.sqrt(np.arange(1, h + 1))
        point = fc_res
        ci95 = np.column_stack([point - 1.96 * se, point + 1.96 * se])

    point = np.asarray(point)
    ci95 = np.asarray(ci95)
    forecast_table = []
    for i, mth in enumerate(FUTURE_MONTHS):
        base = float(point[i])
        lo, hi = float(ci95[i, 0]), float(ci95[i, 1])
        forecast_table.append(dict(
            month=mth, base_case=base,
            conservative_case=max(lo, 0.0),
            optimistic_case=hi,
            ci95_lower=max(lo, 0.0), ci95_upper=hi,
        ))

    out = dict(
        cv_summary=cv_summary,
        best_model_by_rolling_rmse=best_model,
        in_sample_aic_bic=in_sample,
        forecast_company_revenue=forecast_table,
        historical_months=months,
        historical_revenue=y.tolist(),
        method_note=(f"يعتمد اختيار النموذج على التحقق المتدحرج (Rolling-origin, expanding window, one-step-ahead) "
                      f"عبر آخر {len(next(iter(cv_errors.values())))} أشهر، باختيار النموذج الأقل خطأ (RMSE) خارج "
                      "العيّنة؛ ثم تتم إعادة معايرة هذا النموذج على كامل تاريخ الـ18 شهرًا لإنتاج توقع 7 أشهر مقبلة "
                      "مع فترة ثقة 95% مبنية على تقريب التوزيع الطبيعي."),
    )
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: v for k, v in out.items() if k not in ("historical_revenue",)},
                      ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
