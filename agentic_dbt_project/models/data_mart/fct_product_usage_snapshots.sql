
-- models/data_mart/fct_product_usage_snapshots.sql
SELECT
    md5(concat(customer_id, '-', domain_id, '-', snapshot_date)) as usage_id,
    customer_id,
    domain_id,
    full_subpage_count,
    is_temp_domains,
    snapshot_date
FROM {{ ref('int_customer_domains') }}
