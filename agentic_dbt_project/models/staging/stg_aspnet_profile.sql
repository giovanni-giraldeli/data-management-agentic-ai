SELECT 
    user_id, 
    address_country_code, 
    customer_plan, 
    customer_payment_type,
    dw_valid_from, 
    dw_valid_to
FROM main.aspnet_profile
WHERE dw_valid_to = '9999-12-31'
