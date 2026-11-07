"""The fairness of the backtest rests on these checks, not on anyone's good intentions."""

from datetime import date

import numpy as np
import pandas as pd

from busfactor.config import HORIZON_DAYS, TEST_CUTOFFS, TRAIN_CUTOFFS
from busfactor.forecast import (
    log_loss_each,
    paired_cluster_ci,
    panel_row,
    train_cutoffs_for,
)
from busfactor.health import day_number


def test_no_training_outcome_overlaps_a_test_date():
    for test in TEST_CUTOFFS:
        for c in train_cutoffs_for(test):
            assert (test - c).days >= HORIZON_DAYS


def test_training_rows_exist_for_every_fold():
    assert all(len(train_cutoffs_for(t)) >= 3 for t in TEST_CUTOFFS)
    assert max(TRAIN_CUTOFFS) < TEST_CUTOFFS[-1]


def test_last_outcome_window_is_complete_on_the_build_date():
    assert (date(2026, 11, 7) - TEST_CUTOFFS[-1]).days >= HORIZON_DAYS


def frame(rows):
    return pd.DataFrame(rows, columns=["repo_key", "day", "person", "n", "m"])


CUT = date(2023, 1, 1)
T = day_number(CUT)


def test_outcome_labels_and_eligibility():
    rows = frame(
        [
            ("goes_quiet", T - 10, 0, 5, 0),
            ("stays", T - 10, 0, 5, 0),
            ("stays", T + 100, 0, 1, 0),
            ("late_return", T - 10, 0, 5, 0),
            ("late_return", T + HORIZON_DAYS + 1, 0, 1, 0),
            ("bot_only_after", T - 10, 0, 5, 0),
            ("bot_only_after", T + 20, -1, 9, 0),
            ("already_quiet", T - 500, 0, 5, 0),
        ]
    )
    p = panel_row(rows, CUT).set_index("repo_key")
    assert "already_quiet" not in p.index
    assert p.loc["goes_quiet", "quiet"] == 1
    assert p.loc["stays", "quiet"] == 0
    assert p.loc["late_return", "quiet"] == 1
    assert p.loc["bot_only_after", "quiet"] == 1


def test_label_is_not_a_feature():
    """A commit after the cutoff must change the label and nothing else."""
    a = frame([("r", T - 10, 0, 5, 0)])
    b = frame([("r", T - 10, 0, 5, 0), ("r", T + 30, 0, 5, 0)])
    pa, pb = panel_row(a, CUT), panel_row(b, CUT)
    assert pa["quiet"].iloc[0] == 1 and pb["quiet"].iloc[0] == 0
    pd.testing.assert_frame_equal(pa.drop(columns="quiet"), pb.drop(columns="quiet"))


def test_strict_outcome_needs_no_release():
    rows = frame([("a", T - 10, 0, 5, 0), ("b", T - 10, 0, 5, 0)])
    rel = pd.DataFrame({"repo_key": ["a"], "day": [T + 5]})
    p = panel_row(rows, CUT, rel).set_index("repo_key")
    assert p.loc["a", "quiet_strict"] == 0 and p.loc["b", "quiet_strict"] == 1


def test_bootstrap_sees_a_real_gain_and_clusters_by_repo():
    n = 400
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, n)
    df = pd.DataFrame(
        {
            "repo_key": np.arange(n).astype(str),
            "y": y,
            "good": np.where(y == 1, 0.8, 0.2) + rng.normal(0, 0.15, n).clip(-0.19, 0.19),
            "bad": 0.5,
        }
    )
    gain, lo, hi = paired_cluster_ci(df, "good", "bad", reps=300)
    assert lo > 0 and lo < gain < hi
    # Copying each repo four times adds no information, so the interval must not shrink much.
    four = pd.concat([df] * 4, ignore_index=True)
    _, lo4, hi4 = paired_cluster_ci(four, "good", "bad", reps=300)
    assert (hi4 - lo4) > 0.8 * (hi - lo)


def test_log_loss_of_a_coin():
    assert abs(log_loss_each(np.array([1.0]), np.array([0.5]))[0] - 0.6931) < 1e-3
