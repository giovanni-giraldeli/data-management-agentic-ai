SELECT 
    dg.domain_group_id,
    p.company_size
FROM {{ ref('stg_domain_group') }} dg
JOIN {{ ref('stg_aspnet_profile') }} p ON dg.customer_id = p.user_id
-- Removed the dw_valid_to IS NULL filter to ensure we capture historical company sizes
-- if needed, though for a simple join, this is the most direct path.
