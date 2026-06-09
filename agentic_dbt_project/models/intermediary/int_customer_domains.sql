
-- models/intermediary/int_customer_domains.sql
SELECT
    dg.customer_id,
    d.domain_id,
    d.full_subpage_count,
    d.is_temp_domains,
    d.dw_valid_from as snapshot_date
FROM {{ ref('stg_domain') }} d
JOIN {{ ref('stg_domain_group') }} dg ON d.domain_group_id = dg.domain_group_id
