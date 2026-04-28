# Job Sources

This document describes the job sources supported by Job Hunter EU.

## Arbeitnow

- **Name**: `arbeitnow`
- **URL**: [https://www.arbeitnow.com/](https://www.arbeitnow.com/)
- **API Endpoint**: `https://www.arbeitnow.com/api/job-board-api`
- **Authentication**: None required.
- **Format**: JSON.
- **Pagination**: Supported via `links.next` in the response.
- **Rate Limit**: Not strictly documented, but handled by the centralized `SourceHttpClient` with exponential backoff and 1 concurrent request per host.
- **Notes**: Results are ordered by `created_at` descending. The scraper stops when it encounters a job older than the `since` threshold.
