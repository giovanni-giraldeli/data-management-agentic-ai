
-- models/staging/stg_aspnet_profile.sql
SELECT
    user_id,
    address_country_code,
    customer_plan,
    customer_payment_type,
    dw_valid_from,
    dw_valid_to
FROM {{ source('aspnet', 'aspnet_profile') }}
WHERE dw_valid_to IS NULL OR dw_valid_to > CURRENT_DATE
