# Internet Bus Factor

**Live site: https://anoopibrampur.github.io/bus-factor/**

Which widely used PyPI packages rest on very few people, what depends on them, and which are
likely to go quiet? A public map, a failure simulator, and a forecast that is graded in public.

## Results

- **Few people carry a lot.** Of the 4,999 most downloaded PyPI packages, 4,671 have a git history
  we could read. In 2,322 of those (50%), one person made at least half of the past year's human
  commits. Among the top 100 packages it's 57. That includes packages hundreds of others depend
  on, such as idna, requests, python-dateutil and pyyaml.
- **The forecast passed its pre-registered test.** Over four past years (9,568 project-years from
  a 2022 cohort), a LightGBM model on git history predicted "no human commit in the next 12
  months" better than the best simple rule. Log loss was 0.299 against 0.344 (gain CI 0.039 to
  0.052) and ROC-AUC 0.87 against 0.82. The rule was committed before any result
  (commit `180fd73`).
- **A second pre-registered test, for "how long", also passed.** A discrete-time hazard model
  gives each project a curve: the chance of no human commit for 3 months, 6 months, 1 year and 2
  years. Pooled across horizons (36,176 scored predictions), LightGBM beat the best simple method,
  with log loss 0.348 against 0.399 (gain CI 0.045 to 0.057). Rules in D18, result in D20. The
  curve runs low at long horizons: at 2 years, the top tenth was told 33% and 46% stayed silent.
  The site says so.
- **Fixing the curve's low bias didn't clear the bar.** A pre-registered recalibration (D21)
  brought the 2-year top tenth from 33% said to 42%, against 45% observed. But its log loss gain
  (0.0015, CI −0.0002 to 0.0032) wasn't clearly above zero, so the original curve stays (D24).
- **Which quiet projects come back: barely predictable.** Within 12 months, about 1 in 6 quiet
  projects has a human commit again. A pre-registered model beat "days since the last commit"
  (log loss 0.402 against 0.405, CI on the gain 0.001 to 0.006), but nearly all of its signal is
  how long the silence has lasted (D22, D25).
- **npm, side by side.** Among npm's 100 most downloaded packages, 73% have one person making half
  of the commits, against 58% on PyPI. The median is 3.5 active people against 18. Across the
  top 5,000, a third of npm repos look quiet, against a fifth on PyPI. Many npm packages are
  tiny, single-purpose and finished, so read this as packaging style as much as risk (D23, D26).
- **Quiet is often a pause, not an end.** In a hand check and in the data, about 4 in 10 projects
  that went a year without a human commit later had one again. Git can't tell finished software
  from unattended software, and the site never claims it can.
- **Live record started.** The first week of forecasts is frozen on the
  [`predictions`](https://github.com/AnoopIbrampur/bus-factor/tree/predictions) branch. It gets
  graded from 2027-11-07. There is no live result yet.

## What's on the site
1. **Map:** the top 5,000 packages, their repos and their dependency graph.
2. **Health:** active people, bus factor, concentration, trend, time since the last human commit
   and handovers, with bots filtered out.
3. **Simulator:** pick a package and see its direct and indirect dependents and the downloads
   behind them. Every result has its own URL.
4. **Forecast:** the chance of no human commit in the next 12 months, with plain-language reasons
   and a weekly frozen record.
5. **How long it may stay silent:** on each package page, the chance of no human commit for 3
   months, 6 months and 2 years, next to the frozen 12-month forecast.
6. **Dependency checker:** paste a `requirements.txt`, `pyproject.toml` or npm `package.json`
   and see the health of everything your project needs, down the tree. Parsing happens in the
   browser, and nothing is uploaded.
7. **Will it come back?** Quiet packages show the chance of a human commit again within 12
   months.
8. **npm:** the top 5,000 npm packages with the same health measures and dependents, plus a
   PyPI-versus-npm comparison whose measures were fixed before any npm number was seen. There is
   no npm forecast, because the models were only tested on PyPI.

## How it works
- Data: ecosyste.ms (package list, 2022 archive via `pg_restore`), PyPI JSON (requirements,
  release dates), and full git history from tree-less clones (`--filter=tree:0`).
- Every measure is computed by one function that only sees commits dated up to the cutoff. Tests
  inject future commits and fail if anything changes.
- Heavy work runs on GitHub Actions: 6 parallel resumable shards clone about 6,000 repos in under
  15 minutes. State lives in a release, not in git.
- Weekly workflow: refresh, score, freeze into `predictions` (new files only), grade what's due,
  deploy Pages, keep the schedule alive.

## Honest limits
Commits miss reviews, triage, releases and support. Monorepos can't be split by package. 292
top packages have no repo we can read, and they show as unknown, never as healthy. The 2022
cohort still carries some survivor bias (docs/model_card.md). Downloads count machines, not
people.

## Safety and privacy
No names, emails or usernames are stored or published. Emails are hashed in memory with a
throwaway salt and replaced by a per-repo number. There are no repo links, because personal-account
URLs contain usernames. On the site, nothing can be sorted by health or forecast, and "looks
quiet" can't be combined with "few active contributors". Working data in releases is encrypted.
The frozen weekly forecasts are public, so anyone can sort them. A record that can't be checked
would be worthless. Maintainers owe nobody free labour. To ask for a
correction, [open an issue](https://github.com/AnoopIbrampur/bus-factor/issues).

## Related work
[OpenSSF Criticality Score](https://github.com/ossf/criticality_score),
[OpenSSF Scorecard](https://securityscorecards.dev) and the Harvard and Linux Foundation census
studies of open source already map critical projects. This project adds a dated, graded forecast
and a simulator anyone can use.

## Docs
[Decisions](docs/decisions.md) · [Data audit](docs/data_audit.md) · [Model card](docs/model_card.md)
· [Case study](docs/case_study.md) · [Launch notes](docs/launch.md)

## Run it
```bash
uv sync
uv run pytest
```
The pipeline commands are `busfactor plan | harvest | backtest | weekly | site`. See
`.github/workflows/`.

## Licence and credit
Code: MIT. Published data: CC-BY-SA 4.0, derived in part from [ecosyste.ms](https://ecosyste.ms)
open data (CC-BY-SA 4.0). Fonts: Spectral and Atkinson Hyperlegible (SIL OFL). A student
portfolio project, with no money involved.
