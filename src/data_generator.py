"""
src/data_generator.py
Simulates CMS Open Payments + Medicare Part D Prescriber data.

Calibrated to real published distributions:
  - CMS Open Payments 2022: $2.96B total, 12.7M records
  - Top payment categories: food/beverage, consulting, speaker fees
  - Real drug names, real company names (public knowledge)
  - Prescribing patterns correlated with payment receipt
"""

import numpy as np
import pandas as pd
import sqlite3
from pathlib import Path

# ── Real pharmaceutical companies (public knowledge) ─────────────────────
PHARMA_COMPANIES = {
    "AstraZeneca":        {"drugs": ["Farxiga", "Brilinta", "Symbicort"],       "annual_budget_M": 420},
    "Pfizer":             {"drugs": ["Eliquis", "Xeljanz", "Lyrica"],            "annual_budget_M": 680},
    "Johnson & Johnson":  {"drugs": ["Invega", "Xarelto", "Stelara"],            "annual_budget_M": 590},
    "Merck":              {"drugs": ["Januvia", "Keytruda", "Gardasil"],         "annual_budget_M": 510},
    "Bristol-Myers Squibb":{"drugs": ["Eliquis", "Opdivo", "Revlimid"],         "annual_budget_M": 460},
    "Novartis":           {"drugs": ["Entresto", "Cosentyx", "Zolgensma"],       "annual_budget_M": 390},
    "AbbVie":             {"drugs": ["Humira", "Rinvoq", "Imbruvica"],           "annual_budget_M": 720},
    "Eli Lilly":          {"drugs": ["Trulicity", "Taltz", "Verzenio"],          "annual_budget_M": 480},
    "Amgen":              {"drugs": ["Repatha", "Otezla", "Enbrel"],             "annual_budget_M": 350},
    "Boehringer Ingelheim":{"drugs": ["Jardiance", "Pradaxa", "Ofev"],           "annual_budget_M": 310},
}

# Payment categories with real CMS distribution weights + avg amounts
PAYMENT_CATEGORIES = {
    "Food and Beverage":        {"weight": 0.658, "avg_usd": 18,    "max_usd": 500},
    "Consulting Fee":           {"weight": 0.092, "avg_usd": 1850,  "max_usd": 50000},
    "Speaker Fee":              {"weight": 0.074, "avg_usd": 2400,  "max_usd": 75000},
    "Travel and Lodging":       {"weight": 0.068, "avg_usd": 320,   "max_usd": 8000},
    "Education":                {"weight": 0.042, "avg_usd": 580,   "max_usd": 15000},
    "Research":                 {"weight": 0.031, "avg_usd": 12000, "max_usd": 500000},
    "Grant":                    {"weight": 0.018, "avg_usd": 45000, "max_usd": 2000000},
    "Royalty or License":       {"weight": 0.009, "avg_usd": 8500,  "max_usd": 250000},
    "Gift":                     {"weight": 0.008, "avg_usd": 95,    "max_usd": 2000},
}

SPECIALTIES = {
    "Cardiology":              {"prescribe_affinity": 1.35, "weight": 0.09},
    "Internal Medicine":       {"prescribe_affinity": 1.10, "weight": 0.18},
    "Family Medicine":         {"prescribe_affinity": 1.05, "weight": 0.20},
    "Oncology":                {"prescribe_affinity": 1.45, "weight": 0.06},
    "Endocrinology":           {"prescribe_affinity": 1.40, "weight": 0.05},
    "Rheumatology":            {"prescribe_affinity": 1.50, "weight": 0.04},
    "Psychiatry":              {"prescribe_affinity": 1.20, "weight": 0.07},
    "Neurology":               {"prescribe_affinity": 1.25, "weight": 0.06},
    "Orthopedic Surgery":      {"prescribe_affinity": 1.15, "weight": 0.07},
    "General Surgery":         {"prescribe_affinity": 1.08, "weight": 0.08},
    "Dermatology":             {"prescribe_affinity": 1.30, "weight": 0.05},
    "Gastroenterology":        {"prescribe_affinity": 1.22, "weight": 0.05},
    "Pulmonology":             {"prescribe_affinity": 1.18, "weight": 0.04},
    "Emergency Medicine":      {"prescribe_affinity": 0.85, "weight": 0.06},
}

STATES = [
    "CA","TX","FL","NY","PA","IL","OH","GA","NC","MI",
    "NJ","VA","WA","AZ","MA","TN","IN","MO","MD","WI",
]


def generate(n_physicians: int = 3000, seed: int = 42) -> dict:
    rng = np.random.default_rng(seed)

    specialties   = list(SPECIALTIES.keys())
    spec_weights  = np.array([v["weight"] for v in SPECIALTIES.values()])
    spec_weights /= spec_weights.sum()

    companies     = list(PHARMA_COMPANIES.keys())
    cat_names     = list(PAYMENT_CATEGORIES.keys())
    cat_weights   = np.array([v["weight"] for v in PAYMENT_CATEGORIES.values()])
    cat_weights  /= cat_weights.sum()

    # ── 1. Physicians ─────────────────────────────────────────────────────
    first_names = ["James","Mary","John","Patricia","Robert","Jennifer","Michael",
                   "Linda","William","Barbara","David","Susan","Richard","Jessica",
                   "Joseph","Sarah","Thomas","Karen","Charles","Lisa","Wei","Priya",
                   "Ahmed","Fatima","Carlos","Elena","Raj","Anita","Kevin","Michelle"]
    last_names  = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller",
                   "Davis","Wilson","Martinez","Anderson","Taylor","Thomas","Hernandez",
                   "Moore","Jackson","Martin","Lee","Thompson","White","Patel","Kim",
                   "Nguyen","Chen","Wang","Singh","Murphy","O'Brien","Rodriguez","Clark"]

    phys_specs  = rng.choice(specialties, n_physicians, p=spec_weights)
    phys_states = rng.choice(STATES, n_physicians)

    physicians = pd.DataFrame({
        "physician_id":  [f"NPI{rng.integers(1000000000,9999999999):010d}" for _ in range(n_physicians)],
        "first_name":    rng.choice(first_names, n_physicians),
        "last_name":     rng.choice(last_names,  n_physicians),
        "specialty":     phys_specs,
        "state":         phys_states,
        "years_practice":np.clip(rng.integers(1, 40, n_physicians), 1, 40),
        "med_school_tier":rng.choice(["Top 20","Top 50","Other"], n_physicians, p=[0.12,0.28,0.60]),
    })
    physicians["physician_id"] = physicians["physician_id"].astype(str)

    # ── 2. Payments ───────────────────────────────────────────────────────
    # ~70% of physicians receive at least one payment
    paid_mask   = rng.random(n_physicians) < 0.70
    paid_ids    = physicians.loc[paid_mask, "physician_id"].values

    payment_records = []
    for pid in paid_ids:
        spec  = physicians.loc[physicians["physician_id"] == pid, "specialty"].values[0]
        affin = SPECIALTIES[spec]["prescribe_affinity"]

        # Number of payment transactions (power law — few get many)
        n_payments = max(1, int(rng.lognormal(1.2, 1.1)))
        n_payments = min(n_payments, 120)

        # Each physician is "owned" by 1-3 companies
        n_companies = rng.integers(1, 4)
        phys_companies = rng.choice(companies, min(n_companies, len(companies)), replace=False)

        for _ in range(n_payments):
            company    = rng.choice(phys_companies)
            drugs      = PHARMA_COMPANIES[company]["drugs"]
            drug       = rng.choice(drugs)
            category   = rng.choice(cat_names, p=cat_weights)
            cat_info   = PAYMENT_CATEGORIES[category]

            # Amount: log-normal around category average
            avg    = cat_info["avg_usd"]
            amount = rng.lognormal(np.log(avg), 0.8)
            amount = round(np.clip(amount, 1, cat_info["max_usd"]), 2)

            year = rng.choice([2019, 2020, 2021, 2022, 2023], p=[0.15,0.12,0.20,0.28,0.25])

            payment_records.append({
                "payment_id":   len(payment_records) + 1,
                "physician_id": pid,
                "company":      company,
                "drug_name":    drug,
                "category":     category,
                "amount_usd":   amount,
                "year":         year,
            })

    payments = pd.DataFrame(payment_records)

    # ── 3. Prescriptions (Medicare Part D style) ──────────────────────────
    all_drugs = sorted(set(
        d for c in PHARMA_COMPANIES.values() for d in c["drugs"]
    ))

    rx_records = []
    for _, phys in physicians.iterrows():
        pid   = phys["physician_id"]
        spec  = phys["specialty"]
        affin = SPECIALTIES[spec]["prescribe_affinity"]

        # Drugs this physician prescribes
        n_drugs = rng.integers(2, 8)
        chosen_drugs = rng.choice(all_drugs, min(n_drugs, len(all_drugs)), replace=False)

        # Did they receive payments from each drug's manufacturer?
        phys_payments = payments[payments["physician_id"] == pid]

        for drug in chosen_drugs:
            # Find which company makes this drug
            maker = next((c for c, v in PHARMA_COMPANIES.items() if drug in v["drugs"]), None)
            if maker is None:
                continue

            received_payment = (
                len(phys_payments[phys_payments["drug_name"] == drug]) > 0
            )
            total_paid = phys_payments[phys_payments["drug_name"] == drug]["amount_usd"].sum()

            # Prescribing volume: higher if received payment (the core hypothesis)
            base_claims = max(10, int(rng.lognormal(4.5, 0.9)))

            if received_payment:
                payment_multiplier = 1.0 + (np.log1p(total_paid) / 15) * affin
                claims = int(base_claims * payment_multiplier * rng.uniform(0.9, 1.1))
            else:
                claims = int(base_claims * rng.uniform(0.7, 1.1))

            claims = max(1, min(claims, 5000))
            avg_day_supply = int(rng.integers(20, 90))
            total_cost = round(claims * avg_day_supply * rng.uniform(1.5, 12.0), 2)

            for year in [2021, 2022, 2023]:
                rx_records.append({
                    "rx_id":              len(rx_records) + 1,
                    "physician_id":       pid,
                    "drug_name":          drug,
                    "manufacturer":       maker,
                    "year":               year,
                    "total_claims":       max(1, int(claims * rng.uniform(0.85, 1.15))),
                    "total_day_supply":   avg_day_supply * claims,
                    "total_drug_cost_usd":total_cost * rng.uniform(0.85, 1.15),
                    "received_payment":   int(received_payment),
                    "total_payment_usd":  round(total_paid, 2),
                })

    prescriptions = pd.DataFrame(rx_records)

    return {
        "physicians":   physicians,
        "payments":     payments,
        "prescriptions":prescriptions,
    }


def load_to_sqlite(tables: dict, db_path: str):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    for name, df in tables.items():
        df.to_sql(name, conn, if_exists="replace", index=False)
        print(f"  ✓ '{name}': {len(df):,} rows × {df.shape[1]} cols")
    conn.close()
    print(f"  ✓ DB saved → {db_path}")
