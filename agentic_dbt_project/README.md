# Project Overview: Customer Usage Analytics

This dbt project transforms raw ASP.NET membership and domain data into a structured analytical model to track customer growth and usage patterns.

## 1. Conceptual Data Model
The project follows a **Star Schema** design:
- **Fact Table:** `fct_monthly_usage` captures the grain of monthly domain activity per customer.
- **Dimension Table:** `dim_customers` provides descriptive attributes for customers, including plan types and geographic information.

## 2. Logical Data Model
The project is organized into three distinct layers:
- **Staging (`models/staging/`):** Cleans and standardizes raw source data (`aspnet_membership`, `aspnet_profile`, `domain`, `domain_group`).
- **Data Mart (`models/data_mart/`):** Aggregates and joins staging models to create business-ready entities (`dim_customers`, `fct_monthly_usage`).
- **Semantics (`models/semantics/`):** Defines metrics and time-based structures for BI consumption.

## 3. Physical Data Model
| Layer | Table Name | Primary Key | Relationships |
| :--- | :--- | :--- | :--- |
| Data Mart | `dim_customers` | `user_id` | N/A |
| Data Mart | `fct_monthly_usage` | N/A | `customer_id` -> `dim_customers.user_id` |

## 4. Business Logic and Metrics
- **Customer Segmentation:** Customers are categorized into 'S', 'M', and 'L' packages based on their monthly domain count.
- **Usage Tracking:** The `fct_monthly_usage` table tracks domain activity over time, allowing for trend analysis of customer engagement.
- **Data Grain:** The fact table is aggregated at the `customer` + `month` level.

## 5. Data Quality and Integrity
The following referential integrity issues have been identified:
- **Staging Layer:** Orphaned records exist between `aspnet_profile` and `aspnet_membership` (14 orphans).
- **Data Mart Layer:** Orphaned records exist between `fct_monthly_usage` and `dim_customers` (11 orphans).

**Recommendations:**
- Investigate the source systems to determine why these records are missing their parent references.
- Implement dbt tests (e.g., `relationships`) to monitor these failures and alert the data engineering team.
- Consider implementing a "soft" join or a "dummy" record strategy if these orphans are expected to persist in the source data.
