# ADR-002: PostgreSQL as Primary Database

## Status
Accepted

## Context
The system needs to store job data, application history, metrics, and audit logs.

## Decision
We use **PostgreSQL** as the primary relational database.

## Consequences
- **Pros:** Robust support for JSONB (used for flexible LLM scoring data), advanced SQL features (CTEs, Window functions for analytics), reliable migrations via Alembic.
- **Cons:** Requires a running service (Docker container), slightly more overhead than SQLite for very small deployments.
