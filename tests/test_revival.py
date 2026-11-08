"""Checks for the D22 revival test: who is eligible, the label, and point-in-time features."""

from datetime import date

import numpy as np
import pandas as pd

from busfactor import revival
from busfactor.config import TEST_CUTOFFS
from busfactor.health import day_number

CUT = date(2023, 11, 1)
T = day_number(CUT)
COLS = ["repo_key", "day", "person", "n", "m"]


def frame(rows):
    return pd.DataFrame(rows, columns=COLS)


NO_RELEASES = pd.DataFrame({"repo_key": pd.Series(dtype=str), "day": pd.Series(dtype=int)})


def test_only_quiet_repos_with_history_are_eligible_and_labels_follow_commits():
    rows = frame(
        [
            ("active", T - 10, 0, 1, 0),
            ("quiet_back", T - 500, 0, 1, 0),
            ("quiet_back", T + 100, 1, 1, 0),
            ("quiet_stays", T - 600, 0, 1, 0),
            ("quiet_bot_only", T - 700, 0, 1, 0),
            ("quiet_bot_only", T + 50, -1, 5, 0),
            ("late", T - 400, 0, 1, 0),
            ("late", T + 366, 0, 1, 0),
        ]
    )
    p = revival.panel_row(rows, CUT, NO_RELEASES).set_index("repo_key")
    assert "active" not in p.index
    assert p["revived"].to_dict() == {
        "late": 0,
        "quiet_back": 1,
        "quiet_bot_only": 0,
        "quiet_stays": 0,
    }


def test_extra_features_ignore_anything_after_the_cutoff():
    rows = frame([("r", T - 500, 0, 1, 0), ("r", T - 30, -1, 4, 0)])
    rel = pd.DataFrame({"repo_key": ["r", "r", "r"], "day": [T - 20, T - 20, T - 10]})
    a = revival.panel_row(rows, CUT, rel).set_index("repo_key")
    more_rows = pd.concat([rows, frame([("r", T + 5, -1, 9, 0)])], ignore_index=True)
    more_rel = pd.concat([rel, pd.DataFrame({"repo_key": ["r"], "day": [T + 3]})])
    b = revival.panel_row(more_rows, CUT, more_rel).set_index("repo_key")
    assert a.loc["r", "releases_365d"] == 2 and a.loc["r", "bot_commits_365d"] == 4
    pd.testing.assert_frame_equal(a, b)


def synthetic(n_repos: int = 160, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    lo, hi = day_number(date(2013, 1, 1)), day_number(date(2026, 11, 7))
    rows, rels = [], []
    for r in range(n_repos):
        key = f"r{r:03d}"
        day = int(rng.integers(lo, day_number(date(2018, 1, 1))))
        while day <= hi:
            rows.append((key, day, int(rng.integers(0, 3)), 1, 0))
            if rng.random() < 0.3:
                rels.append((key, day + 3))
            # Mostly short gaps, sometimes a long silence that may or may not end.
            day += int(rng.choice([5, 30, 500, 900], p=[0.6, 0.3, 0.07, 0.03]))
    return frame(rows), pd.DataFrame(rels, columns=["repo_key", "day"])


def test_walk_forward_scores_every_test_year_and_never_trains_on_open_outcomes():
    rows, rel = synthetic()
    panel = revival.build_panel(rows, rel)
    makers = {k: revival.MAKERS[k] for k in ("logistic", "days_since_human", "releases_365d")}
    preds = revival.walk_forward(panel, makers)
    assert set(preds["cutoff"]) == {c.isoformat() for c in TEST_CUTOFFS}
    test = TEST_CUTOFFS[1]
    t = day_number(test)
    keys = sorted(rows["repo_key"].unique())[::2]
    later = pd.concat([rows, frame([(k, t + 20, 0, 3, 0) for k in keys])], ignore_index=True)
    moved = revival.walk_forward(revival.build_panel(later, rel), makers)
    a = preds[preds["cutoff"] == test.isoformat()].reset_index(drop=True)
    b = moved[moved["cutoff"] == test.isoformat()].reset_index(drop=True)
    for name in makers:
        np.testing.assert_allclose(a[name], b[name])
