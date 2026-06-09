WITH months AS (
    SELECT CAST(date_trunc('month', CAST(d AS TIMESTAMP)) AS DATE) as report_month
    FROM (SELECT unnest(generate_series(current_date - INTERVAL '2 years', current_date, INTERVAL '1 month')) as d)
),
domain_metrics AS (
    SELECT 
        dg.customer_id,
        d.dw_valid_from,
        d.full_subpage_count,
        CASE 
            WHEN d.full_subpage_count < 10 THEN 'S'
            WHEN d.full_subpage_count < 100 THEN 'M'
            ELSE 'L'
        END as package_size
    FROM {{ ref('stg_domain') }} d
    JOIN {{ ref('stg_domain_group') }} dg ON d.domain_group_id = dg.domain_group_id
)

SELECT 
    m.report_month,
    dm.customer_id,
    COUNT(dm.full_subpage_count) as total_domains,
    SUM(CASE WHEN dm.package_size = 'S' THEN 1 ELSE 0 END) as count_s_package,
    SUM(CASE WHEN dm.package_size = 'M' THEN 1 ELSE 0 END) as count_m_package,
    SUM(CASE WHEN dm.package_size = 'L' THEN 1 ELSE 0 END) as count_l_package
FROM months m
LEFT JOIN domain_metrics dm ON dm.dw_valid_from <= m.report_month
GROUP BY 1, 2
