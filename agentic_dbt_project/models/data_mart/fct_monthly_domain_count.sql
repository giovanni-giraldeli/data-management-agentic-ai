WITH RECURSIVE date_range AS (
    SELECT (SELECT MIN(dw_valid_from) FROM {{ ref('stg_domain') }})::DATE AS d
    UNION ALL
    SELECT d + INTERVAL '1 month' FROM date_range WHERE d < (SELECT MAX(dw_valid_from) FROM {{ ref('stg_domain') }})
),
month_ends AS (
    SELECT 
        date_trunc('month', d)::DATE AS month,
        last_day(d) AS last_day
    FROM date_range
)

SELECT 
    me.month,
    igs.company_size,
    COUNT(d.domain_id) AS domain_count
FROM month_ends me
JOIN {{ ref('stg_domain') }} d 
    ON d.dw_valid_from <= me.last_day 
    AND (d.dw_valid_to > me.last_day OR d.dw_valid_to IS NULL)
JOIN {{ ref('int_domain_groups_with_size') }} igs 
    ON d.domain_group_id = igs.domain_group_id
GROUP BY 1, 2
