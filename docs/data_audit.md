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
3. **PyPI's own metadata rarely fills the gaps.** I expected well-known packages with no repo at
   ecosyste.ms to have one in PyPI's `project_urls`. Only 4 of 296 did. numba, protobuf, thrift
   and others list only a homepage, and some use hosts we can't read (Mercurial on Heptapod,
   SourceForge). They stay "unknown" rather than getting a guessed repo.

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

## Coverage of the current top 5,000 (first harvest, 2026-11-07)

Lowest package in the list: 640,909 monthly downloads.

| What | Count |
|---|---|
| Packages | 5,000 |
| With a repo we could identify | 4,708 |
| No readable repo link (unknown on the site) | 292 |
| Hosts: GitHub / GitLab / Bitbucket / Codeberg | 4,677 / 18 / 11 / 2 |
| Distinct repos | 3,847 |
| Repos read | 3,812 |
| Repos that couldn't be cloned (deleted, private or moved without a redirect) | 35 |
| Packages unknown in total, including unreadable repos | 328 (17 of them in the top 500) |

- **Monorepos:** the largest repo backs 139 of the top 5,000 packages. Family repos and Nvidia's
  binary packages inflate package counts, which is why forecasts and error bars use repos.
- **Renames:** GitHub redirects clones, and ecosyste.ms's `repo_metadata` follows renames.
- **Non-GitHub hosts:** GitLab, Bitbucket and Codeberg clones worked the same way.
- **Binary-only vendors:** many Nvidia packages have a marketing homepage and no public repo.
- **Dependencies:** PyPI returned 99.96% of packages, but only 77% declare `requires_dist`.
  A missing value can mean no dependencies, or metadata PyPI couldn't extract from an old-style
  upload. Dependents are therefore a floor. The graph has 14,642 direct edges.

## Spot checks (2026-11-07)

| Check | Ours | Independent source |
|---|---|---|
| urllib3 human commits, past year | 132 | ecosyste.ms: 167 total minus 35 bot = 132 |
| urllib3 active people, past year | 51 | ecosyste.ms: 52 committers minus 1 bot = 51 |
| h11 no human commit in a year | 562 days | ecosyste.ms list in the brief: no push in a year |
| sortedcontainers same | 981 days | same |
| urllib3 monthly downloads | 1,323,555,688 | pypistats: the same |
