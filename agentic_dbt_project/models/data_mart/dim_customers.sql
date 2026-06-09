WITH profile AS (
    SELECT * FROM {{ ref('stg_aspnet_profile') }}
),
membership AS (
    SELECT * FROM {{ ref('stg_aspnet_membership') }}
),
domain_data AS (
    SELECT 
        dg.customer_id,
        MAX(d.full_subpage_count) as max_subpage_count
    FROM {{ ref('stg_domain') }} d
    JOIN {{ ref('stg_domain_group') }} dg ON d.domain_group_id = dg.domain_group_id
    GROUP BY 1
)

SELECT 
    p.user_id as customer_id,
    m.user_create_time as create_date,
    p.customer_plan,
    p.customer_payment_type,
    p.address_country_code as country_name,
    d.max_subpage_count
FROM profile p
LEFT JOIN membership m ON p.user_id = m.user_id
LEFT JOIN domain_data d ON p.user_id = d.customer_id
