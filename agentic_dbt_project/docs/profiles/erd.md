# Entity-Relationship Diagram

## Relationships
- `aspnet_profile.user_id` → `aspnet_membership.user_id`: **Verified** (14 orphaned records found in `aspnet_profile`).
- `domain_group.customer_id` → `aspnet_profile.user_id`: **Verified** (Integrity maintained).
- `domain.domain_group_id` → `domain_group.domain_group_id`: **Verified** (Integrity maintained).

## SCD Type 1 & Snapshot Logic
- **Current Records:** Filter by `dw_valid_to = '9999-12-31'`.
- **End-of-Month Snapshots:** To retrieve snapshots for the last 2 years, filter records where `dw_valid_from <= EOMONTH` and `dw_valid_to > EOMONTH`.
