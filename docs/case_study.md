# Case study: Internet Bus Factor

![Home page of the live site](screenshot.png)

**Live:** https://anoopibrampur.github.io/bus-factor/ · **Code:** https://github.com/AnoopIbrampur/bus-factor

## The question
Python's most used packages are free, and many depend on one or two volunteers. When one of them
stops, or is pressured, everyone downstream feels it: left-pad (2016), event-stream (2018),
colors and faker (2022), and the xz backdoor (2024), where an attacker spent about two years
earning a lone maintainer's trust. I wanted to answer three things in public. Which widely used
packages rest on very few people? What depends on them? Can we forecast which will go quiet,
in a way that gets checked?

## What I built
- A map of the top 5,000 PyPI packages: 3,847 repos, about 6,000 git histories, and a
  dependency graph with 14,642 edges.
- Health measures from full git history, recomputable at any past date: active people, bus
  factor, concentration, trend, time since the last human commit, and handovers.
- A failure simulator with a static, shareable page for every package.
- A forecast of "no human commit in the next 12 months", tested walk-forward on four past years
  and now frozen weekly in public before outcomes exist.

## Hard parts and how I handled them
**Survivor bias.** Today's top list only contains survivors. I took the cohort from an
ecosyste.ms archive dated 2022-11-09. It's a 9 GB Postgres custom-format dump, so I streamed it
through `pg_restore` on a GitHub runner, with no database server. 839 cohort packages had no repo
link in 2022, and 102 repos were gone by 2026. I report both and a worst-case base rate.

**Point-in-time correctness.** Every feature comes from one function that drops commits after the
cutoff before doing anything. Tests inject future commits and fail if any value moves. Training
rows are only used when their 12-month outcome had finished by the test date, and a test checks
that too.

**Pre-registration.** The outcome, the comparison, the metric and the pass rule were committed
(`180fd73`) before any model was scored. I also caught and disclosed my own bug after the result:
the model-saving code had no branch for the winning model. The fix changed no numbers, a re-run
reproduced the result, and both runs are in the model card.

**Privacy and safety.** Emails are hashed in memory with a throwaway salt and replaced by a
per-repo number. No names, usernames or repo links are published, because a personal repo URL
contains a username. The site has no ranking by weakness and no way to combine "looks quiet" with
"few active contributors", and frozen forecasts are sorted by hash. That's the profile the xz
attacker searched for, and the site shouldn't make it easier to find.

**Running on free infrastructure.** All heavy work runs on GitHub Actions: 6 resumable shards
clone about 6,000 repos in under 15 minutes with `--filter=tree:0`. State lives as release
assets, the URL map is encrypted, and a keep-alive step stops GitHub from switching off the
weekly schedule.

## Results
- **Concentration:** in 50% of the 4,671 packages with readable history, one person made at
  least half of the past year's human commits. Among the top 100 packages, it's 57.
- **Forecast:** LightGBM on git features beat the best simple rule (past-year commits). Log loss
  was 0.299 against 0.344, with gain CI 0.039 to 0.052. ROC-AUC was 0.87 against 0.82, and
  calibration was close across all tenths. It passed the pre-registered rule, and both the
  logistic and LightGBM models beat both baselines in every test year.
- **The humbling part:** about 4 in 10 projects that went a year without a human commit later had
  one again. Half of a hand-checked sample that stayed quiet looked finished. "Quiet" is not
  "abandoned", and the site says so everywhere.
- **Compared with OpenSSF Criticality Score** (one year, 1,474 repos), the model ranked quiet
  projects better (ROC-AUC 0.85 against 0.72). Criticality measures importance, not quiet, so
  the two answer different questions.

## What I'd do next
- Grade the first live week in November 2027, and see whether backtest skill holds.
- Add issue and review activity as point-in-time features. They're absent today because only
  current snapshots were free.
- Extend to npm once the PyPI record is stable.

## Stack
Python 3.12, uv, pandas, DuckDB and Parquet, scikit-learn, LightGBM, httpx, Jinja2, pytest, ruff,
GitHub Actions and Pages. Fonts are self-hosted, and the site uses about 30 lines of JavaScript.
