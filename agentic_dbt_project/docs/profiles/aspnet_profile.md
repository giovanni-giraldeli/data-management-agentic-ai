# Profile: aspnet_profile
**Row count:** 419,166 | **Columns:** 13 | **Completeness:** ~95%

## Column profiles

### user_id (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 0 (0%) |
| Cardinality | 419,166 distinct |

### address_country_code (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 58,251 (13.9%) |
| Cardinality | 245 distinct |

### payment_card_expiration_date (VARCHAR)
| Metric | Value |
|--------|-------|
| Null count / rate | 112,789 (26.9%) |
| Cardinality | 121 distinct |

## ⚠ Data Nuances
- No specific sentinel values detected in the checked columns. High null rates in `address_country_code` and `payment_card_expiration_date` suggest optional profile fields.

## FK Validation
- `domain_group.customer_id` references `aspnet_profile.user_id` (1,079,028 rows validated, 0 orphans).
