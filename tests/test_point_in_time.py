"""Rule 1 of this project: nothing dated after t may change a feature computed at t.

These tests build a small history, add commits after the cutoff, and require every measure to
stay identical. If someone removes the date filter, or adds a feature that looks ahead, they fail.
"""

from datetime import date

import pandas as pd
import pytest

from busfactor.health import FEATURES, bus_factor, day_number, measures_at, repo_measures

CUTOFF = date(2023, 6, 1)
T = day_number(CUTOFF)


def history() -> pd.DataFrame:
    rows = []
    for i in range(0, 900, 7):
        rows.append(("r1", T - i, i % 3, 1 + i % 2, 0))
    rows += [("r1", T - 5, -1, 4, 0), ("r2", T - 400, 0, 3, 0), ("r2", T - 800, 1, 1, 0)]
    return pd.DataFrame(rows, columns=["repo_key", "day", "person", "n", "m"])


def future(rows: pd.DataFrame) -> pd.DataFrame:
    extra = [
        ("r1", T + 1, 0, 50, 0),
        ("r1", T + 200, 9, 500, 3),
        ("r1", T + 3, -1, 7, 0),
        ("r2", T + 10, 5, 40, 0),
        ("r3", T + 10, 0, 40, 0),
    ]
    return pd.concat([rows, pd.DataFrame(extra, columns=rows.columns)], ignore_index=True)


def test_future_commits_change_nothing():
    base = history()
    a = measures_at(base, CUTOFF)
    b = measures_at(future(base), CUTOFF)
    pd.testing.assert_frame_equal(a, b)


def test_repo_measures_filters_on_its_own():
    """Even a caller who forgets to filter first can't leak the future."""
    base = history()
    r1 = base[base.repo_key == "r1"]
    r1f = future(base).query("repo_key == 'r1'")
    assert repo_measures(r1, T) == repo_measures(r1f, T)


def test_repo_born_after_cutoff_is_absent():
    assert "r3" not in set(measures_at(future(history()), CUTOFF)["repo_key"])


def test_commit_exactly_on_cutoff_counts():
    rows = pd.DataFrame([("r", T, 0, 1, 0)], columns=["repo_key", "day", "person", "n", "m"])
    assert repo_measures(rows, T)["days_since_human"] == 0
    assert repo_measures(rows, T - 1) is None


def test_every_declared_feature_is_produced():
    m = repo_measures(history().query("repo_key == 'r1'"), T)
    assert set(FEATURES) <= set(m)


@pytest.mark.parametrize(
    "counts,expected",
    [([], 0), ([10], 1), ([5, 5], 1), ([4, 3, 3], 2), ([1, 1, 1, 1], 2), ([1, 1, 1, 1, 1], 3)],
)
def test_bus_factor(counts, expected):
    import numpy as np

    assert bus_factor(np.array(counts, dtype=float)) == expected


def test_bots_never_count_as_people():
    rows = pd.DataFrame(
        [("r", T - 1, 0, 1, 0), ("r", T - 2, -1, 99, 0)],
        columns=["repo_key", "day", "person", "n", "m"],
    )
    m = repo_measures(rows, T)
    assert m["active_humans"] == 1 and m["commits_365d"] == 1
    assert m["bot_share"] == pytest.approx(0.99)


def test_quiet_repo_has_zero_recent_activity():
    rows = pd.DataFrame([("r", T - 800, 0, 9, 0)], columns=["repo_key", "day", "person", "n", "m"])
    m = repo_measures(rows, T)
    assert m["active_humans"] == 0 and m["bus_factor"] == 0 and m["days_since_human"] == 800
