#!/usr/bin/env python3
"""
Time-series diagnostics on the monthly company-revenue series (n=18 months,
2025-01 .. 2026-06). With only 18 observations every classical asymptotic
test below has materially reduced power; results are reported together with
this caveat rather than presented as definitive (see academic report,
Limitations section).
"""
import json
import warnings
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller, kpss, acf, pacf
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.stats.diagnostic import acorr_ljungbox, het_breuschpagan, het_white, linear_reset
from statsmodels.stats.stattools import durbin_watson, jarque_bera
from statsmodels.stats.outliers_influence import variance_inflation_factor
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
M_CSV = ROOT / "data" / "processed" / "eda_monthly_series.csv"
OUT = ROOT / "data" / "processed" / "timeseries_diagnostics.json"


def main():
    m = pd.read_csv(M_CSV)
    y = m["revenue"].values
    n = len(y)
    t = np.arange(1, n + 1)

    out = {"n_obs": int(n), "series": "monthly company revenue (EGP), 2025-01..2026-06"}

    # ADF (level) — H0: unit root (non-stationary)
    adf_res = adfuller(y, autolag="AIC")
    out["adf_level"] = dict(stat=float(adf_res[0]), pvalue=float(adf_res[1]), lags=int(adf_res[2]),
                             crit_values={k: float(v) for k, v in adf_res[4].items()})
    # ADF on first difference
    adf_diff = adfuller(np.diff(y), autolag="AIC")
    out["adf_first_diff"] = dict(stat=float(adf_diff[0]), pvalue=float(adf_diff[1]), lags=int(adf_diff[2]))

    # KPSS (level) — H0: stationary
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        kpss_res = kpss(y, regression="c", nlags="auto")
    out["kpss_level"] = dict(stat=float(kpss_res[0]), pvalue=float(kpss_res[1]), lags=int(kpss_res[2]),
                              crit_values={k: float(v) for k, v in kpss_res[3].items()})

    # ACF / PACF (up to lag 8, n=18 -> keep lags <= n/2)
    max_lag = 8
    acf_vals = acf(y, nlags=max_lag, fft=True)
    pacf_vals = pacf(y, nlags=max_lag)
    out["acf"] = [float(v) for v in acf_vals]
    out["pacf"] = [float(v) for v in pacf_vals]
    # approx 95% CI under white-noise null: +/- 1.96/sqrt(n)
    out["acf_pacf_ci95"] = float(1.96 / np.sqrt(n))

    # Ljung-Box on levels (autocorrelation) at lags 6 and 12(not valid,too close to n) -> use 4,8
    lb = acorr_ljungbox(y, lags=[4, 8], return_df=True)
    out["ljung_box"] = lb.reset_index().to_dict(orient="records")

    # Seasonal decomposition (additive) — flagged as low-confidence: only 1.5 annual cycles
    try:
        sd = seasonal_decompose(pd.Series(y, index=pd.PeriodIndex(m["month"], freq="M")),
                                 model="additive", period=12, extrapolate_trend="freq")
        out["seasonal_decompose"] = dict(
            trend=[None if pd.isna(v) else float(v) for v in sd.trend],
            seasonal=[float(v) for v in sd.seasonal],
            resid=[None if pd.isna(v) else float(v) for v in sd.resid],
            note="Only ~1.5 annual cycles observed (18 months); seasonal component estimated with low precision.",
        )
    except Exception as e:
        out["seasonal_decompose_error"] = str(e)

    # Regression for residual diagnostics: revenue ~ trend + Fourier(12) seasonal terms
    # (2 harmonic terms instead of 11 month dummies to preserve degrees of freedom at n=18)
    X = pd.DataFrame({
        "trend": t,
        "sin12": np.sin(2 * np.pi * t / 12),
        "cos12": np.cos(2 * np.pi * t / 12),
    })
    X = sm.add_constant(X)
    model = sm.OLS(y, X).fit()
    out["ols_trend_seasonal"] = dict(
        params=model.params.to_dict(), pvalues=model.pvalues.to_dict(),
        r2=float(model.rsquared), r2_adj=float(model.rsquared_adj),
        f_pvalue=float(model.f_pvalue), n=int(n), df_resid=int(model.df_resid),
    )
    resid = model.resid

    # Durbin-Watson (autocorrelation of residuals)
    out["durbin_watson"] = float(durbin_watson(resid))

    # Jarque-Bera (normality of residuals)
    jb_stat, jb_p, skew, kurt = jarque_bera(resid)
    out["jarque_bera"] = dict(stat=float(jb_stat), pvalue=float(jb_p), skew=float(skew), kurtosis=float(kurt))

    # Breusch-Pagan (heteroskedasticity)
    bp_stat, bp_p, bp_f, bp_fp = het_breuschpagan(resid, X)
    out["breusch_pagan"] = dict(lm_stat=float(bp_stat), lm_pvalue=float(bp_p),
                                 f_stat=float(bp_f), f_pvalue=float(bp_fp))

    # White test (heteroskedasticity, general form)
    try:
        w_stat, w_p, w_f, w_fp = het_white(resid, X)
        out["white_test"] = dict(lm_stat=float(w_stat), lm_pvalue=float(w_p),
                                  f_stat=float(w_f), f_pvalue=float(w_fp))
    except Exception as e:
        out["white_test_error"] = str(e)

    # Ramsey RESET (functional form misspecification)
    try:
        reset_res = linear_reset(model, power=2, use_f=True)
        out["ramsey_reset"] = dict(stat=float(reset_res.statistic), pvalue=float(reset_res.pvalue))
    except Exception as e:
        out["ramsey_reset_error"] = str(e)

    # VIF (multicollinearity) on regressors excluding constant
    vif_data = {}
    Xv = X.drop(columns=["const"])
    for i, col in enumerate(Xv.columns):
        vif_data[col] = float(variance_inflation_factor(Xv.values, i))
    out["vif"] = vif_data

    # Simple Chow-style structural break test: split at t=13 (start of 2026, where
    # YoY growth accelerated sharply per the EDA monthly series) and at the midpoint.
    def chow_test(y, t, split_t):
        X_full = sm.add_constant(t.astype(float))
        rss_pooled = sm.OLS(y, X_full).fit().ssr
        m1 = t <= split_t
        m2 = ~m1
        if m1.sum() < 3 or m2.sum() < 3:
            return None
        rss1 = sm.OLS(y[m1], sm.add_constant(t[m1].astype(float))).fit().ssr
        rss2 = sm.OLS(y[m2], sm.add_constant(t[m2].astype(float))).fit().ssr
        k = 2
        n_ = len(y)
        f_stat = ((rss_pooled - (rss1 + rss2)) / k) / ((rss1 + rss2) / (n_ - 2 * k))
        from scipy.stats import f as f_dist
        p_value = 1 - f_dist.cdf(f_stat, k, n_ - 2 * k)
        return dict(split_t=int(split_t), f_stat=float(f_stat), pvalue=float(p_value))

    out["chow_test_split_2026_01"] = chow_test(y, t, 12)
    out["chow_test_split_midpoint"] = chow_test(y, t, n // 2)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: v for k, v in out.items() if k not in
                       ("acf", "pacf", "seasonal_decompose")}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
