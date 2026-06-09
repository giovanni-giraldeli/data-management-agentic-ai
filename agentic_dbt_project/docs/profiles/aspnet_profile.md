# Data Profile: aspnet_profile

## Overview
- **Row Count:** 419,166
- **Primary Key Candidate:** `user_id` (Note: Not unique, 129,124 unique values out of 419,166 rows).

## Column Analysis
| Column | Type | Nulls | Distinct Values |
| :--- | :--- | :--- | :--- |
| user_id | VARCHAR | 0 | 129,124 |
| address_country_code | VARCHAR | 0 | 245 |
| payment_currency | VARCHAR | 0 | 150 |
| payment_card_type | VARCHAR | 0 | 15 |
| user_language | VARCHAR | 0 | 50 |
| customer_plan | VARCHAR | 0 | 20 |

## Observations
- Contains user demographic and payment profile information.
- High cardinality in `address_country_code` and `payment_currency`.
- `payment_data_completed` is a boolean flag.
