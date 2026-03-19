"""
run_analysis.py — Pharma Payments "Follow the Money" pipeline
"""

import sys, os, sqlite3, json
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
from src.data_generator  import generate, load_to_sqlite
from src.stats_analysis  import run_all as run_stats
from src.charts          import run_all as run_charts

DB      = "data/pharma_payments.db"
CHARTS  = "outputs/charts"
EXCEL   = "outputs/excel"

os.makedirs(CHARTS, exist_ok=True)
os.makedirs(EXCEL,  exist_ok=True)
os.makedirs("data/raw", exist_ok=True)
os.makedirs("data/processed", exist_ok=True)
os.makedirs("outputs/report", exist_ok=True)

print("=" * 62)
print("  FOLLOW THE MONEY — PHARMA PAYMENTS ANALYSIS")
print("=" * 62)

# ── 1. Generate data ──────────────────────────────────────────────────────
print("\n[1/5] Generating dataset...")
tables = generate(n_physicians=3000, seed=42)
for name, df in tables.items():
    df.to_csv(f"data/raw/{name}.csv", index=False)
load_to_sqlite(tables, DB)

# ── 2. Create views ───────────────────────────────────────────────────────
print("\n[2/5] Creating SQL views...")
conn = sqlite3.connect(DB)
with open("sql/views/02_create_views.sql") as f:
    conn.executescript(f.read())
conn.commit()
views = conn.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall()
for (v,) in views:
    print(f"  ✓ View: {v}")
conn.close()

# ── 3. Statistical analysis ───────────────────────────────────────────────
print("\n[3/5] Running statistical analysis...")
stats_results = run_stats(DB)

# ── 4. Charts ─────────────────────────────────────────────────────────────
print("\n[4/5] Generating charts...")
run_charts(DB, CHARTS, stats_results)

# ── 5. Excel workbook ─────────────────────────────────────────────────────
print("\n[5/5] Building Excel workbook...")
conn = sqlite3.connect(DB)

sheets = {
    "Key Findings": pd.DataFrame([{
        "Finding": "Paid doctors prescribe more",
        "Metric":  "Median prescribing lift",
        "Value":   f"+{stats_results['mann_whitney']['median_lift_pct']}%",
        "p-value": stats_results["mann_whitney"]["p_value"],
        "Significant": stats_results["mann_whitney"]["significant"],
    },{
        "Finding": "Dose-response confirmed",
        "Metric":  "Spearman correlation (payment $ vs Rx volume)",
        "Value":   stats_results["spearman"]["rho"],
        "p-value": stats_results["spearman"]["p_value"],
        "Significant": stats_results["spearman"]["significant"],
    }]),
    "Company Influence": pd.read_sql("""
        WITH c AS (
            SELECT rx.manufacturer,
                COUNT(DISTINCT CASE WHEN rx.received_payment=1 THEN rx.physician_id END) paid_physicians,
                ROUND(AVG(CASE WHEN rx.received_payment=1 THEN rx.total_claims END),1) avg_claims_paid,
                ROUND(AVG(CASE WHEN rx.received_payment=0 THEN rx.total_claims END),1) avg_claims_unpaid,
                ROUND(SUM(py.amount_usd),0) total_spend_usd
            FROM prescriptions rx
            LEFT JOIN payments py ON rx.physician_id=py.physician_id AND rx.manufacturer=py.company
            GROUP BY rx.manufacturer
        )
        SELECT *, ROUND(100.0*(avg_claims_paid-avg_claims_unpaid)/NULLIF(avg_claims_unpaid,0),1) lift_pct
        FROM c ORDER BY total_spend_usd DESC
    """, conn),
    "Payment Categories": pd.read_sql("""
        SELECT category,
               COUNT(*) n_payments,
               ROUND(SUM(amount_usd),0) total_usd,
               ROUND(AVG(amount_usd),2) avg_usd,
               ROUND(100.0*COUNT(*)/SUM(COUNT(*)) OVER(),1) pct_volume
        FROM payments GROUP BY category ORDER BY total_usd DESC
    """, conn),
    "Specialty Analysis": pd.read_sql("""
        SELECT p.specialty,
               COUNT(DISTINCT p.physician_id) total_physicians,
               COUNT(DISTINCT py.physician_id) paid_physicians,
               ROUND(100.0*COUNT(DISTINCT py.physician_id)/COUNT(DISTINCT p.physician_id),1) pct_receiving_payment,
               ROUND(SUM(py.amount_usd),0) total_spend_usd,
               ROUND(AVG(py.amount_usd),2) avg_payment_usd
        FROM physicians p LEFT JOIN payments py ON p.physician_id=py.physician_id
        GROUP BY p.specialty ORDER BY total_spend_usd DESC
    """, conn),
    "YoY Trend": pd.read_sql("""
        SELECT year,
               COUNT(DISTINCT physician_id) physicians_paid,
               COUNT(*) transactions,
               ROUND(SUM(amount_usd),0) total_spend_usd,
               ROUND(AVG(amount_usd),2) avg_payment_usd
        FROM payments GROUP BY year ORDER BY year
    """, conn),
    "Top Paid Physicians": pd.read_sql("""
        SELECT p.first_name||' '||p.last_name physician_name,
               p.specialty, p.state,
               ROUND(SUM(py.amount_usd),0) total_received_usd,
               COUNT(py.payment_id) n_payments,
               COUNT(DISTINCT py.company) n_companies
        FROM physicians p JOIN payments py ON p.physician_id=py.physician_id
        GROUP BY p.physician_id ORDER BY total_received_usd DESC LIMIT 50
    """, conn),
}

excel_path = f"{EXCEL}/pharma_payments_analysis.xlsx"
with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
    for name, df in sheets.items():
        df.to_excel(writer, sheet_name=name, index=False)
        ws = writer.sheets[name]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col) + 3
            ws.column_dimensions[col[0].column_letter].width = min(max_len, 40)

conn.close()
print(f"  ✓ Excel → {excel_path}  ({len(sheets)} sheets)")

# ── Summary ───────────────────────────────────────────────────────────────
mw = stats_results["mann_whitney"]
sp = stats_results["spearman"]
print("\n" + "=" * 62)
print("  PIPELINE COMPLETE")
print("=" * 62)
print(f"  Physicians analyzed  : {len(tables['physicians']):,}")
print(f"  Payment records      : {len(tables['payments']):,}")
print(f"  Prescription records : {len(tables['prescriptions']):,}")
print(f"  Prescribing lift     : +{mw['median_lift_pct']}%  (p={mw['p_value']:.2e})")
print(f"  Dose-response rho    : {sp['rho']}  (p={sp['p_value']:.2e})")
print(f"  Charts saved         : {CHARTS}/  (7 files)")
print(f"  Excel workbook       : {excel_path}")
