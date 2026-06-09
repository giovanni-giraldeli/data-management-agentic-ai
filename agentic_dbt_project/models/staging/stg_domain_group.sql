
-- models/staging/stg_domain_group.sql
SELECT
    domain_group_id,
    customer_id,
    dw_valid_from,
    dw_valid_to
FROM {{ source('domains', 'domain_group') }}
WHERE dw_valid_to IS NULL OR dw_valid_to > CURRENT_DATE
