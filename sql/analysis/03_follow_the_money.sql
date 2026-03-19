-- ============================================================
-- sql/analysis/03_follow_the_money.sql
-- "Follow the Money" — Investigative Pharma Payment Analysis
--
-- Central question: Do doctors who receive pharma payments
-- prescribe significantly more of that company's drugs?
--
-- Techniques: CTEs, window functions, self-joins,
-- conditional aggregation, percentile ranking, ratio analysis
-- ============================================================


-- ════════════════════════════════════════════════════════════
-- SECTION 1: THE CORE FINDING
-- Paid vs unpaid doctors — prescribing volume comparison
-- ════════════════════════════════════════════════════════════

-- 1A. The headline number: paid vs unpaid prescribing gap
SELECT
    received_payment,
    CASE received_payment WHEN 1 THEN 'Received Payment' ELSE 'No Payment' END
                                                AS payment_status,
    COUNT(DISTINCT physician_id)               AS physician_count,
    SUM(total_claims)                          AS total_claims,
    ROUND(AVG(total_claims), 1)                AS avg_claims_per_physician,
    ROUND(AVG(total_drug_cost_usd), 2)         AS avg_rx_cost_usd,
    ROUND(AVG(total_payment_usd), 2)           AS avg_payment_received_usd
FROM prescriptions
GROUP BY received_payment
ORDER BY received_payment DESC;


-- 1B. Payment amount buckets vs prescribing volume
--     The dose-response relationship: more money = more prescriptions?
WITH payment_buckets AS (
    SELECT
        physician_id,
        drug_name,
        total_claims,
        total_payment_usd,
        CASE
            WHEN total_payment_usd = 0          THEN '1. No payment'
            WHEN total_payment_usd < 100        THEN '2. Under $100'
            WHEN total_payment_usd < 500        THEN '3. $100–$499'
            WHEN total_payment_usd < 2000       THEN '4. $500–$1,999'
            WHEN total_payment_usd < 10000      THEN '5. $2,000–$9,999'
            ELSE                                     '6. $10,000+'
        END AS payment_band
    FROM prescriptions
)
SELECT
    payment_band,
    COUNT(*)                                    AS records,
    COUNT(DISTINCT physician_id)               AS physician_count,
    ROUND(AVG(total_claims), 1)                AS avg_claims,
    ROUND(AVG(total_claims) / (
        SELECT AVG(total_claims)
        FROM payment_buckets WHERE payment_band = '1. No payment'
    ), 2)                                       AS claims_ratio_vs_unpaid,
    ROUND(AVG(total_payment_usd), 2)           AS avg_payment_usd
FROM payment_buckets
GROUP BY payment_band
ORDER BY payment_band;


-- ════════════════════════════════════════════════════════════
-- SECTION 2: COMPANY-LEVEL INFLUENCE ANALYSIS
-- Which companies spend the most, and does it work?
-- ════════════════════════════════════════════════════════════

-- 2A. Company spend vs prescribing lift
WITH company_paid AS (
    SELECT
        rx.manufacturer,
        COUNT(DISTINCT CASE WHEN rx.received_payment = 1 THEN rx.physician_id END)
                                                AS paid_physicians,
        ROUND(AVG(CASE WHEN rx.received_payment = 1 THEN rx.total_claims END), 1)
                                                AS avg_claims_paid,
        ROUND(AVG(CASE WHEN rx.received_payment = 0 THEN rx.total_claims END), 1)
                                                AS avg_claims_unpaid,
        ROUND(SUM(py.amount_usd), 0)           AS total_spend_usd,
        COUNT(DISTINCT py.payment_id)          AS payment_transactions
    FROM prescriptions rx
    LEFT JOIN payments py
        ON rx.physician_id = py.physician_id
        AND rx.manufacturer = py.company
    GROUP BY rx.manufacturer
)
SELECT
    manufacturer,
    paid_physicians,
    avg_claims_paid,
    avg_claims_unpaid,
    ROUND(avg_claims_paid - avg_claims_unpaid, 1)
                                                AS prescribing_lift,
    ROUND(100.0 * (avg_claims_paid - avg_claims_unpaid)
          / NULLIF(avg_claims_unpaid, 0), 1)   AS lift_pct,
    total_spend_usd,
    payment_transactions,
    RANK() OVER (ORDER BY total_spend_usd DESC) AS spend_rank,
    RANK() OVER (ORDER BY
        ROUND(100.0 * (avg_claims_paid - avg_claims_unpaid)
              / NULLIF(avg_claims_unpaid, 0), 1) DESC
    )                                           AS lift_rank
FROM company_paid
ORDER BY total_spend_usd DESC;


-- ════════════════════════════════════════════════════════════
-- SECTION 3: SPECIALTY ANALYSIS
-- Which specialties are most targeted and most influenced?
-- ════════════════════════════════════════════════════════════

-- 3A. Payment targeting by specialty
SELECT
    p.specialty,
    COUNT(DISTINCT p.physician_id)              AS total_physicians,
    COUNT(DISTINCT py.physician_id)             AS paid_physicians,
    ROUND(100.0 * COUNT(DISTINCT py.physician_id)
          / COUNT(DISTINCT p.physician_id), 1) AS pct_receiving_payment,
    ROUND(AVG(py.amount_usd), 2)               AS avg_payment_usd,
    ROUND(SUM(py.amount_usd), 0)               AS total_spend_usd,
    ROUND(AVG(CASE WHEN rx.received_payment = 1 THEN rx.total_claims END), 1)
                                                AS avg_claims_if_paid,
    ROUND(AVG(CASE WHEN rx.received_payment = 0 THEN rx.total_claims END), 1)
                                                AS avg_claims_if_unpaid,
    RANK() OVER (ORDER BY SUM(py.amount_usd) DESC) AS spend_rank
FROM physicians p
LEFT JOIN payments      py ON p.physician_id = py.physician_id
LEFT JOIN prescriptions rx ON p.physician_id = rx.physician_id
GROUP BY p.specialty
ORDER BY total_spend_usd DESC;


-- ════════════════════════════════════════════════════════════
-- SECTION 4: HIGH-VALUE PAYMENT DEEP DIVE
-- The top earners — who are they and what do they prescribe?
-- ════════════════════════════════════════════════════════════

-- 4A. Top 25 highest-paid physicians with prescribing profile
WITH physician_totals AS (
    SELECT
        py.physician_id,
        SUM(py.amount_usd)                      AS total_received_usd,
        COUNT(py.payment_id)                    AS n_payments,
        COUNT(DISTINCT py.company)              AS n_companies,
        COUNT(DISTINCT py.drug_name)            AS n_drugs_promoted,
        GROUP_CONCAT(DISTINCT py.company)       AS companies,
        MAX(py.category)                        AS top_category
    FROM payments py
    GROUP BY py.physician_id
),
prescribe_totals AS (
    SELECT
        physician_id,
        SUM(total_claims)                       AS total_rx_claims,
        ROUND(AVG(total_claims), 1)             AS avg_claims_per_drug
    FROM prescriptions
    WHERE received_payment = 1
    GROUP BY physician_id
)
SELECT
    pt.physician_id,
    p.first_name || ' ' || p.last_name          AS physician_name,
    p.specialty,
    p.state,
    ROUND(pt.total_received_usd, 2)             AS total_payments_usd,
    pt.n_payments,
    pt.n_companies,
    pt.n_drugs_promoted,
    pt.companies,
    COALESCE(rx.total_rx_claims, 0)             AS total_rx_claims,
    COALESCE(rx.avg_claims_per_drug, 0)         AS avg_claims_per_drug,
    NTILE(100) OVER (ORDER BY pt.total_received_usd DESC) AS payment_percentile
FROM physician_totals pt
JOIN physicians p ON pt.physician_id = p.physician_id
LEFT JOIN prescribe_totals rx ON pt.physician_id = rx.physician_id
ORDER BY pt.total_received_usd DESC
LIMIT 25;


-- ════════════════════════════════════════════════════════════
-- SECTION 5: PAYMENT CATEGORY BREAKDOWN
-- Speaker fees vs food/beverage — which category drives more prescribing?
-- ════════════════════════════════════════════════════════════

-- 5A. Category influence analysis
WITH category_rx AS (
    SELECT
        py.category,
        py.physician_id,
        ROUND(SUM(py.amount_usd), 2)            AS cat_payment_total,
        COUNT(py.payment_id)                    AS n_payments
    FROM payments py
    GROUP BY py.category, py.physician_id
),
joined AS (
    SELECT
        cr.category,
        cr.cat_payment_total,
        COALESCE(SUM(rx.total_claims), 0)       AS total_rx_claims,
        COALESCE(AVG(rx.total_claims), 0)       AS avg_rx_claims
    FROM category_rx cr
    LEFT JOIN prescriptions rx ON cr.physician_id = rx.physician_id
                               AND rx.received_payment = 1
    GROUP BY cr.category, cr.cat_payment_total
)
SELECT
    category,
    COUNT(*)                                    AS physician_category_pairs,
    ROUND(AVG(cat_payment_total), 2)            AS avg_payment_usd,
    ROUND(SUM(cat_payment_total), 0)            AS total_category_spend_usd,
    ROUND(AVG(avg_rx_claims), 1)                AS avg_rx_claims,
    RANK() OVER (ORDER BY AVG(avg_rx_claims) DESC) AS influence_rank
FROM joined
GROUP BY category
ORDER BY avg_payment_usd DESC;


-- ════════════════════════════════════════════════════════════
-- SECTION 6: YEAR-OVER-YEAR TREND
-- How did pharma spending change 2019–2023?
-- ════════════════════════════════════════════════════════════

WITH yearly AS (
    SELECT
        year,
        COUNT(DISTINCT physician_id)            AS physicians_paid,
        COUNT(payment_id)                       AS transactions,
        ROUND(SUM(amount_usd), 0)               AS total_spend_usd,
        ROUND(AVG(amount_usd), 2)               AS avg_payment_usd
    FROM payments
    GROUP BY year
)
SELECT
    year,
    physicians_paid,
    transactions,
    total_spend_usd,
    avg_payment_usd,
    total_spend_usd - LAG(total_spend_usd) OVER (ORDER BY year)
                                                AS yoy_change_usd,
    ROUND(100.0 * (total_spend_usd - LAG(total_spend_usd) OVER (ORDER BY year))
          / NULLIF(LAG(total_spend_usd) OVER (ORDER BY year), 0), 1)
                                                AS yoy_change_pct
FROM yearly
ORDER BY year;


-- ════════════════════════════════════════════════════════════
-- SECTION 7: STATE-LEVEL GEOGRAPHIC ANALYSIS
-- ════════════════════════════════════════════════════════════

SELECT
    p.state,
    COUNT(DISTINCT p.physician_id)              AS total_physicians,
    COUNT(DISTINCT py.physician_id)             AS paid_physicians,
    ROUND(100.0 * COUNT(DISTINCT py.physician_id)
          / COUNT(DISTINCT p.physician_id), 1) AS pct_paid,
    ROUND(SUM(py.amount_usd), 0)               AS total_spend_usd,
    ROUND(AVG(py.amount_usd), 2)               AS avg_payment_usd,
    ROUND(SUM(py.amount_usd)
          / NULLIF(COUNT(DISTINCT p.physician_id), 0), 2)
                                                AS spend_per_physician,
    RANK() OVER (ORDER BY SUM(py.amount_usd) DESC) AS state_rank
FROM physicians p
LEFT JOIN payments py ON p.physician_id = py.physician_id
GROUP BY p.state
ORDER BY total_spend_usd DESC;
