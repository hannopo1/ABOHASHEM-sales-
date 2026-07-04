#!/usr/bin/env python3
"""
Revenue-based financial analysis. IMPORTANT SCOPE LIMIT: the uploaded files
contain no cost data (no COGS, no bill-of-materials, no production/purchase
prices, no payroll or overhead). Consequently COGS, Gross Profit, Gross
Margin, Operating Margin, EBITDA, Net Profit and Inventory Turnover CANNOT be
computed and are intentionally NOT reported here (reporting them would
require inventing a cost assumption, which the brief explicitly forbids).
Everything below is computed strictly from: (a) the parsed sales invoices,
and (b) the 2026-07-04 accounts-receivable snapshot across 8 sales-rep books.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TX = ROOT / "data" / "processed" / "sales_transactions_enriched.csv"
AR = ROOT / "data" / "processed" / "ar_customer_balances_2026-07-04.csv"
OUT = ROOT / "data" / "processed" / "financial_analysis.json"


def main():
    df = pd.read_csv(TX, dtype={"customer_code": str})
    df["invoice_date_parsed"] = pd.to_datetime(df["invoice_date"], format="%Y/%m/%d")
    df["month"] = df["invoice_date_parsed"].dt.to_period("M").astype(str)
    ar = pd.read_csv(AR, dtype={"customer_code": str})
    ar["net_balance"] = ar["debit"] - ar["credit"]

    out = {}
    out["total_revenue_egp"] = float(df["line_total"].sum())
    out["period"] = dict(start=str(df["invoice_date_parsed"].min().date()),
                          end=str(df["invoice_date_parsed"].max().date()), n_months=int(df["month"].nunique()))

    # trailing-12-month revenue (2025-07 .. 2026-06) for run-rate / DSO purposes
    last12_months = sorted(df["month"].unique())[-12:]
    rev_t12 = float(df[df["month"].isin(last12_months)]["line_total"].sum())
    out["trailing_12m_revenue_egp"] = rev_t12
    out["trailing_12m_months"] = last12_months
    out["avg_monthly_revenue_t12_egp"] = rev_t12 / 12

    # gross (list-price) value vs net value -> effective aggregate deduction rate
    gross_value = float((df["qty"] * df["unit_price"]).sum())
    net_value = float(df["line_total"].sum())
    out["gross_list_value_egp"] = gross_value
    out["net_invoiced_value_egp"] = net_value
    out["aggregate_deduction_value_egp"] = gross_value - net_value
    out["aggregate_deduction_rate_pct"] = (gross_value - net_value) / gross_value * 100 if gross_value else None
    out["deduction_field_note"] = ("الحقل المصدري المسمّى \"نسبة الضريبة\" (tax %) يعمل فعليًا كنسبة استقطاع تُخصم من "
                                    "حاصل ضرب الكمية × سعر الوحدة للوصول إلى إجمالي بند الفاتورة — وهذا مؤكَّد بمطابقة "
                                    "تامة مع الإجمالي المطبوع في كل فاتورة على حدة (صفر فروقات تتجاوز جنيهًا واحدًا عبر "
                                    "4,902 فاتورة). لذلك يُعرض هنا كاستقطاع إجمالي (Aggregate Deduction) وليس كضريبة قيمة "
                                    "مضافة، لأن النسب المرصودة (0-25%) لا تطابق نسبة ضريبة القيمة المضافة المصرية "
                                    "القياسية (14%) وتتفاوت حسب الفاتورة/العميل — وهو ما يتسق مع نظام خصم/حسم تجاري خاص "
                                    "بالعميل أو بقناة التوزيع أكثر من كونه ضريبة نظامية.")

    weighted_disc = float(np.average(df["discount_pct"], weights=df["qty"].clip(lower=0.01)))
    weighted_ded = float(np.average(df["tax_pct"].fillna(0), weights=df["qty"].clip(lower=0.01)))
    out["qty_weighted_avg_discount_pct_field"] = weighted_disc
    out["qty_weighted_avg_deduction_pct_field"] = weighted_ded

    # bonus / free-goods value (promotional giveaways priced at 0) valued at
    # each item's own period average selling price
    bonus = df[df["is_bonus"] & (df["unit_price"] == 0) & (df["qty"] > 0)]
    item_asp = df[(~df["is_bonus"]) & (df["unit_price"] > 0)].groupby("item_name_canonical").apply(
        lambda g: g["line_total"].sum() / g["qty"].sum())
    bonus_valued = bonus.groupby("item_name_canonical")["qty"].sum() * item_asp.reindex(
        bonus.groupby("item_name_canonical")["qty"].sum().index)
    out["bonus_lines_count"] = int(len(bonus))
    out["bonus_qty_total"] = float(bonus["qty"].sum())
    out["bonus_estimated_value_at_asp_egp"] = float(bonus_valued.sum(skipna=True))
    out["bonus_value_pct_of_revenue"] = out["bonus_estimated_value_at_asp_egp"] / net_value * 100

    # customer concentration
    cust_rev = df.groupby("customer_code")["line_total"].sum().sort_values(ascending=False)
    out["hhi_customers"] = float(((cust_rev / cust_rev.sum()) ** 2).sum() * 10000)
    out["top5_customer_share_pct"] = float(cust_rev.head(5).sum() / cust_rev.sum() * 100)
    out["top10_customer_share_pct"] = float(cust_rev.head(10).sum() / cust_rev.sum() * 100)
    out["top20_customer_share_pct"] = float(cust_rev.head(20).sum() / cust_rev.sum() * 100)
    out["n_customers"] = int(cust_rev.shape[0])

    # brand concentration
    brand_rev = df.groupby("brand")["line_total"].sum().sort_values(ascending=False)
    out["hhi_brands"] = float(((brand_rev / brand_rev.sum()) ** 2).sum() * 10000)
    out["brand_shares_pct"] = (brand_rev / brand_rev.sum() * 100).round(2).to_dict()

    # product concentration
    item_rev = df.groupby("item_name_canonical")["line_total"].sum().sort_values(ascending=False)
    out["hhi_items"] = float(((item_rev / item_rev.sum()) ** 2).sum() * 10000)
    out["top10_item_share_pct"] = float(item_rev.head(10).sum() / item_rev.sum() * 100)

    # customer historical-value proxy (NOT a predictive CLV model -- see limitations)
    cust_g = df.groupby("customer_code").agg(
        total_revenue=("line_total", "sum"),
        first_month=("month", "min"), last_month=("month", "max"),
        n_months_active=("month", "nunique"), n_invoices=("invoice_no", "nunique"))
    cust_g["revenue_per_active_month"] = cust_g["total_revenue"] / cust_g["n_months_active"]
    out["avg_revenue_per_active_month_per_customer_egp"] = float(cust_g["revenue_per_active_month"].mean())
    out["median_revenue_per_active_month_per_customer_egp"] = float(cust_g["revenue_per_active_month"].median())

    # AR / receivables analysis (point-in-time snapshot 2026-07-04)
    out["ar_total_net_balance_egp"] = float(ar["net_balance"].sum())
    out["ar_total_debit_egp"] = float(ar["debit"].sum())
    out["ar_total_credit_egp"] = float(ar["credit"].sum())
    out["ar_n_customers_with_debit_balance"] = int((ar["debit"] > 0).sum())
    out["ar_n_customers_with_credit_balance"] = int((ar["credit"] > 0).sum())
    ar_by_rep = ar.groupby("rep").apply(lambda g: pd.Series({
        "net_balance": g["net_balance"].sum(), "n_customers": g["customer_code"].nunique(),
        "debit": g["debit"].sum(), "credit": g["credit"].sum()})).reset_index()
    out["ar_by_rep"] = ar_by_rep.to_dict(orient="records")

    # DSO proxy: AR balance / (trailing-12m revenue / 365) -- approximation since
    # the AR snapshot postdates the transactional data by only ~4 days (2026-06-30 -> 2026-07-04)
    daily_revenue = rev_t12 / 365
    out["dso_proxy_days"] = float(ar["net_balance"].sum() / daily_revenue) if daily_revenue else None
    out["dso_proxy_method_note"] = ("طريقة الاحتساب التقريبية = صافي رصيد المديونية (2026/7/4) ÷ (إيراد آخر 12 شهرًا "
                                     "÷ 365). هذا تقدير تقريبي وليس مؤشر DSO رسميًا محسوبًا من كشف حركة مديونية متسلسل "
                                     "زمنيًا، نظرًا لتوفر لقطة واحدة فقط لرصيد المديونية في نقطة زمنية محددة (بلا رصيد "
                                     "افتتاحي، وبلا تصنيف أعمار الديون حسب تاريخ كل فاتورة).")

    # concentration of AR itself (top debtors)
    ar_sorted = ar.groupby("customer_code")["net_balance"].sum().sort_values(ascending=False)
    out["ar_top10_debtor_share_pct"] = float(ar_sorted.head(10).clip(lower=0).sum() /
                                              ar[ar["net_balance"] > 0]["net_balance"].sum() * 100)
    out["ar_hhi_debtors"] = float(((ar_sorted.clip(lower=0) / ar_sorted.clip(lower=0).sum()) ** 2).sum() * 10000)

    out["not_computable_due_to_missing_cost_data"] = [
        "COGS (تكلفة البضاعة المباعة)", "Gross Profit / إجمالي الربح", "Gross Margin / هامش الربح الإجمالي",
        "Operating Margin / الهامش التشغيلي", "EBITDA", "Net Profit / صافي الربح",
        "Working Capital (يتطلب بيانات الأصول/الخصوم المتداولة الكاملة)",
        "Inventory Turnover (لا توجد بيانات مخزون/أرصدة مخزنية)",
        "Receivables Turnover الرسمي (يتطلب سلسلة أرصدة مدينين تاريخية، وليس لقطة واحدة)",
    ]
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(json.dumps({k: v for k, v in out.items() if k != "ar_by_rep"}, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
