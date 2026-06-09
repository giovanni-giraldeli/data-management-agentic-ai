# Agentic dbt Project Documentation

## 1. Conceptual Overview
This project implements a **Star Schema** design to support analytical reporting on customer product usage. The architecture centralizes data into a clean, performant structure, separating raw source data from business-ready dimensions and facts.

## 2. Logical Data Model
The project follows a standard dbt layering approach:
- **Staging Layer**: Cleans and standardizes raw data from `aspnet` and `domain` sources.
- **Data Mart Layer**:
    - `dim_customers`: A dimension table containing customer attributes (plan, country, payment type).
    - `fct_product_usage_monthly`: A fact table capturing monthly product usage metrics (domain counts, package tiers).

## 3. Physical Data Model
- **Schema Naming**: Models are materialized in the `main` schema (default for DuckDB).
- **Naming Conventions**:
    - `stg_`: Staging models.
    - `dim_`: Dimension tables.
    - `fct_`: Fact tables.
- **Relationships**: `fct_product_usage_monthly` maintains a foreign key relationship with `dim_customers` via `customer_id`.

## 4. Semantic Layer Metrics
The project defines metrics for business intelligence:
- **Total Customers**: Count of unique customers.
- **Total Domains Active**: Sum of all domains across the customer base.
- **Package Breakdown**: Specific metrics for `S`, `M`, and `L` package domain counts.

## 5. Project Accomplishments
- Established a robust ELT pipeline from raw sources to a star-schema data mart.
- Implemented dbt semantic layer metrics for consistent business reporting.
- Ensured data integrity through automated testing (unique/not-null constraints and relationship checks).
