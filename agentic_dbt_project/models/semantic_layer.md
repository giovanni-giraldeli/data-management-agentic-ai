# Semantic Layer Documentation

## Overview
This project implements a semantic layer to provide standardized metrics for product usage analysis.

## Modeling Choices
- **Semantic Models**: We have defined `dim_customers` and `fct_product_usage_snapshots` as the core semantic models.
- **Relationships**: The `fct_product_usage_snapshots` model links to `dim_customers` via the `customer_id` foreign key, allowing for slicing metrics by customer attributes like `customer_plan` or `address_country_code`.
- **Metrics**:
    - `total_subpage_usage`: Aggregates the `full_subpage_count` measure.
    - `active_customer_count`: Counts distinct `customer_id`s to track engagement.

## Consumers
These metrics are intended for use in:
- Executive Dashboards (Customer Growth & Engagement)
- Product Analytics Reports
