"""
src/stats_analysis.py
Statistical tests validating the core hypothesis:
  H0: No difference in prescribing between paid and unpaid physicians
  H1: Paid physicians prescribe significantly more of the promoted drug
"""

import numpy as np
import pandas as pd
from scipy import stats
import sqlite3


def run_all(db_path: str) -> dict:
    conn = sqlite3.connect(db_path)

    rx = pd.read_sql("SELECT * FROM prescriptions", conn)
    py = pd.read_sql("SELECT * FROM payments", conn)
    ph = pd.read_sql("SELECT * FROM physicians", conn)
    conn.close()

    results = {}

    # ── 1. Mann-Whitney U test (non-parametric — claims are skewed) ───────
    paid   = rx[rx["received_payment"] == 1]["total_claims"]
    unpaid = rx[rx["received_payment"] == 0]["total_claims"]

    stat, p = stats.mannwhitneyu(paid, unpaid, alternative="greater")
    r = 1 - (2 * stat) / (len(paid) * len(unpaid))   # rank-biserial correlation

    results["mann_whitney"] = {
        "test":              "Mann-Whitney U (one-sided)",
        "hypothesis":        "Paid physicians prescribe MORE than unpaid",
        "paid_median":       round(paid.median(), 1),
        "unpaid_median":     round(unpaid.median(), 1),
        "median_lift":       round(paid.median() - unpaid.median(), 1),
        "median_lift_pct":   round((paid.median() / unpaid.median() - 1) * 100, 1),
        "u_statistic":       round(stat, 2),
        "p_value":           round(p, 8),
        "effect_size_r":     round(r, 4),
        "significant":       p < 0.05,
        "interpretation":    _interpret_r(r),
    }

    # ── 2. Spearman correlation: payment amount vs prescribing volume ─────
    paid_rx = rx[rx["received_payment"] == 1].copy()
    rho, p2 = stats.spearmanr(paid_rx["total_payment_usd"], paid_rx["total_claims"])

    results["spearman"] = {
        "test":          "Spearman rank correlation",
        "hypothesis":    "Higher payment → more prescriptions (dose-response)",
        "rho":           round(rho, 4),
        "p_value":       round(p2, 8),
        "significant":   p2 < 0.05,
        "interpretation":_interpret_rho(rho),
    }

    # ── 3. Kruskal-Wallis across payment bands ────────────────────────────
    paid_rx["band"] = pd.cut(
        paid_rx["total_payment_usd"],
        bins=[0, 100, 500, 2000, 10000, np.inf],
        labels=["<$100","$100-499","$500-1999","$2000-9999","$10000+"]
    )
    groups = [g["total_claims"].values for _, g in paid_rx.groupby("band", observed=True)]
    h, p3  = stats.kruskal(*groups)

    results["kruskal_wallis"] = {
        "test":          "Kruskal-Wallis H (payment bands)",
        "h_statistic":   round(h, 3),
        "p_value":       round(p3, 8),
        "significant":   p3 < 0.05,
        "n_groups":      len(groups),
    }

    # ── 4. Effect size summary per specialty ──────────────────────────────
    merged = rx.merge(ph[["physician_id","specialty"]], on="physician_id")
    specialty_effects = []
    for spec, grp in merged.groupby("specialty"):
        p_  = grp[grp["received_payment"] == 1]["total_claims"]
        u_  = grp[grp["received_payment"] == 0]["total_claims"]
        if len(p_) < 5 or len(u_) < 5:
            continue
        _, pv = stats.mannwhitneyu(p_, u_, alternative="greater")
        lift  = p_.median() - u_.median()
        specialty_effects.append({
            "specialty":       spec,
            "paid_n":          len(p_),
            "unpaid_n":        len(u_),
            "paid_median":     round(p_.median(), 1),
            "unpaid_median":   round(u_.median(), 1),
            "median_lift":     round(lift, 1),
            "lift_pct":        round(lift / u_.median() * 100, 1) if u_.median() > 0 else 0,
            "p_value":         round(pv, 5),
            "significant":     pv < 0.05,
        })

    results["specialty_effects"] = pd.DataFrame(specialty_effects)\
                                     .sort_values("lift_pct", ascending=False)

    # ── 5. Company-level payment ROI proxy ────────────────────────────────
    company_rx = rx.groupby(["manufacturer","received_payment"])["total_claims"].median().unstack()
    company_rx.columns = ["unpaid_median","paid_median"]
    company_py = py.groupby("company")["amount_usd"].sum().rename("total_spend")
    company_df = company_rx.join(company_py, how="left")
    company_df["lift"]       = company_df["paid_median"] - company_df["unpaid_median"]
    company_df["lift_pct"]   = (company_df["lift"] / company_df["unpaid_median"] * 100).round(1)
    company_df["spend_per_lift"] = (company_df["total_spend"] / company_df["lift"]).round(0)
    results["company_roi"] = company_df.reset_index().rename(columns={"manufacturer":"company"})

    # Print summary
    mw = results["mann_whitney"]
    sp = results["spearman"]
    print(f"\n  Mann-Whitney U: paid median={mw['paid_median']} vs unpaid={mw['unpaid_median']}")
    print(f"    Lift: +{mw['median_lift']} claims (+{mw['median_lift_pct']}%)")
    print(f"    p={mw['p_value']}  effect r={mw['effect_size_r']}  [{mw['interpretation']}]")
    print(f"\n  Spearman ρ={sp['rho']}  p={sp['p_value']}  [{sp['interpretation']}]")
    print(f"    → {'DOSE-RESPONSE CONFIRMED' if sp['significant'] else 'Not significant'}")

    return results


def _interpret_r(r):
    a = abs(r)
    if a < 0.1: return "negligible"
    if a < 0.3: return "small"
    if a < 0.5: return "medium"
    return "large"

def _interpret_rho(r):
    a = abs(r)
    if a < 0.1: return "negligible"
    if a < 0.3: return "weak"
    if a < 0.5: return "moderate"
    return "strong"
