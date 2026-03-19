"""
src/charts.py
Investigative-quality charts — designed to tell the story clearly.
"""

import sqlite3
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import seaborn as sns
from pathlib import Path

P = {
    "red":     "#A32D2D",
    "teal":    "#1D9E75",
    "blue":    "#185FA5",
    "amber":   "#BA7517",
    "purple":  "#534AB7",
    "coral":   "#D85A30",
    "neutral": "#5F5E5A",
    "light":   "#F1EFE8",
    "mid":     "#B4B2A9",
}

BASE = {
    "figure.facecolor": "white",
    "axes.facecolor":   "#FAFAF8",
    "axes.spines.top":  False,
    "axes.spines.right":False,
    "axes.spines.left": False,
    "axes.grid":        True,
    "axes.grid.axis":   "x",
    "grid.color":       "#ECEAE4",
    "grid.linewidth":   0.6,
    "font.family":      "DejaVu Sans",
    "axes.titlesize":   13,
    "axes.titleweight": "bold",
    "axes.labelsize":   11,
    "xtick.labelsize":  9.5,
    "ytick.labelsize":  9.5,
    "xtick.bottom":     False,
    "ytick.left":       False,
}

def q(conn, sql): return pd.read_sql_query(sql, conn)
def save(fig, path):
    fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  ✓ {Path(path).name}")


def run_all(db_path, charts_dir, stats_results):
    Path(charts_dir).mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)

    # ── Chart 1: THE HEADLINE — paid vs unpaid prescribing ───────────────
    df1 = q(conn, """
        SELECT received_payment,
               ROUND(AVG(total_claims),1) avg_claims,
               COUNT(*) n,
               ROUND(AVG(total_drug_cost_usd),0) avg_cost
        FROM prescriptions GROUP BY received_payment
    """)

    with plt.rc_context(BASE):
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))

        labels  = ["No payment received", "Payment received"]
        colors  = [P["teal"], P["red"]]
        claims  = df1.sort_values("received_payment")["avg_claims"].values
        costs   = df1.sort_values("received_payment")["avg_cost"].values

        for ax, vals, ylabel, title in zip(
            axes,
            [claims, costs],
            ["Avg prescriptions per physician", "Avg drug cost (USD)"],
            ["Avg prescriptions: paid vs unpaid doctors",
             "Avg drug cost: paid vs unpaid doctors"]
        ):
            bars = ax.barh(labels, vals, color=colors, height=0.5)
            for bar, v in zip(bars, vals):
                ax.text(v + vals.max()*0.01, bar.get_y() + bar.get_height()/2,
                        f"{v:,.0f}", va="center", fontsize=10.5, fontweight="bold")
            ax.set_xlabel(ylabel)
            ax.set_title(title)
            lift = vals[1] - vals[0]
            pct  = lift / vals[0] * 100
            ax.annotate(f"+{pct:.0f}% lift",
                        xy=(vals[1], 1), xytext=(vals[0] + lift*0.5, 1.35),
                        fontsize=10, color=P["red"], fontweight="bold",
                        arrowprops=dict(arrowstyle="->", color=P["red"], lw=1.2))

        mw = stats_results["mann_whitney"]
        fig.suptitle(
            f"Doctors who receive pharma payments prescribe more of that drug\n"
            f"Median lift: +{mw['median_lift_pct']}%  |  Mann-Whitney p={mw['p_value']:.2e}  |  Effect r={mw['effect_size_r']}",
            fontsize=12, fontweight="bold", y=1.02
        )
        fig.tight_layout()
        save(fig, f"{charts_dir}/01_paid_vs_unpaid_headline.png")

    # ── Chart 2: Dose-response — payment amount vs prescriptions ─────────
    df2 = q(conn, """
        SELECT
            CASE WHEN total_payment_usd=0 THEN '1. None'
                 WHEN total_payment_usd<100 THEN '2. <$100'
                 WHEN total_payment_usd<500 THEN '3. $100-499'
                 WHEN total_payment_usd<2000 THEN '4. $500-1999'
                 WHEN total_payment_usd<10000 THEN '5. $2k-9.9k'
                 ELSE '6. $10k+' END AS band,
            ROUND(AVG(total_claims),1) avg_claims,
            COUNT(*) n
        FROM prescriptions GROUP BY band ORDER BY band
    """)

    with plt.rc_context({**BASE, "axes.grid.axis":"y"}):
        fig, ax = plt.subplots(figsize=(11, 5))
        baseline = df2.iloc[0]["avg_claims"]
        colors_  = [P["teal"]] + [P["coral"]] * 2 + [P["red"]] * 3
        bars = ax.bar(df2["band"], df2["avg_claims"], color=colors_, width=0.6)
        ax.axhline(baseline, color=P["neutral"], linestyle="--", lw=1.2,
                   label=f"No-payment baseline: {baseline:.0f} avg claims")
        for bar, val, n in zip(bars, df2["avg_claims"], df2["n"]):
            ax.text(bar.get_x()+bar.get_width()/2, val+2,
                    f"{val:.0f}", ha="center", fontsize=9.5, fontweight="bold")
            ax.text(bar.get_x()+bar.get_width()/2, val/2,
                    f"n={n:,}", ha="center", fontsize=8, color="white")

        sp = stats_results["spearman"]
        ax.set_xlabel("Total payment received from manufacturer")
        ax.set_ylabel("Avg prescription claims")
        ax.set_title(
            f"Dose-response: higher payments → more prescriptions\n"
            f"Spearman ρ = {sp['rho']}  |  p = {sp['p_value']:.2e}  |  [{sp['interpretation']} correlation]"
        )
        ax.legend(fontsize=9)
        fig.tight_layout()
        save(fig, f"{charts_dir}/02_dose_response.png")

    # ── Chart 3: Company spend vs prescribing lift ─────────────────────
    df3 = q(conn, """
        WITH company_paid AS (
            SELECT rx.manufacturer,
                ROUND(AVG(CASE WHEN rx.received_payment=1 THEN rx.total_claims END),1) avg_paid,
                ROUND(AVG(CASE WHEN rx.received_payment=0 THEN rx.total_claims END),1) avg_unpaid,
                ROUND(SUM(py.amount_usd)/1000000.0,2) spend_M
            FROM prescriptions rx
            LEFT JOIN payments py ON rx.physician_id=py.physician_id
                AND rx.manufacturer=py.company
            GROUP BY rx.manufacturer
        )
        SELECT *, ROUND(100.0*(avg_paid-avg_unpaid)/NULLIF(avg_unpaid,0),1) lift_pct
        FROM company_paid WHERE spend_M IS NOT NULL
        ORDER BY spend_M DESC
    """)

    with plt.rc_context({**BASE, "axes.grid": False}):
        fig, ax = plt.subplots(figsize=(11, 6))
        scatter = ax.scatter(
            df3["spend_M"], df3["lift_pct"],
            s=df3["spend_M"]*30, c=df3["lift_pct"],
            cmap="RdYlGn", vmin=-5, vmax=df3["lift_pct"].max(),
            alpha=0.8, edgecolors="white", linewidths=0.8, zorder=3
        )
        for _, row in df3.iterrows():
            ax.annotate(row["manufacturer"],
                        (row["spend_M"], row["lift_pct"]),
                        fontsize=8.5, color=P["neutral"],
                        xytext=(5,5), textcoords="offset points")
        ax.axhline(0, color=P["neutral"], linestyle="--", lw=1, alpha=0.6)
        plt.colorbar(scatter, ax=ax, label="Prescribing lift (%)", shrink=0.8)
        ax.set_xlabel("Total pharma spend (USD millions)")
        ax.set_ylabel("Prescribing lift: paid vs unpaid doctors (%)")
        ax.set_title("Company spend vs prescribing influence\nBubble size = total spend")
        ax.spines["left"].set_visible(True)
        ax.spines["bottom"].set_visible(True)
        fig.tight_layout()
        save(fig, f"{charts_dir}/03_company_spend_vs_lift.png")

    # ── Chart 4: Specialty targeting analysis ─────────────────────────────
    df4 = q(conn, """
        SELECT p.specialty,
               COUNT(DISTINCT p.physician_id) total_phys,
               COUNT(DISTINCT py.physician_id) paid_phys,
               ROUND(100.0*COUNT(DISTINCT py.physician_id)/COUNT(DISTINCT p.physician_id),1) pct_paid,
               ROUND(SUM(py.amount_usd)/1000.0,1) spend_K
        FROM physicians p
        LEFT JOIN payments py ON p.physician_id=py.physician_id
        GROUP BY p.specialty ORDER BY spend_K DESC LIMIT 12
    """)

    with plt.rc_context(BASE):
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.5))

        df4s = df4.sort_values("spend_K")
        bars = ax1.barh(df4s["specialty"], df4s["spend_K"],
                        color=[P["red"] if p > 70 else P["amber"] if p > 50 else P["teal"]
                               for p in df4s["pct_paid"]], height=0.6)
        for bar, v in zip(bars, df4s["spend_K"]):
            ax1.text(v+2, bar.get_y()+bar.get_height()/2,
                     f"${v:,.0f}K", va="center", fontsize=8.5)
        ax1.set_xlabel("Total pharma spend (USD thousands)")
        ax1.set_title("Total pharma spend by specialty")

        df4s2 = df4.sort_values("pct_paid")
        bars2 = ax2.barh(df4s2["specialty"], df4s2["pct_paid"],
                         color=[P["red"] if p > 70 else P["amber"] if p > 50 else P["teal"]
                                for p in df4s2["pct_paid"]], height=0.6)
        ax2.axvline(50, color=P["neutral"], linestyle="--", lw=1, label="50% threshold")
        for bar, v in zip(bars2, df4s2["pct_paid"]):
            ax2.text(v+0.5, bar.get_y()+bar.get_height()/2,
                     f"{v}%", va="center", fontsize=8.5)
        ax2.set_xlabel("% of physicians receiving payment")
        ax2.set_title("% of physicians targeted by pharma")
        ax2.legend(fontsize=9)

        fig.suptitle("Pharma targeting by medical specialty", fontsize=13, fontweight="bold")
        fig.tight_layout()
        save(fig, f"{charts_dir}/04_specialty_targeting.png")

    # ── Chart 5: Payment category breakdown ──────────────────────────────
    df5 = q(conn, """
        SELECT category,
               COUNT(*) n_payments,
               ROUND(SUM(amount_usd)/1000000.0,2) spend_M,
               ROUND(AVG(amount_usd),0) avg_amount,
               ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(),1) pct_volume
        FROM payments GROUP BY category ORDER BY spend_M DESC
    """)

    with plt.rc_context({**BASE, "axes.grid.axis": "x"}):
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 7))
        cat_colors = [P["red"] if c in ("Speaker Fee","Consulting Fee","Research","Grant")
                      else P["mid"] for c in df5["category"]]

        bars1 = ax1.barh(df5["category"], df5["spend_M"], color=cat_colors, height=0.6)
        for bar, v in zip(bars1, df5["spend_M"]):
            ax1.text(v+0.1, bar.get_y()+bar.get_height()/2,
                     f"${v:.2f}M", va="center", fontsize=9)
        ax1.set_xlabel("Total spend (USD millions)")
        ax1.set_title("Payment by category — total spend")

        bars2 = ax2.barh(df5["category"], df5["avg_amount"], color=cat_colors, height=0.6)
        for bar, v in zip(bars2, df5["avg_amount"]):
            ax2.text(v+10, bar.get_y()+bar.get_height()/2,
                     f"${v:,.0f}", va="center", fontsize=9)
        ax2.set_xlabel("Avg payment per transaction (USD)")
        ax2.set_title("Avg payment per transaction by category")

        red_p  = mpatches.Patch(color=P["red"],  label="High-influence categories")
        gray_p = mpatches.Patch(color=P["mid"],  label="Low-influence categories")
        fig.legend(handles=[red_p, gray_p], fontsize=9, loc="lower right")
        fig.suptitle("How pharma pays doctors — category breakdown", fontsize=13, fontweight="bold")
        fig.tight_layout()
        save(fig, f"{charts_dir}/05_payment_categories.png")

    # ── Chart 6: Year-over-year trend ────────────────────────────────────
    df6 = q(conn, """
        SELECT year,
               ROUND(SUM(amount_usd)/1000000.0,2) spend_M,
               COUNT(DISTINCT physician_id) physicians_paid,
               COUNT(*) transactions
        FROM payments GROUP BY year ORDER BY year
    """)

    with plt.rc_context({**BASE, "axes.grid": False}):
        fig, ax1 = plt.subplots(figsize=(10, 4.5))
        ax2 = ax1.twinx()

        ax1.bar(df6["year"], df6["spend_M"], color=P["blue"], alpha=0.7,
                width=0.5, label="Total spend ($M)")
        ax2.plot(df6["year"], df6["physicians_paid"], "o-",
                 color=P["red"], lw=2, markersize=7, label="Physicians paid")

        ax1.set_xlabel("Year")
        ax1.set_ylabel("Total pharma spend (USD millions)", color=P["blue"])
        ax2.set_ylabel("Number of physicians paid", color=P["red"])
        ax1.set_title("Pharma payments trend 2019–2023")
        ax1.spines["left"].set_visible(True)
        ax1.spines["bottom"].set_visible(True)

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc="upper left")
        fig.tight_layout()
        save(fig, f"{charts_dir}/06_yearly_trend.png")

    # ── Chart 7: Specialty effect sizes ──────────────────────────────────
    spec_df = stats_results["specialty_effects"].head(12).copy()

    with plt.rc_context(BASE):
        fig, ax = plt.subplots(figsize=(11, 5.5))
        spec_sorted = spec_df.sort_values("lift_pct")
        colors_ = [P["red"] if s else P["mid"] for s in spec_sorted["significant"]]
        bars = ax.barh(spec_sorted["specialty"], spec_sorted["lift_pct"],
                       color=colors_, height=0.6)
        ax.axvline(0, color=P["neutral"], lw=1)
        for bar, v, sig in zip(bars, spec_sorted["lift_pct"], spec_sorted["significant"]):
            label = f"+{v:.0f}% *" if sig else f"+{v:.0f}%"
            ax.text(v + 0.3, bar.get_y() + bar.get_height()/2,
                    label, va="center", fontsize=9,
                    color=P["red"] if sig else P["neutral"])

        red_p = mpatches.Patch(color=P["red"], label="Statistically significant (p<0.05)")
        gry_p = mpatches.Patch(color=P["mid"], label="Not significant")
        ax.legend(handles=[red_p, gry_p], fontsize=9)
        ax.set_xlabel("Prescribing lift: paid vs unpaid doctors (%)")
        ax.set_title("Prescribing lift by specialty\n* = statistically significant (Mann-Whitney, p<0.05)")
        fig.tight_layout()
        save(fig, f"{charts_dir}/07_specialty_lift.png")

    conn.close()
