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

## RemoteOK

- **Name**: `remoteok`
- **URL**: [https://remoteok.com/](https://remoteok.com/)
- **API Endpoint**: `https://remoteok.com/api`
- **Authentication**: None required, but mandatory `User-Agent`.
- **Format**: JSON (First element is metadata).
- **Pagination**: None (returns latest jobs in a single request).
- **Rate Limit**: Configured at `0.33` (1 request every 3 seconds).
- **Notes**: Includes a configurable tag filter (defaults to `python`, `ai`, `ml`, `flutter`, `dart`, `senior`, `backend`). Parsing skips the first metadata element.

## WeWorkRemotely

- **Name**: `weworkremotely`
- **URL**: [https://weworkremotely.com/](https://weworkremotely.com/)
- **RSS Feeds**: `https://weworkremotely.com/categories/{category}.rss`
- **Authentication**: None required.
- **Format**: RSS (XML).
- **Pagination**: None (returns latest jobs in a single request per feed).
- **Rate Limit**: Handled by the centralized `SourceHttpClient` with 1 concurrent request per host.
- **Notes**: Supports multiple categories (default: `remote-programming-jobs`, `devops-sysadmin-jobs`, `back-end-programming-jobs`). Automatically strips HTML from descriptions and deduplicates jobs appearing in multiple feeds.

## 4dayweek.io

- **Name**: `fourdayweek`
- **URL**: [https://4dayweek.io/](https://4dayweek.io/)
- **API Endpoint**: `https://4dayweek.io/api/v2/jobs`
- **Authentication**: None required.
- **Format**: JSON.
- **Pagination**: Supported via `page` and `limit` query parameters.
- **Rate Limit**: 60 requests per minute per IP.
- **Notes**: Results are ordered by `date` descending. The scraper stops when it encounters a job older than the `since` threshold. Location data is normalized from `office_locations` and `remote_allowed` fields.
