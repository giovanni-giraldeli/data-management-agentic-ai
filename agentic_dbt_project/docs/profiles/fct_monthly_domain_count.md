# Profile: fct_monthly_domain_count
**Row count:** 12,450 | **Columns:** 3 | **Completeness:** 100%

## Column profiles
### company_size (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 12 distinct |

## ⚠ Data Nuances
- **Orphaned Records:** 42 rows in `fct_monthly_domain_count` have a `company_size` that does not exist in `int_domain_groups_with_size`. This suggests data drift or missing mappings in the intermediary model.

## FK Validation
- fct_monthly_domain_count.company_size → int_domain_groups_with_size.company_size (42 orphans)
