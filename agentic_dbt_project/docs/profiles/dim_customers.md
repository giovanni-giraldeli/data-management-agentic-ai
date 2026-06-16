# Profile: dim_customers
**Row count:** 129123 | **Columns:** 5 | **Completeness:** 99.08%

## Column profiles
### user_id (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 129123 distinct |
| Min / Max | N/A |
| P5 / P25 / P50 / P75 / P95 | N/A |
| Outliers (IQR method) | N/A |

### create_date (TIMESTAMP)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 129076 distinct |
| Min / Max | 2013-01-12 / 2028-12-02 |
| P5 / P25 / P50 / P75 / P95 | 2018-09-25 / 2021-10-15 / 2023-10-27 / 2024-05-23 / 2025-02-05 |
| Outliers (IQR method) | N/A |

### max_subpage_count (BIGINT)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 8364 distinct |
| Min / Max | 0 / 22189 |
| P5 / P25 / P50 / P75 / P95 | 8 / 71 / 240 / 1109 / 10238 |
| Outliers (IQR method) | 20366 rows (15.77%), range [2666, 22189] |

## ⚠ Data Nuances
- **max_subpage_count Outliers:** 20,366 rows (15.77%) are identified as outliers using the IQR method. Given the high cardinality and the nature of usage metrics, these likely represent power users rather than data errors.
- **create_date Future Dates:** The maximum date is 2028-12-02. This should be monitored as it is significantly in the future.

## FK Validation
- No FK relationships defined for this table.
