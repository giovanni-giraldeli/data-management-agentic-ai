
-- models/data_mart/dim_customers.sql
SELECT
    m.user_id as customer_id,
    m.user_create_time,
    p.address_country_code,
    p.customer_plan,
    p.customer_payment_type
FROM {{ ref('stg_aspnet_membership') }} m
LEFT JOIN {{ ref('stg_aspnet_profile') }} p ON m.user_id = p.user_id
