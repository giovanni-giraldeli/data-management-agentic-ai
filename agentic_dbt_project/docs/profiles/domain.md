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
- `domain_id` is a candidate primary key.
- `dw_valid_to` uses '9999-12-31' for 377,605 rows (~4.6%).

## FK Validation
- domain.domain_group_id → domain_group.domain_group_id (0 orphans)
