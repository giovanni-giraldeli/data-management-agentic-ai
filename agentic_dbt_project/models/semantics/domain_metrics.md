# Domain Metrics

## Overview
This document describes the metrics related to domain counts, aggregated by company size.

## Metrics

### Total Domain Count
- **Business Definition**: The total number of domains registered or active, aggregated by month and company size.
- **Calculation Logic**: Sum of `domain_count` from the `fct_monthly_domain_count` table.
- **Grain**: Monthly, per company size.
- **Typical Consumers**: Executive leadership, Sales Operations, Product Managers.
