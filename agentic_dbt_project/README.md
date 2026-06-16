# Project Overview
This dbt project transforms raw backend data from customer membership, profile, and domain event systems into a structured analytical layer. It enables tracking of user lifecycle, domain usage, and customer segmentation.

## Conceptual Data Model
The project revolves around three core entities:
- **User**: The primary customer entity, defined by membership and profile data.
- **Domain Group**: A collection of domains associated with a specific user.
- **Domain**: Individual domain instances tracked over time.

**Relationships:**
- A **User** owns one or more **Domain Groups**.
- A **Domain Group** contains one or more **Domains**.

## Logical Data Model
The project follows a standard dbt layering approach:
1. **Staging (`models/staging/`)**: Cleans and standardizes raw source data.
   - `stg_aspnet_profile`: User profile attributes.
   - `stg_domain`: Domain event records.
   - `stg_domain_group`: Mapping of domain groups to users.
2. **Intermediary (`models/intermediary/`)**: Joins and aggregates data for complex business logic.
   - `int_domain_groups_with_size`: Enriches domain groups with user profile attributes (e.g., company size).
3. **Data Mart (`models/data_mart/`)**: Final business-ready tables.
   - `fct_monthly_domain_count`: Aggregated domain usage metrics by month.

## Physical Data Model
The project materializes the following tables in DuckDB:
- `stg_aspnet_profile`: Primary key `user_id`.
- `stg_domain`: Primary key `domain_id`, Foreign key `domain_group_id` -> `stg_domain_group`.
- `stg_domain_group`: Primary key `domain_group_id`, Foreign key `customer_id` -> `stg_aspnet_profile`.
- `fct_monthly_domain_count`: Aggregated fact table.

## Data Quality Findings
- **Duplicates**: Source data is generally clean, but SCD Type 2 logic requires careful filtering using `dw_valid_to = '9999-12-31'`.
- **Nulls**: `company_size` in `stg_aspnet_profile` has a 1% null rate.
- **Unexpected Values**: `company_size` contains 12 distinct bins; ensure downstream reporting handles these categories appropriately.
