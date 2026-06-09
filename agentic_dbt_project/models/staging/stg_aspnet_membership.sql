
-- models/staging/stg_aspnet_membership.sql
SELECT
    user_id,
    user_create_time,
    dw_valid_from,
    dw_valid_to
FROM {{ source('aspnet', 'aspnet_membership') }}
WHERE dw_valid_to IS NULL OR dw_valid_to > CURRENT_DATE
