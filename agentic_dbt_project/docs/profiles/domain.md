# Profile: domain
**Row count:** 8,277,242 | **Columns:** 6 | **Completeness:** 100%

## Column profiles

### domain_id (BIGINT)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 8,277,242 distinct |

### domain_group_id (BIGINT)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1,079,028 distinct |

## ⚠ Data Nuances
- No anomalies detected.

## FK Validation
- `domain.domain_group_id` references `domain_group.domain_group_Id` (8,277,242 rows validated, 0 orphans).
