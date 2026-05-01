# ADR-003: GitHub Actions for Orchestration

## Status
Accepted

## Context
The system requires periodic execution of tasks: scraping, scoring, notifications, and analytics.

## Decision
We use **GitHub Actions** as the primary orchestration engine instead of a dedicated tool like Airflow or Prefect.

## Consequences
- **Pros:** Zero infrastructure maintenance, integrated with the repository, free tier is sufficient for personal use.
- **Cons:** Workflows are limited by GitHub's infrastructure, debugging long-running jobs can be harder than on local orchestrators.
