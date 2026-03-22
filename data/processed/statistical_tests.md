# Statistical Tests — Pharma Payments Analysis

## Primary Test: Mann-Whitney U
- **H0:** No difference in prescriptions between paid and unpaid doctors
- **H1:** Paid doctors prescribe more
- **Result:** p < 0.001 — reject H0
- **Effect size:** +64.1% more prescriptions in paid group

## Correlation Test: Spearman's Rank
- **Variables:** Payment amount vs prescription volume
- **Spearman ρ:** 0.134
- **p-value:** < 0.001
- **Interpretation:** Weak but statistically significant positive correlation

## Dose-Response: Payment Tier Analysis
| Payment Tier | Avg Prescriptions | vs Unpaid |
|---|---|---|
| No payment | baseline | — |
| $1 - $999 | +22% | +22% |
| $1,000 - $9,999 | +41% | +41% |
| $10,000+ | +170% | +170% (2.7x) |

## Confounders Acknowledged
- Specialty type (cardiologists prescribe more in general)
- Practice size and patient volume
- Geographic market differences
- Causality cannot be established from correlation alone
