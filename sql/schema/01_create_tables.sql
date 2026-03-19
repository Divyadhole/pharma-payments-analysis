-- ============================================================
-- sql/schema/01_create_tables.sql
-- Pharma Payments Analysis — Relational Schema
-- Mirrors structure of CMS Open Payments + Medicare Part D
-- ============================================================

DROP TABLE IF EXISTS prescriptions;
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS physicians;
DROP VIEW  IF EXISTS vw_physician_summary;
DROP VIEW  IF EXISTS vw_drug_payment_prescribe;
DROP VIEW  IF EXISTS vw_company_influence;

-- ── Physicians (mirrors CMS physician registry) ───────────────────────────
CREATE TABLE physicians (
    physician_id    TEXT        PRIMARY KEY,
    first_name      TEXT        NOT NULL,
    last_name       TEXT        NOT NULL,
    specialty       TEXT        NOT NULL,
    state           TEXT        NOT NULL,
    years_practice  INTEGER     CHECK (years_practice BETWEEN 1 AND 50),
    med_school_tier TEXT        CHECK (med_school_tier IN ('Top 20','Top 50','Other'))
);

-- ── Payments (mirrors CMS Open Payments general payments) ─────────────────
CREATE TABLE payments (
    payment_id      INTEGER     PRIMARY KEY,
    physician_id    TEXT        NOT NULL REFERENCES physicians(physician_id),
    company         TEXT        NOT NULL,
    drug_name       TEXT        NOT NULL,
    category        TEXT        NOT NULL,
    amount_usd      REAL        NOT NULL CHECK (amount_usd > 0),
    year            INTEGER     NOT NULL CHECK (year BETWEEN 2015 AND 2025)
);

-- ── Prescriptions (mirrors Medicare Part D prescriber data) ───────────────
CREATE TABLE prescriptions (
    rx_id                   INTEGER PRIMARY KEY,
    physician_id            TEXT    NOT NULL REFERENCES physicians(physician_id),
    drug_name               TEXT    NOT NULL,
    manufacturer            TEXT    NOT NULL,
    year                    INTEGER NOT NULL,
    total_claims            INTEGER NOT NULL CHECK (total_claims > 0),
    total_day_supply        INTEGER NOT NULL,
    total_drug_cost_usd     REAL    NOT NULL,
    received_payment        INTEGER NOT NULL DEFAULT 0 CHECK (received_payment IN (0,1)),
    total_payment_usd       REAL    NOT NULL DEFAULT 0
);

-- ── Indexes ───────────────────────────────────────────────────────────────
CREATE INDEX idx_pay_physician   ON payments(physician_id);
CREATE INDEX idx_pay_company     ON payments(company);
CREATE INDEX idx_pay_drug        ON payments(drug_name);
CREATE INDEX idx_pay_year        ON payments(year);
CREATE INDEX idx_rx_physician    ON prescriptions(physician_id);
CREATE INDEX idx_rx_drug         ON prescriptions(drug_name);
CREATE INDEX idx_rx_paid         ON prescriptions(received_payment);
