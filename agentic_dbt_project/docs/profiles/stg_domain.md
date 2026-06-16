# Profile: stg_domain
**Row count:** 8,277,242 | **Columns:** 6 | **Completeness:** 100%

## Column profiles
### domain_id (BIGINT)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 8,277,242 distinct |

### dw_valid_to (DATE)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1,240 distinct |
⚠ Sentinel / magic values: 9999-12-31 appears in 377,605 rows (4.56%). Business meaning: open-ended / active record (SCD Type 2).

## ⚠ Data Nuances
- **Sentinel Value:** `dw_valid_to` = '9999-12-31' indicates active records. Downstream models must filter by `dw_valid_to = '9999-12-31'` to isolate current state.

## FK Validation
- stg_domain.domain_group_id → stg_domain_group.domain_group_Id (8,277,242 rows validated, 0 orphans)
