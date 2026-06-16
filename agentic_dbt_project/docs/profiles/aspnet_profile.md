# Profile: aspnet_profile
**Row count:** 419,166 | **Columns:** 13 | **Completeness:** 100%

## Column profiles
### user_id (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 419,166 distinct |

⚠ Sentinel / magic values:
- '9999-12-31' appears in 129,123 rows (~30.8%). This is a standard sentinel for "active/current" records.

## ⚠ Data Nuances
- `user_id` is a candidate primary key.
- 14 records in `aspnet_profile` have a `user_id` that does not exist in `aspnet_membership`.

## FK Validation
- aspnet_profile.user_id → aspnet_membership.user_id (14 orphans)
- domain_group.customer_id → aspnet_profile.user_id (0 orphans)
