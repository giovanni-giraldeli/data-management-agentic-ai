# Data Profile: aspnet_membership

## Overview
- **Row Count:** 1,300,627
- **Primary Key Candidate:** `user_id` (Note: Not unique, 129,110 unique values out of 1,300,627 rows). This table likely tracks history or multiple entries per user.

## Column Analysis
| Column | Type | Nulls | Distinct Values |
| :--- | :--- | :--- | :--- |
| user_id | VARCHAR | 0 | 129,110 |
| user_create_time | TIMESTAMP | 0 | 1,291,100 |
| dw_valid_from | DATE | 0 | 1,291,100 |
| dw_valid_to | DATE | 0 | 1,291,100 |

## Observations
- The table contains historical data as indicated by the `dw_valid_` columns.
- `user_create_time` is highly granular.
