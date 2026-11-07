# Decisions

Numbered decisions with the reasoning. Entries are added, not rewritten. A rule changed after
seeing results gets a dated note and keeps its original text. The git history of this file is
the proof of what was decided when.

## D1. The repo is the unit of analysis (2026-11-07)
Several hundred packages share a few repos (the largest repo backs 139 of the top 5,000). People
maintain repos, not package names. If packages were the unit, a few monorepos would dominate the
forecast and its error bars would be too narrow. So health and forecasts are per repo, and every
package in that repo shows the same numbers. Cost: a monorepo's activity may not touch the
particular package you care about. The package page says so.

## D2. The top 5,000 are chosen by downloads alone (2026-11-07)
Last-month downloads from ecosyste.ms, descending, taken from the list API. The rule looks at no
health or outcome signal. Download counts include CI and mirrors, so this is a measure of use by
machines, not of people. Packages whose repo can't be found stay in the list as "unknown".

## D3. No usernames anywhere, including in URLs (2026-11-07)
A repo URL on a personal account contains a username, and so can a funding link. So the site
links to PyPI project pages, never to repos or funding links. It says only whether a project
declares a funding link. Release assets and public logs use a hashed `repo_key`. The URL map lives
only in an AES-encrypted release asset (key in the repo secret `BF_STATE_KEY`), because the
cohort's 2022 URLs have to be kept somewhere to allow re-runs. Owner kind (person or organisation)
is used for one aggregate count and is never published per project.

## D4. Author identity stays in memory (2026-11-07)
Emails and names are hashed with a salt made fresh for each repo, merged into a per-repo index
(0, 1, 2 ...) and discarded. Only the index is stored. Stored salted hashes would add nothing,
since the salt changes per run, and the index gives away less. All bots are pooled under one id.

## D5. Git dates use the committer date (2026-11-07)
Git records no push date. The committer date is closest to when a change landed. A commit made on
a branch and merged later keeps its older date, so history as seen at date t can include a few
commits that were not yet public then. A repo whose history was rewritten shows most of its
committer dates collapsed onto a few days; for those, the author date is used instead.

## D6. Default branch only, tree-less clones (2026-11-07)
`git clone --bare --filter=tree:0 --single-branch --no-tags`. That brings commits without file
contents. It means commits can't be filtered by path, so monorepo activity can't be split per
package, and commits that only touch docs or CI count the same as code. Merge commits count as
activity of the person who made them.

## D7. OpenSSF criticality is only comparable in the last test year (2026-11-07)
Historical scores can no longer be downloaded (data audit, surprise 2). The only scored list that
is both obtainable and dated before a test cutoff is 2025-07-25, which can be used for the
2025-11-01 cutoff only. Using it on earlier cutoffs would leak the future. So it is compared on
that one year, on the repos it covers, and reported separately.

## D8. Bus factor means half of recent human commits (2026-11-07)
The fewest people who made at least half of the human commits on the default branch in the past
365 days. It is a simple measure that anyone can check. Authors count, not committers, because web
merges show GitHub as the committer. Commits are a thin proxy for work: they miss review, triage,
releases and support. All of these measures are computed by one function that sees only rows
dated up to t, so any measure can be recomputed at any past date.

## D9. Graph comes from PyPI metadata, required dependencies only (2026-11-07)
deps.dev looked incomplete in earlier tests and the 2026-02 archive is 64 GB and dated. PyPI's JSON
API gives `requires_dist` for each package's latest release. Extras are dropped (a choice, not a
need). Environment markers are kept (the dependency applies to someone). The graph stops at the
top 5,000, so indirect counts are floors. Downloads behind a package overlap heavily, so the site
shows the largest single dependent next to the sum and labels the sum as overlapping.

## D10. What the site lets you sort and filter (2026-11-07)
Tables sort by downloads or reach only, never by health or forecast. The package list has one
"Show" menu, so "looks quiet" and "few active contributors" can't be combined. The home list is
limited to active projects, ordered by what depends on them, and framed around where help reaches
furthest. Owner type (person or organisation) is not shown or filterable per project. All of this
is public information anyway, but the brief is clear that this site must not make a target list
easier to build, so convenience loses.

## D11. Labels describe commits only (2026-11-07)
Active, Slowing down (human commits at least halved, year on year, with 10 or more the year
before), Looks quiet (no human commit in 365 days), Archived by its owners, Unknown. Never
"abandoned", "unsafe" or "at risk". Archive status is today's flag from ecosyste.ms, so it isn't
used in the backtest, where it would leak the future.

## D12. Keep the forecast cohort fixed from the 2022-11-09 snapshot (2026-11-07)
The top 5,000 by downloads in the archive, by the same rule as D2. Test cutoffs are on or after
the snapshot date: 2022-11-09, 2023-11-01, 2024-11-01, 2025-11-01. Earlier yearly cutoffs (Nov 1,
2017 to 2021, plus 2022) are training rows only, and they carry some survivor bias because those
projects were chosen for being popular in 2022. Training rows must have a finished outcome by the
test date. Later test years use a cohort that is ageing: it can't include projects that became
popular after 2022.
