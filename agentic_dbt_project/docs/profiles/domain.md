# Data Profile: domain

## Overview
- **Row Count:** 8,277,242
- **Primary Key Candidate:** `domain_id` (Note: Not unique, 449,381 unique values out of 8,277,242 rows).

## Column Analysis
| Column | Type | Nulls | Distinct Values |
| :--- | :--- | :--- | :--- |
| domain_id | BIGINT | 0 | 449,381 |
| domain_group_id | BIGINT | 0 | 296,201 |
| full_subpage_count | BIGINT | 0 | 1,500 |
| is_temp_domains | BIGINT | 0 | 2 |

## Observations
- This is a large fact-like table.
- `is_temp_domains` acts as a flag (0/1).
- `domain_group_id` links to the `domain_group` table.
