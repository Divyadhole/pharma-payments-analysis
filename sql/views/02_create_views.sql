-- ============================================================
-- sql/views/02_create_views.sql
-- Reusable analytical views across all analyses
-- ============================================================

-- ── View 1: Full physician payment + prescribing profile ──────────────────
CREATE VIEW IF NOT EXISTS vw_physician_summary AS
SELECT
    p.physician_id,
    p.first_name || ' ' || p.last_name          AS physician_name,
    p.specialty,
    p.state,
    p.years_practice,
    p.med_school_tier,

    -- Payment metrics
    COUNT(DISTINCT py.payment_id)                AS total_payment_transactions,
    COUNT(DISTINCT py.company)                   AS distinct_companies_paid,
    ROUND(SUM(py.amount_usd), 2)                 AS total_payments_usd,
    ROUND(AVG(py.amount_usd), 2)                 AS avg_payment_usd,
    MAX(py.amount_usd)                           AS largest_single_payment_usd,
    COUNT(DISTINCT py.drug_name)                 AS drugs_promoted_to,

    -- Prescribing metrics
    SUM(rx.total_claims)                         AS total_rx_claims,
    ROUND(AVG(rx.total_claims), 1)               AS avg_claims_per_drug,
    ROUND(SUM(rx.total_drug_cost_usd), 2)        AS total_rx_cost_usd,

    -- Key flag
    CASE WHEN SUM(py.amount_usd) > 0
         THEN 1 ELSE 0 END                       AS received_any_payment

FROM physicians p
LEFT JOIN payments     py ON p.physician_id = py.physician_id
LEFT JOIN prescriptions rx ON p.physician_id = rx.physician_id
GROUP BY p.physician_id, p.first_name, p.last_name,
         p.specialty, p.state, p.years_practice, p.med_school_tier;


-- ── View 2: Drug-level payment vs prescribing comparison ─────────────────
CREATE VIEW IF NOT EXISTS vw_drug_payment_prescribe AS
SELECT
    rx.drug_name,
    rx.manufacturer,
    rx.year,
    rx.received_payment,
    COUNT(DISTINCT rx.physician_id)              AS physician_count,
    SUM(rx.total_claims)                         AS total_claims,
    ROUND(AVG(rx.total_claims), 1)               AS avg_claims_per_physician,
    ROUND(AVG(rx.total_drug_cost_usd), 2)        AS avg_rx_cost_usd,
    ROUND(SUM(rx.total_payment_usd), 2)          AS total_payments_received,
    ROUND(AVG(rx.total_payment_usd), 2)          AS avg_payment_per_physician
FROM prescriptions rx
GROUP BY rx.drug_name, rx.manufacturer, rx.year, rx.received_payment;


-- ── View 3: Company-level influence scorecard ─────────────────────────────
CREATE VIEW IF NOT EXISTS vw_company_influence AS
SELECT
    py.company,
    py.year,
    COUNT(DISTINCT py.physician_id)              AS physicians_paid,
    COUNT(py.payment_id)                         AS total_transactions,
    ROUND(SUM(py.amount_usd), 2)                 AS total_spend_usd,
    ROUND(AVG(py.amount_usd), 2)                 AS avg_payment_usd,
    ROUND(MAX(py.amount_usd), 2)                 AS largest_payment_usd,
    COUNT(DISTINCT py.drug_name)                 AS drugs_promoted,
    -- Spend by category (conditional aggregation)
    ROUND(SUM(CASE WHEN py.category = 'Speaker Fee'
                   THEN py.amount_usd ELSE 0 END), 2) AS speaker_fee_spend_usd,
    ROUND(SUM(CASE WHEN py.category = 'Consulting Fee'
                   THEN py.amount_usd ELSE 0 END), 2) AS consulting_spend_usd,
    ROUND(SUM(CASE WHEN py.category = 'Food and Beverage'
                   THEN py.amount_usd ELSE 0 END), 2) AS food_bev_spend_usd,
    ROUND(SUM(CASE WHEN py.category = 'Research'
                   THEN py.amount_usd ELSE 0 END), 2) AS research_spend_usd
FROM payments py
GROUP BY py.company, py.year;
