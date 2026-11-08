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

## D13. PRE-REGISTERED forecast test (2026-11-07, committed before any forecast result)
Written after the outcome hand check in docs/data_audit.md, which looked at labels only. No model
had been fitted or scored on real data when this was committed.

**Unit and sample.** One row per repo per cutoff. Repos from the D12 cohort, eligible at a cutoff
if they had at least one human commit in the 365 days before it.

**Primary outcome (`quiet`).** No human commit on the default branch in the 365 days after the
cutoff. Bots are excluded by the D4/people.py filter.

**Secondary outcome (`quiet_strict`).** Quiet, and no PyPI release from any of the repo's cohort
packages in the same window. Reported, never used for the pass rule.

**Features.** The 16 git measures in `health.FEATURES`, computed by `health.measures_at` at each
cutoff. Nothing else.

**Candidates.**
1. Logistic regression (L2, C=1, standardised, counts on log scale), the primary model.
2. LightGBM, small and fixed (200 trees, 8 leaves, learning rate 0.03), the challenger.
3. Baselines, each a one-feature logistic fit through the same pipeline: (a) days since last
   human commit, (b) human commits in the past year.
All are calibrated by Platt scaling on the latest training cutoff. Hyperparameters are the ones in
`forecast.py` at this commit. There is no tuning.

**Walk-forward.** Test cutoffs 2022-11-09, 2023-11-01, 2024-11-01, 2025-11-01. Training cutoffs are
Nov 1 of 2017 to 2024, used only if cutoff + 365 days is on or before the test cutoff.

**Primary metric.** Mean log loss over all test rows pooled across the four years.

**Comparison.** Best baseline = the baseline with the lower pooled test log loss (the harder
opponent, chosen after the fact on purpose). Difference = baseline log loss minus model log loss.
95% CI from 2,000 bootstrap resamples of repos (clusters), seed 0, pairing each repo's rows across
years.

**Pass rule.** The logistic model passes if the CI's lower bound is above zero. LightGBM is
adopted instead only if it beats the logistic model and the best baseline, both with CI lower
bounds above zero. If nothing passes, the site publishes the best baseline's calibrated
probabilities, and says plainly that the model didn't beat it.

**Also reported, not deciding.** ROC-AUC, PR-AUC, Brier, share quiet in the top tenth, per-year
results, calibration by tenths, the secondary outcome, and the sensitivity case where every
unreadable cohort repo counts as quiet. OpenSSF criticality is compared by ROC-AUC on the
2025-11-01 fold only, on repos its 2025-07-25 list covers, with lower score taken as more likely
quiet (D7). It can't enter the log-loss rule because it has no history to calibrate on.

**What a result would mean.** A pass means git history adds a little over "when was the last
commit". It doesn't mean the model can tell finished from unattended projects (the hand check says
nothing here can).

## D14. Display bands for chances (2026-11-07, before any result)
Lower chance: under 10%. Middle chance: 10% to under 30%. Higher chance: 30% or more. Fixed now so
they can't be chosen to flatter the results. Colour always comes with the words.

## D15. Live record scoring rules (2026-11-07, before the first freeze)
- The weekly job scores every repo of today's top 5,000 that had a human commit in the past 365
  days and isn't archived, with the model and baseline fitted once by the backtest job. The job
  never refits.
- The first run of each week (named by its Monday) writes `predictions/<Monday>.json.gz` to the
  `predictions` branch. An existing file is never replaced. The job refuses any commit to that
  branch other than a new file.
- Each file is graded once 365 days after its freeze date have passed: quiet means no human commit
  on the default branch in (freeze date, freeze date + 365 days], using the harvest at grading time.
- Metric: mean log loss, for the published forecast and for the baseline frozen next to it.
  Repos whose history can't be read at grading time are left out and counted.
- The live record is reported apart from the backtest and never pooled with it.
- Any change to these rules gets a dated note here and applies only to weeks frozen after it.

## D16. Result of the D13 test, and a bug fixed after it (2026-11-07)
The test ran once (Actions run 42416215467) on the pre-registered rules. The logistic model beat
the best baseline (past-year commits) with a CI above zero, and LightGBM beat both the logistic
model and the baseline with CIs above zero. **Under D13, LightGBM is the published model.**
Numbers are in docs/model_card.md.

Bug, found after the result: the code that saves the live model had no LightGBM branch, so it
saved a one-feature model under LightGBM's name. No rule, feature, hyperparameter or number in
backtest.json changed. The fix adds a stored form of LightGBM and per-project reasons from its own
feature contributions (TreeSHAP), and adds calibration tables for every candidate to the report.
The backtest was then re-run unchanged to produce the corrected model file, and the two runs were
compared.

Addendum (2026-11-07): logistic and baseline numbers matched exactly. LightGBM did not: it moved in
the fourth decimal, because multithreaded LightGBM isn't bit-for-bit reproducible. Every pass
decision held. Both runs are in docs/model_card.md.

## D17. Privacy fixes and a disclosed point-in-time gap, found in final review (2026-11-07)
1. **Public files that could rebuild a target list.** `site_packages.parquet`, the per-commit
   rows, the backtest panel and the backtest predictions were plain release assets. Combined, any
   of them can be sorted into the "few people and quiet" list D10 keeps off the site. All are now
   encrypted (`.enc`), and the plain copies were deleted. What stays public on purpose: the frozen
   weekly forecasts on the `predictions` branch. A public record has to be checkable, so anyone
   can sort it. The hash order only slows that down.
2. **Identity merging sees the whole history.** `aggregate()` merges author identities, and
   checks for rewritten histories, using the full 2026 clone. A commit made after a cutoff can
   therefore link two identities from before it. That makes past headcounts slightly lower than
   they would have looked at the time. The effect is likely small (it needs one person to change
   email or name and later commit under both), but it is a real point-in-time gap. The tests
   start from aggregated rows, so they can't catch it. D13 is not changed. This is disclosed in
   the model card.
3. **Grading as published.** `grade()` now grades only repos read successfully on or after the
   due date, as D15 says. Before this fix, a deleted repo would have kept its old rows and been
   graded as quiet. No week was graded before the fix.

## D18. PRE-REGISTERED "how long" test (2026-11-08, committed before any survival result)
Written before any survival code ran on real data. Nobody has looked at survival curves,
Kaplan–Meier tables, or hazards from the real harvest. Synthetic-data unit tests are the only runs.

**Question.** How long will a project go without a human commit? D13 answers this only for
12 months, as yes or no. This test asks for a whole curve.

**Event.** The next human commit on the default branch after the cutoff, with bots excluded as in
D4. S(h) = chance of no human commit in (t, t+h]. S(365) is exactly D13's `quiet`.
- Why this definition and not "time until a year-long silence starts": that event can only be seen
  up to D − 365, so it would lose most test folds. It also has no clean link to D13.
- Worked example. Cutoff 2023-11-01, next human commit 2024-02-10 (101 days later). The project is
  silent through h = 90 and not through 180, 365 or 730.

**Data, pinned.** As-of date D = 2026-11-07 (the harvest D13 used).
- Rows are filtered to `day <= D`.
- Only repos whose latest read succeeded on or after D are used.
- The first run copies its inputs to dated release assets (`survival-*`), and every later run reads
  those copies. The weekly harvest therefore can't change the answer.
- Same D12 cohort and D13 eligibility: at least one human commit in the 365 days before the cutoff.
  Features: the 16 `health.FEATURES`, from `measures_at`.

**Model form.** A discrete-time hazard over four intervals: (0,90], (90,180], (180,365], (365,730]
days.
- A repo-cutoff contributes one row per interval it enters while still silent.
- Each row's label is whether the first human commit falls inside that interval.
- S(h) is the product of (1 − hazard) over the intervals up to h.

**Censoring, and the leakage rule.**
- For test cutoff T, a training row from cutoff c uses only commits on or before T.
- Its interval k is used only if c + end_k ≤ T. Later intervals are dropped.
- A test enforces this: adding a commit after T to a training repo must leave the predictions for
  that test cutoff unchanged.
- Test labels use commits up to D. Each (fold, horizon) is scored only if T + h ≤ D, so no
  censoring weights are needed.

**Folds and horizons.**
- Test cutoffs as in D13: 2022-11-09, 2023-11-01, 2024-11-01, 2025-11-01.
- Horizons 90, 180 and 365: all four folds. Horizon 730: the first three folds.
- Training cutoffs as in D13 (Nov 1 of 2017–2024), each with the interval rule above.

**Candidates.** Same pipeline, no tuning, no Platt step. A hazard model has no clean calibration
year, so none of the candidates get one.
1. Logistic hazard: L2, C=1, standardised, D13 log-scale features, plus interval dummies. The
   primary candidate.
2. LightGBM hazard: D13 hyperparameters, with the interval index as an extra feature. The
   challenger.
3. Baselines:
   - (a) Kaplan–Meier style: each interval's hazard taken from training rows, with no features.
   - (b) and (c) one-feature logistic hazards on `days_since_human` and on `commits_365d`, each
     with interval dummies.

**Metric and comparison.**
- Each test (repo, cutoff, horizon) is one scored item: y = 1 if silent through h, p = S(h).
- Primary metric: mean log loss over all items pooled.
- Best baseline: the baseline with the lowest pooled log loss, chosen after the fact on purpose.
- 95% CI on the difference from 2,000 bootstrap resamples of repos, seed 0, pairing all of a repo's
  items.

**Pass rule.**
- The logistic hazard passes if the CI's lower bound is above zero against the best baseline.
- LightGBM is adopted instead only if it beats both the logistic hazard and the best baseline, each
  with a CI lower bound above zero.

**Also reported, not deciding.**
- Log loss, Brier and ROC-AUC at each horizon and fold.
- Calibration by tenths at each horizon.
- At 365 days, the D13 LightGBM refitted in the same job on the same rows, for comparison.
  LightGBM isn't bit-for-bit reproducible, so this refit is not the live model.

**What the site shows.**
- **On a pass:** each package page gets a "how long it may stay silent" line with the adopted
  model's S at 3 months, 6 months and 2 years.
  - The 12-month point is left out. The only 12-month chance on the site stays the frozen D13/D15
    forecast, so there are never two 12-month numbers.
  - Displayed points are kept in order around that number: 3 and 6 months are shown as at least the
    12-month chance, and 2 years as at most it. The page marks any point that was adjusted, and the
    method page reports how often this happened.
  - Words follow D14 bands. "Unknown" stays unknown.
- **On a fail:** package pages show nothing new, and the method page says the curve didn't beat the
  baseline.
- **Either way:** survival numbers are not added to the frozen weekly files, and the D13 model and
  `models.json` are not touched. The survival job writes only its own files (`survival.json`,
  `survival_model.json`).

## D19. The dependency checker (2026-11-08)
A page where someone pastes their own `requirements.txt` or `pyproject.toml` and sees how the
packages their project needs are kept going. It's built so it can't turn into the list D10 and
D17 keep off the site.

- **No all-packages health file.** Health comes from one small `p/<name>/data.json` per package.
  Each holds the same facts its page shows: activity, few active contributors, chance band, and
  its required dependencies. The page fetches these only for packages in the pasted list and the
  packages they need. The one shared file, `check/names.json`, is names only, in alphabetical
  order. This exposes no more than the package pages already do.
- **Ordered by depth, then name, never by health.** Summary counts are shown. There is no
  "worst first" view and no filter combining quiet with few people.
- **Limited to 100 named packages per check.** That covers a project's own list, and makes
  pasting the whole top 5,000 tedious. It's a speed bump, not a wall. The packages page already
  shows the same facts one at a time.
- **Unknown is never healthy.** A name outside the top 5,000 shows as "not covered", and what it
  needs isn't followed. A package whose data won't load shows as unknown.
- **Parsing stays in the browser, and nothing is uploaded.** Requirements lines follow PEP 508
  names (PEP 503 normalised, as `deps.canon` does). Options, `-r`, `-e` and bare URLs are listed
  as unread. `pyproject.toml` support covers `[project].dependencies` and
  `[tool.poetry.dependencies]` only.
- **Dependencies come from each package's latest release (D9).** Required only, extras not
  followed, markers ignored.
