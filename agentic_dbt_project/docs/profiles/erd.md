# Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    ASPNET_MEMBERSHIP ||--o{ ASPNET_PROFILE : "user_id"
    DOMAIN_GROUP ||--o{ DOMAIN : "domain_group_id"
    
    ASPNET_MEMBERSHIP {
        string user_id
        timestamp user_create_time
    }
    
    ASPNET_PROFILE {
        string user_id
        string address_country_code
        string customer_plan
    }
    
    DOMAIN {
        bigint domain_id
        bigint domain_group_id
    }
    
    DOMAIN_GROUP {
        bigint domain_group_Id
        string customer_id
    }
```

## Relationships
- **Users:** `aspnet_membership` and `aspnet_profile` are linked by `user_id`.
- **Domains:** `domain_group` and `domain` are linked by `domain_group_id`.
- **Note:** All tables appear to be SCD Type 2 or historical logs, as primary keys are not unique across the entire table.
