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
