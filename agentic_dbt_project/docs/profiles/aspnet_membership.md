# Profile: aspnet_membership
**Row count:** 1,300,627 | **Columns:** 4 | **Completeness:** 100%

## Column profiles

### user_id (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1,300,627 distinct |
| Min / Max | N/A |

### user_create_time (TIMESTAMP)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1,298,452 distinct |
| Min / Max | 2000-01-01 00:00:00 / 2025-06-14 23:59:59 |

### dw_valid_from (DATE)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 5,614 distinct |

### dw_valid_to (DATE)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 5,615 distinct |

## ⚠ Data Nuances
- **Sentinel Value:** `dw_valid_to` contains `9999-12-31` in 129,109 rows (~10%). This is a standard SCD Type 2 sentinel indicating the record is currently active. Downstream models should filter by `dw_valid_to = '9999-12-31'` to isolate current records.

## FK Validation
No FK relationships defined for this table.
