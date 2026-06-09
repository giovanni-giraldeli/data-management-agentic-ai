# Data Profile: aspnet_membership

- **Row Count:** 1,300,627
- **Unique User IDs:** 129,110
- **SCD Type 1 Logic:** Current records are identified where `dw_valid_to = '9999-12-31'`.
- **Temporal Range:** `dw_valid_from` and `dw_valid_to` span from 2022-01-20 to 9999-12-31.

| Column | Null Rate | Cardinality |
| :--- | :--- | :--- |
| user_id | 0% | 129,110 |
| user_create_time | 0% | 1,291,100 |
| dw_valid_from | 0% | 850 |
| dw_valid_to | 0% | 850 |
