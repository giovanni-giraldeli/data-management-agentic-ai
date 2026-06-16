SELECT 
    user_id, 
    user_create_time, 
    dw_valid_from, 
    dw_valid_to
FROM main.aspnet_membership
WHERE dw_valid_to = '9999-12-31'
