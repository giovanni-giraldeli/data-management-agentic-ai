# Semantic Metrics Documentation

## Overview
This document defines the core business metrics for customer and domain usage analysis.

## Metrics

### 1. Total Number of Customers
- **Definition**: The total count of unique customers registered in the system.
- **Calculation**: Count of distinct `user_id` from `dim_customers`.
- **Grain**: Customer.
- **Consumers**: Executive Management, Sales Team.

### 2. Total Number of Domains
- **Definition**: The total number of domains managed across all customers.
- **Calculation**: Sum of `domain_count` from `fct_monthly_usage`.
- **Grain**: Monthly.
- **Consumers**: Product Team, Operations.

### 3. Domains by Package (S, M, L)
- **Definition**: The number of domains categorized by their subscription package (S, M, or L).
- **Calculation**: Sum of `domain_count` filtered by `package_category`.
- **Grain**: Monthly.
- **Consumers**: Product Team, Marketing.
