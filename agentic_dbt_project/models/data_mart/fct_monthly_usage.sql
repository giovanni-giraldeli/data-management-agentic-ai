WITH RECURSIVE months AS (
    SELECT CAST('2022-01-01' AS DATE) as month_end
    UNION ALL
    SELECT month_end + INTERVAL 1 MONTH
    FROM months
    WHERE month_end < CURRENT_DATE
),
domain_history AS (
    SELECT 
        d.domain_id,
        dg.customer_id,
        d.is_temp_domains,
        d.dw_valid_from,
        d.dw_valid_to
    FROM main.domain d
    JOIN main.domain_group dg ON d.domain_group_id = dg."domain_group_Id"
),
monthly_snapshots AS (
    SELECT 
        m.month_end,
        dh.customer_id,
        COUNT(dh.domain_id) as domain_count
    FROM months m
    JOIN domain_history dh ON m.month_end >= dh.dw_valid_from AND m.month_end < dh.dw_valid_to
    WHERE dh.is_temp_domains = 0
    GROUP BY 1, 2
)
SELECT 
    month_end,
    customer_id,
    domain_count,
    CASE 
        WHEN domain_count <= 500 THEN 'S'
        WHEN domain_count <= 5000 THEN 'M'
        ELSE 'L'
    END as package_category
FROM monthly_snapshots
