WITH profile AS (
    SELECT * FROM {{ ref('stg_aspnet_profile') }}
),
membership AS (
    SELECT * FROM {{ ref('stg_aspnet_membership') }}
),
domain_groups AS (
    SELECT * FROM {{ ref('stg_domain_group') }}
),
domains AS (
    SELECT * FROM {{ ref('stg_domain') }}
),
customer_domains AS (
    SELECT 
        dg.customer_id,
        MAX(d.full_subpage_count) as max_subpage_count
    FROM domain_groups dg
    JOIN domains d ON dg.domain_group_id = d.domain_group_id
    GROUP BY 1
)
SELECT 
    p.user_id,
    m.user_create_time as create_date,
    CASE 
        WHEN p.address_country_code = 'DE' THEN 'Germany'
        WHEN p.address_country_code = 'US' THEN 'United States'
        ELSE p.address_country_code 
    END as country_name,
    p.customer_plan,
    cd.max_subpage_count
FROM profile p
LEFT JOIN membership m ON p.user_id = m.user_id
LEFT JOIN customer_domains cd ON p.user_id = cd.customer_id
