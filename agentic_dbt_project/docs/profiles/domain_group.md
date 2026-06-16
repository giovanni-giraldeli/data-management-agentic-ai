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
- No anomalies detected.

## FK Validation
- `domain.domain_group_id` references `domain_group.domain_group_Id` (8,277,242 rows validated, 0 orphans).
- `domain_group.customer_id` references `aspnet_profile.user_id` (1,079,028 rows validated, 0 orphans).
