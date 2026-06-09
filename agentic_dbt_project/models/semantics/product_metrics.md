# Product Usage Metrics

## Overview
This document defines the key performance indicators (KPIs) for product usage, focusing on customer growth and domain distribution across different service packages.

## Metrics

### 1. Total Number of Customers
- **Definition**: The total count of unique customers identified in the system.
- **Calculation**: `count(distinct customer_id)`
- **Grain**: Customer level.
- **Consumers**: Executive leadership, Sales team.

### 2. Total Number of Domains
- **Definition**: The total number of domains managed by all customers.
- **Calculation**: `sum(total_domains)`
- **Grain**: Monthly.
- **Consumers**: Product team, Operations.

### 3. Domains by Package (S/M/L)
- **Definition**: The total number of domains categorized by their service package (Small, Medium, Large).
- **Calculation**: `sum(count_s_package)`, `sum(count_m_package)`, `sum(count_l_package)`
- **Grain**: Monthly.
- **Consumers**: Product team, Finance.
