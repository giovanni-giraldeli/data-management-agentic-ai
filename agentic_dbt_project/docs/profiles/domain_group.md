# Profile: domain_group
**Row count:** 1,079,028 | **Columns:** 4 | **Completeness:** 100%

## Column profiles
### domain_group_Id (BIGINT)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1,079,028 distinct |

### customer_id (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 419,166 distinct |

## ⚠ Data Nuances
- `domain_group_Id` is a candidate primary key.
- `dw_valid_to` uses '9999-12-31' for 295,478 rows (~27.4%).

## FK Validation
- domain_group.customer_id → aspnet_profile.user_id (0 orphans)
- domain.domain_group_id → domain_group.domain_group_id (0 orphans)
