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

## Bot filter, hand check (2026-11-07)

Method: 80 repos (the 40 most downloaded and 40 random ones) were read in memory, nothing stored.
For the last two years of commits, I read every author flagged as a bot, and every unflagged
author whose name or email contained a word common in automation.

- 70,797 commits: 8,510 flagged as bots (12%).
- Wrongly flagged humans: 2 people, 3 commits. One matched the word "travis". Rules were tightened.
- Missed automation: 1 clear case, 504 commits (a project's update bot). Added.
- AI coding agents that commit under their own identity (Copilot agent, Claude) count as bots.

Limits: this check can't find automation with an ordinary human-looking name, and an account that
mixes a person's commits with scripted ones counts as a person.

## The 2022 archive restore: proven on a runner (2026-11-07)

Run 42411583098 restored `packages-2022-11-09.tar.gz` on a free GitHub runner.

- Download and unpack took about 12 minutes. The runner had 101 GB free after clearing unused
  toolchains, far more than the 14 GB assumed.
- The tarball holds three files: `license.txt`, `readme.md` and a `.sql` file that is a Postgres
  custom-format dump (`PGDMP` magic bytes, dump format 1.14, pg_dump 14.2).
- No Postgres server is needed. `pg_restore -a -t registries -t packages -f -` from the newest
  client (PGDG repo) emits COPY text that Python can read from a pipe.
- The `packages` table has `downloads`, `downloads_period`, `repository_url` and `repo_metadata`.
- The dump also holds `maintainers` and `maintainerships` tables. They are never restored.
