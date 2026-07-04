"""
Statistical assumption tests on the monthly company-revenue series (n=18,
2025-01 .. 2026-06). With only 18 monthly observations these tests have low
power - results are reported with that caveat rather than overinterpreted.
"""
import json
import numpy as np
import pandas as pd
import warnings
from statsmodels.tsa.stattools import adfuller, kpss, acf, pacf
from statsmodels.stats.diagnostic import acorr_ljungbox, het_breuschpagan, het_white
from statsmodels.stats.stattools import durbin_watson, jarque_bera
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant

warnings.filterwarnings("ignore")

OUT = "data/eda"


def main():
    m = pd.read_csv(f"{OUT}/monthly_sales.csv")
    y = m["revenue"].values
    n = len(y)
    results = {"n_obs": n}

    # ADF (H0: unit root / non-stationary)
    adf_stat, adf_p, *_ = adfuller(y, autolag="AIC")
    results["adf_stat"] = float(adf_stat)
    results["adf_pvalue"] = float(adf_p)

    # KPSS (H0: stationary)
    kpss_stat, kpss_p, *_ = kpss(y, regression="c", nlags="auto")
    results["kpss_stat"] = float(kpss_stat)
    results["kpss_pvalue"] = float(kpss_p)

    # ACF / PACF (first 6 lags, n too short for more)
    nlags = min(6, n // 2 - 1)
    acf_vals = acf(y, nlags=nlags, fft=False)
    pacf_vals = pacf(y, nlags=nlags)
    results["acf"] = [float(v) for v in acf_vals]
    results["pacf"] = [float(v) for v in pacf_vals]

    # seasonal decomposition (period=12) - only ~1.5 cycles available, indicative only
    try:
        sd = seasonal_decompose(pd.Series(y, index=pd.PeriodIndex(m["month"], freq="M")),
                                 model="additive", period=12, extrapolate_trend="freq")
        results["seasonal_decompose_seasonal_range"] = [float(sd.seasonal.min()), float(sd.seasonal.max())]
        sd_df = pd.DataFrame({"month": m["month"], "trend": sd.trend, "seasonal": sd.seasonal, "resid": sd.resid})
        sd_df.to_csv(f"{OUT}/seasonal_decompose.csv", index=False, encoding="utf-8-sig")
    except Exception as e:
        results["seasonal_decompose_error"] = str(e)

    # trend regression for residual diagnostics
    t = np.arange(n)
    X = add_constant(t)
    ols = OLS(y, X).fit()
    resid = ols.resid

    lb = acorr_ljungbox(resid, lags=[min(6, n // 3)], return_df=True)
    results["ljung_box_stat"] = float(lb["lb_stat"].iloc[0])
    results["ljung_box_pvalue"] = float(lb["lb_pvalue"].iloc[0])

    results["durbin_watson"] = float(durbin_watson(resid))

    jb_stat, jb_p, skew, kurt = jarque_bera(resid)
    results["jarque_bera_stat"] = float(jb_stat)
    results["jarque_bera_pvalue"] = float(jb_p)
    results["skewness"] = float(skew)
    results["kurtosis"] = float(kurt)

    bp_stat, bp_p, *_ = het_breuschpagan(resid, X)
    results["breusch_pagan_stat"] = float(bp_stat)
    results["breusch_pagan_pvalue"] = float(bp_p)

    try:
        white_stat, white_p, *_ = het_white(resid, X)
        results["white_test_stat"] = float(white_stat)
        results["white_test_pvalue"] = float(white_p)
    except Exception as e:
        results["white_test_error"] = str(e)

    # Ramsey RESET
    try:
        from statsmodels.stats.diagnostic import linear_reset
        reset = linear_reset(ols, power=2, use_f=True)
        results["ramsey_reset_stat"] = float(reset.fvalue)
        results["ramsey_reset_pvalue"] = float(reset.pvalue)
    except Exception as e:
        results["ramsey_reset_error"] = str(e)

    results["trend_coef_per_month"] = float(ols.params[1])
    results["trend_coef_pvalue"] = float(ols.pvalues[1])
    results["trend_r2"] = float(ols.rsquared)

    with open(f"{OUT}/timeseries_tests.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
