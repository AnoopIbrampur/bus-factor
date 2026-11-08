# Model card: chance a project goes quiet

## What it predicts
The chance that a repo with at least one human commit in the past year gets **no human commit on
its default branch in the next 365 days**. That is all it predicts. A quiet year is often a pause
(about 4 in 10 quiet projects came back later; see docs/data_audit.md), and it can mean finished
software. It is not a prediction of abandonment, insecurity or compromise.

## Published model
LightGBM (200 trees, 8 leaves, learning rate 0.03, fixed in advance), on 16 git-history features
(`health.FEATURES`), with Platt calibration on the latest training year. It was chosen by the
rule pre-registered in D13 (commit 180fd73, pushed 2026-11-07 21:30 UTC, before any result).
Per-project reasons are its own feature contributions (TreeSHAP), worded in plain language and
shown only when the chance is 10% or more. They are statistical associations, not causes.

## Test design
- Cohort: top 5,000 PyPI packages by downloads in the ecosyste.ms archive of 2022-11-09, which
  map to 3,684 repos. 3,582 could be read.
- Walk-forward by year. Test cutoffs 2022-11-09, 2023-11-01, 2024-11-01, 2025-11-01. Training
  only on cutoffs whose 12-month outcome had finished by the test date.
- 9,568 test rows (repo-years), 1,485 quiet (15.5%).
- Baselines turned into probabilities by one-feature logistic fits through the same pipeline.
- 95% CIs from 2,000 bootstrap resamples of repos.

## Results (pooled test years, run 42416663376)

| Method | Log loss | Brier | ROC-AUC | PR-AUC | Quiet share in top tenth |
|---|---|---|---|---|---|
| **LightGBM (published)** | **0.299** | **0.096** | **0.872** | **0.508** | **55%** |
| Logistic regression | 0.306 | 0.098 | 0.863 | 0.489 | 54% |
| Commits in past year (best baseline) | 0.344 | 0.108 | 0.815 | 0.405 | 47% |
| Days since last commit | 0.346 | 0.107 | 0.814 | 0.415 | 48% |

| Comparison (log-loss gain) | Gain | 95% CI |
|---|---|---|
| Logistic vs best baseline | 0.038 | 0.032 to 0.044 |
| LightGBM vs logistic | 0.007 | 0.005 to 0.010 |
| LightGBM vs best baseline | 0.045 | 0.039 to 0.052 |

**Pass rule met.** Every year, both models beat both baselines:

| Test year | Rows | Quiet | LightGBM | Logistic | Past-year commits | Last commit |
|---|---|---|---|---|---|---|
| 2022-11-09 | 2,670 | 360 | 0.268 | 0.272 | 0.310 | 0.310 |
| 2023-11-01 | 2,522 | 413 | 0.314 | 0.323 | 0.351 | 0.362 |
| 2024-11-01 | 2,280 | 372 | 0.299 | 0.309 | 0.350 | 0.356 |
| 2025-11-01 | 2,096 | 340 | 0.319 | 0.327 | 0.372 | 0.359 |

(LightGBM log losses per year are from the first run; see reproducibility below.)

**Calibration (LightGBM, tenths of test rows):** stated 0.1% / 0.3% / 0.7% / 1.7% / 3.9% / 8.1%
/ 15.4% / 26.2% / 40.0% / 57.4%, observed 0.0% / 0.0% / 0.9% / 1.9% / 4.0% / 8.2% / 18.0% / 26.6%
/ 40.6% / 55.1%. Close throughout, with the 15% tenth slightly under-predicted.

**Secondary outcome** (quiet and no PyPI release): LightGBM log loss 0.287 against 0.333 for the
best baseline (last commit date). The same direction.

**OpenSSF Criticality Score** (2025-11-01 fold only, the 1,474 repos it covers, 212 quiet):
ROC-AUC 0.850 for the logistic model and 0.718 for the score. Difference 95% CI 0.097 to 0.168.
Criticality Score measures importance, not quiet, so this shows the two tools answer different
questions. It is not a criticism of that project.

## Reproducibility
The backtest ran twice: run 42416215467 and run 42416663376 (re-run after the D16 bug fix).
Logistic and baseline numbers match to floating-point noise. LightGBM differs in the fourth
decimal (pooled log loss 0.2987 then 0.2989; gain over logistic CI 0.0047–0.0101 then
0.0045–0.0099), because multithreaded LightGBM isn't bit-for-bit reproducible. Every pass
decision is the same in both runs. The live model is the one from the second run.

## What is still biased or unknown
- **Survivor bias, reduced, not removed.** 839 cohort packages had no repo link in 2022 and can't
  be tested. 102 cohort repos couldn't be cloned in 2026. If those all went quiet in every test
  year, the quiet rate would be 19.0% instead of 15.5%. Training years before 2022 use projects
  chosen for being popular in 2022.
- **Finished vs unattended:** not separable from git. See the hand check.
- **Git dates are not push dates,** so a few commits look earlier than they became public.
- **Archive status and open issues** are today's values, so they're kept out of the features.
- **Identity merging uses the full history** (D17). A later commit can link two earlier
  identities, so past headcounts can be slightly lower than they looked at the time.
- **Live record:** no graded weeks yet. The first frozen week (named 2026-11-02, frozen
  2026-11-07) is due for grading on 2027-11-07. Backtest skill doesn't guarantee live skill.

## Second model: how long a project may stay silent (D18, D20)
- **What:** S(h), the chance of no human commit for h = 90, 180, 365 or 730 days after a date.
  A discrete-time hazard over four intervals, with D13's features plus the interval.
- **Published:** LightGBM hazard, with no calibration step. Fitted on every cutoff, with outcomes
  seen up to the pinned date 2026-11-07. Stored in `survival_model.json`.
- **Result:** pooled log loss 0.348 against 0.399 for the best simple method (past-year commits).
  Gain CI 0.045 to 0.057. It wins at every horizon and in every fold.
- **Known weakness:** under-calibrated at long horizons. In the top tenth at 2 years, it said 33%
  and 46% stayed silent. At 12 months it is slightly worse than the D13 model (0.3025 against
  0.2987), which is why the frozen 12-month forecast stays D13's.
- **Not graded live.** Curves aren't in the frozen weekly files.

## Recalibration attempt (D21, D24)
A Platt step on the latest training cutoff fixed most of the curve's low top-tenth numbers. At
2 years it said 42% against 45% observed, where the D18 curve said 33%. Its pooled log loss gain
(0.0015, CI −0.0002 to 0.0032) didn't clear zero, so the D18 curve stays, as pre-registered.

## Third model: will a quiet project come back? (D22, D25)
- **What:** among repos with no human commit in the past year, the chance of one within the
  next 12 months.
- **Published:** logistic regression on the 16 git features plus releases and bot commits in the
  past year, Platt-calibrated.
- **Result:** log loss 0.4016 against 0.4052 for days since the last commit, with a gain CI of
  0.0011 to 0.0062. ROC-AUC 0.735 against 0.729. LightGBM did worse than both.
- **Base rate:** 14% to 22% came back within a year, depending on the test year.
- **Known weakness:** almost all of the signal is the length of the silence. Training years
  before 2022 come from a cohort chosen for being popular in 2022, which over-represents returns.
  That can only hurt test performance.

## Intended use
To help decide where help and funding should go. Not for judging people. Not for finding projects
to target. The site has no ranking by this score.
