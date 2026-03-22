
-- 7. Payment tier dose-response
SELECT payment_tier,
    COUNT(DISTINCT doctor_id)     AS doctors,
    ROUND(AVG(total_prescriptions), 0) AS avg_prescriptions,
    ROUND(AVG(total_payments), 0)      AS avg_payment_usd
FROM pharma_summary
GROUP BY payment_tier
ORDER BY avg_payment_usd;

-- 8. Top 10 highest-paid doctors and their prescription volumes
SELECT doctor_id, specialty, state,
    total_payments,
    total_prescriptions,
    RANK() OVER (ORDER BY total_payments DESC) AS payment_rank
FROM pharma_summary
ORDER BY total_payments DESC LIMIT 10;
