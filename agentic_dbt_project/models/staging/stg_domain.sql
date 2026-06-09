SELECT 
    domain_id, 
    domain_group_id, 
    full_subpage_count, 
    is_temp_domains,
    dw_valid_from, 
    dw_valid_to
FROM main.domain
WHERE dw_valid_to = '9999-12-31'
