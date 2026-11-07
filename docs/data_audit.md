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

Snapshot run 42413868196 restored `packages-2022-11-09.tar.gz` on a free GitHub runner and printed counts only. Two earlier probe runs were deleted, because one printed two raw rows of the dump to its public log (found in the final review, 2026-11-07).

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

## The 2022 cohort (2026-11-07)

From `packages-2022-11-09`: 413,871 PyPI packages, 280,397 with a download count. The cohort
is the top 5,000 by 2022 last-month downloads (lowest: 28,559).

| What | Count |
|---|---|
| Cohort packages with no readable repo link in 2022 metadata | 839 |
| Distinct cohort repos | 3,684 |
| Hosts: GitHub / Bitbucket / GitLab / Codeberg / sourcehut | 4,096 / 38 / 23 / 3 / 1 |

839 packages with no repo link is far more than today's 292. The 2022 metadata was thinner. These
packages can't enter the backtest, and they aren't a random slice, so this is a stated bias.

The harvest of 6,156 repos (today's list plus the cohort) read 6,031. 124 could not be cloned and
1 was empty. Re-run on 2026-11-07 after the bot filter fix, so all rows use the same filter.

## Outcome hand check (2026-11-07, before any forecast result)

Question: does "active in the prior year, then no human commit for 12 months" separate finished
software from stalled software? I drew 40 random repos labelled quiet at the 2023-11-01 cutoff
(window to 2024-10-31) and looked at public signals git doesn't carry. The sample was printed to
the terminal only. Counts:

| What the record shows | Repos |
|---|---|
| Moved: work continued in another repo, often a monorepo | 2 |
| Formally wound down: archived, or marked deprecated by its owners | 5 |
| Pushes resumed after the window: a pause, not an end | 20 |
| No push since; 10 or fewer open issues (looks finished or low demand) | 7 |
| No push since; more than 10 open issues (looks unattended) | 6 |

From git itself, the share of quiet repos that later had a human commit again:

| Cutoff | Eligible | Quiet in next 12 months | Later had a human commit |
|---|---|---|---|
| 2022-11-09 | 2,670 | 360 (13.5%) | 171 (48%) |
| 2023-11-01 | 2,522 | 413 (16.4%) | 160 (39%) |
| 2024-11-01 | 2,280 | 372 (16.3%) | 126 (34%) |

What this means:
- **"Quiet for a year" is often a pause.** About 4 in 10 came back. The outcome measures a year
  without a human commit, nothing more, and the site says that.
- **It doesn't separate finished from unattended.** Roughly half of the sample that stayed quiet
  looked finished. Open-issue counts help a little, but they are today's numbers, not
  point-in-time ones, so they can't be used as features.
- **The stricter outcome (also no PyPI release) changes little.** 378 of 413 quiet repos in
  2023-11 also had no release. Quiet projects mostly stop releasing too.
- **Moves show up as quiet.** Projects moved into a monorepo look quiet in their old repo. They
  are a small share (2 of 40).

## Live pipeline checks (2026-11-07)

- Weekly run 42417032362 (manual dispatch) succeeded end to end: harvest, scoring, freeze, deploy.
  It froze 2,860 repos as week `2026-11-02` on the `predictions` branch.
- Weekly run 42418042712 succeeded again. It reported the week as already frozen and left the file
  unchanged: the branch still has a single freeze commit.
- The site shows 4,999 packages, not 5,000: two names in the list normalise to the same PEP 503
  name and are merged.
- Browser check on the live site: desktop light, phone width (375px) dark, no sideways scroll,
  no third-party requests (all resources from the site's own host), simulator search normalises
  names, and the package filter counts match the data (820 quiet, 2,294 few active contributors,
  328 unknown).
- Not yet seen: a run started by the schedule itself. The first is due Monday 2026-11-09, and
  GitHub often starts these late.
