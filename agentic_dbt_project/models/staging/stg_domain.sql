
-- models/staging/stg_domain.sql
SELECT
    domain_id,
    domain_group_id,
    full_subpage_count,
    is_temp_domains,
    dw_valid_from,
    dw_valid_to
FROM {{ source('domains', 'domain') }}
WHERE dw_valid_to IS NULL OR dw_valid_to > CURRENT_DATE
