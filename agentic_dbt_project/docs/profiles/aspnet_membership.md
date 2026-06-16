# Profile: aspnet_membership
**Row count:** 1,300,627 | **Columns:** 4 | **Completeness:** 100%

## Column profiles
### user_id (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1,300,627 distinct |

### user_create_time (TIMESTAMP)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1,299,852 distinct |

### dw_valid_from (DATE)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1,254 distinct |

### dw_valid_to (DATE)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1,254 distinct |

⚠ Sentinel / magic values:
- '9999-12-31' appears in 129,109 rows (~9.9%). This is a standard sentinel for "active/current" records in SCD Type 2. Do not treat as a literal date.

## ⚠ Data Nuances
- The `dw_valid_to` column uses '9999-12-31' to denote active records.
- `user_id` is a candidate primary key.

## FK Validation
- aspnet_profile.user_id → aspnet_membership.user_id (14 orphans found)
