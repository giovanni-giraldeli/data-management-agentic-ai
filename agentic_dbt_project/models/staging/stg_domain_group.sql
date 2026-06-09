SELECT 
    domain_group_id, 
    customer_id, 
    dw_valid_from, 
    dw_valid_to
FROM main.domain_group
WHERE dw_valid_to = '9999-12-31'
