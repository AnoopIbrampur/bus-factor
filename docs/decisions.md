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
