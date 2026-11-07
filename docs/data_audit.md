# Data audit

What each source really returned, what surprised us, and what is missing. Written as the work
happened. Counts are filled in from real runs; nothing here is an estimate unless it says so.

## Sources re-verified on 2026-11-07

| Source | Result of re-check | Used for |
|---|---|---|
| ecosyste.ms packages list | Works. Page 5 at 1,000 per page ends at build123d, 640,909 monthly downloads | Choosing the top 5,000 |
| ecosyste.ms commits API | Works, but returns names and emails of committers | **Not used.** Git history gives what we need without storing identities |
| PyPI JSON API | Works. Serves `requires_dist` and `project_urls` | Dependency graph, repo fallback |
| deps.dev | Package endpoint works | Not used (dependency results looked incomplete in the earlier test) |
| OpenSSF Scorecard | Works | Not used in the forecast |
| pypistats | Works. urllib3 last month = 1,323,555,688, the same as ecosyste.ms | Cross-check of downloads |

## Surprises

1. **Rate limit is 5,000 an hour, not 15,000.** The `x-ratelimit-limit` header for anonymous use
   said 5,000. The project uses 5 list pages, not thousands of single-package calls, so this
   doesn't matter in practice.
2. **The OpenSSF criticality history can't be downloaded.** The bucket
   `ossf-criticality-score` still lists dated folders from 2022 to 2025, but every file request
   returns a 403 about an absent billing account. The upstream repo says the bucket and BigQuery
   data are no longer available. The only free copies are in that repo's `data/` folder: a full
   scored list dated 2025-07-25. See D7 for what this does to the baseline.
3. **Some top packages have no repo at ecosyste.ms but do on PyPI** (numba, protobuf). PyPI's
   `project_urls` is used as a fallback.
