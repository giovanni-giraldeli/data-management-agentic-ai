# Profile: fct_monthly_usage
**Row count:** 4549763 | **Columns:** 4 | **Completeness:** 100%

## Column profiles
### month_end (DATE)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 54 distinct |
| Min / Max | 2020-07-31 / 2025-01-31 |

### customer_id (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 125483 distinct |

### domain_count (BIGINT)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 1898 distinct |

### package_category (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 3 distinct |

## ⚠ Data Nuances
- **package_category Skew:** The 'S' category accounts for 4,541,682 rows (99.8%), while 'M' and 'L' are significantly smaller. This is a highly skewed distribution.

## FK Validation
- fct_monthly_usage.customer_id → dim_customers.user_id (4549763 rows validated, 11 orphans)
