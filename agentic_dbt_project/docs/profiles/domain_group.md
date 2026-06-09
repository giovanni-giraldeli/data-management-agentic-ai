# Data Profile: domain_group

## Overview
- **Row Count:** 1,079,028
- **Primary Key Candidate:** `domain_group_Id` (Note: Not unique, 296,201 unique values out of 1,079,028 rows).

## Column Analysis
| Column | Type | Nulls | Distinct Values |
| :--- | :--- | :--- | :--- |
| domain_group_Id | BIGINT | 0 | 296,201 |
| customer_id | VARCHAR | 0 | 150,000 |

## Observations
- Links domains to customers.
- `customer_id` is likely the user or account identifier.
