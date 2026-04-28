# Data Model

This document describes the database schema for the Job Hunter EU project.

## Tables

### `jobs`

The central entity of the system. It stores job offers ingested from various sources, enriched with scoring data.

| Column | Type | Description |
|---|---|---|
| `id` | `UUID` | Primary key, auto-generated using `gen_random_uuid()`. |
| `source` | `VARCHAR(50)` | The source of the job offer (e.g., 'arbeitnow', 'remoteok'). |
| `source_id` | `VARCHAR(255)` | Original ID from the source, if available. |
| `url` | `TEXT` | Full URL to the job offer. |
| `url_hash` | `VARCHAR(64)` | SHA256 hash of the canonical URL, used for deduplication (UNIQUE). |
| `title` | `TEXT` | Job title. |
| `company` | `TEXT` | Company name. |
| `location_raw` | `TEXT` | Location as provided by the source. |
| `description` | `TEXT` | Full job description. |
| `posted_at` | `TIMESTAMPTZ` | When the job was posted (if available). |
| `scraped_at` | `TIMESTAMPTZ` | When the job was ingested (defaults to `now()`). |
| `raw_payload` | `JSONB` | Original data received from the source. |
| `scored_at` | `TIMESTAMPTZ` | When the job was scored by the AI. |
| `score_model` | `VARCHAR(50)` | AI model used for scoring. |
| `score_version` | `VARCHAR(20)` | Version of the scoring prompt. |
| `fit_score` | `INTEGER` | Numerical score (0-100). |
| `tier` | `VARCHAR(10)` | Category based on score ('A', 'B', 'C', 'REJECT'). |
| `score_data` | `JSONB` | Structured output from the scoring AI. |
| `status` | `VARCHAR(30)` | Current status in the pipeline (defaults to 'new'). |

#### Indices

* `idx_jobs_status`: On `status`.
* `idx_jobs_tier`: On `tier`.
* `idx_jobs_scraped_at`: On `scraped_at DESC`.
* `idx_jobs_company`: On `company`.
* `jobs_url_hash_key`: UNIQUE constraint on `url_hash`.

## Enums

### `JobStatus`

* `new`: Ingested but not yet processed.
* `scored`: Evaluated by the AI.
* `queued`: Shortlisted for application.
* `applied`: Application submitted.
* `manual_review`: Needs human intervention.
* `rejected`: Not a good fit.
* `archived`: Old or no longer relevant.

### `JobTier`

* `A`: Excellent fit (Fit Score >= 80).
* `B`: Good fit.
* `C`: Average fit.
* `REJECT`: Poor fit.
