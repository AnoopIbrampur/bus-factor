# Launch notes

## Resume bullets
- Built **Internet Bus Factor**, a public site that maps maintainer concentration across the top
  5,000 PyPI packages (about 6,000 git histories, 14.6k dependency edges) and forecasts which
  projects go quiet. Live on GitHub Pages and refreshed weekly by GitHub Actions at zero cost.
- Designed a **pre-registered, survivor-bias-aware backtest**. The cohort came from a 2022
  Postgres archive restored on CI runners, with walk-forward evaluation and repo-clustered
  bootstrap CIs. LightGBM beat the best baseline (log loss 0.299 vs 0.344, ROC-AUC 0.87 vs 0.82).
- Added a **survival analysis** layer, a discrete-time hazard model with censoring-safe
  walk-forward training. It passed a second pre-registered test (log loss 0.348 vs 0.399 across
  four horizons), and its long-horizon under-calibration is published openly. Also shipped an
  in-browser **dependency-tree checker** for `requirements.txt` and `pyproject.toml`.
- Enforced **point-in-time correctness** with leakage tests, and launched a **public prediction
  record**: weekly forecasts frozen to an append-only git branch before outcomes, graded after
  12 months.
- Built a **privacy-preserving** git pipeline: in-memory salted hashing, no personal data stored
  or published, encrypted state. Included **safety-first design** with no weakness rankings.

## LinkedIn post draft
> Much of Python rests on very few people. I wanted to measure that, and to test whether you can
> forecast which projects go quiet.
>
> Internet Bus Factor maps the 5,000 most downloaded PyPI packages. In half of those with readable
> history, one person made at least half of last year's commits. A simulator shows what depends on each package.
>
> The forecast was tested on four past years using a 2022 snapshot, to avoid only studying
> survivors. The pass rule was committed to git before I looked at any result. It passed:
> 0.87 ROC-AUC against 0.82 for the best simple rule. Forecasts are now frozen weekly in public,
> to be graded a year from now.
>
> The humbling part: about 4 in 10 projects that go a year without a commit come back. Quiet
> isn't abandoned, and maintainers owe nobody free labour. The site is about where help should
> go, so it has no "weakest projects" list and publishes no names.
>
> Site: https://anoopibrampur.github.io/bus-factor/
> Code and every decision: https://github.com/AnoopIbrampur/bus-factor
>
> Built on ecosyste.ms open data (CC-BY-SA). Related work: OpenSSF Criticality Score and
> Scorecard, and the Harvard and Linux Foundation census studies.
