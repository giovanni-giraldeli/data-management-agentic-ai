# Profile: stg_aspnet_profile
**Row count:** 1,200,000 | **Columns:** 13 | **Completeness:** 98%

## Column profiles
### user_id (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1,200,000 distinct |

### company_size (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 12,000 (1%) |
| Cardinality | 12 distinct |

## ⚠ Data Nuances
- **Nulls:** 1% of `company_size` is NULL, which propagates to downstream models.

## FK Validation
- stg_aspnet_profile.user_id → stg_domain_group.customer_id (Validated)
