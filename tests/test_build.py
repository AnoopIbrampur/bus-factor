"""Rule 5: unknown is never shown as healthy. Rule 4: nothing is called abandoned."""

from datetime import date

import pandas as pd

from busfactor.build import STATE_LABEL, assemble, classify, is_few
from busfactor.health import day_number

TODAY = date(2026, 11, 1)
T = day_number(TODAY)


def test_missing_repo_is_unknown():
    assert classify({"repo_key": None})[0] == "unknown"


def test_missing_history_is_unknown_not_active():
    assert classify({"repo_key": "abc", "days_since_human": None})[0] == "unknown"
    assert classify({"repo_key": "abc", "days_since_human": float("nan")})[0] == "unknown"


def test_quiet_slowing_active_archived():
    base = {"repo_key": "a", "commits_prev_365d": 100, "trend": 0.0}
    assert classify({**base, "days_since_human": 500})[0] == "quiet"
    assert classify({**base, "days_since_human": 5, "trend": -1.0})[0] == "slowing"
    assert classify({**base, "days_since_human": 5})[0] == "active"
    assert classify({**base, "days_since_human": 5, "archived": True})[0] == "archived"


def test_small_projects_are_not_called_slowing():
    row = {"repo_key": "a", "days_since_human": 5, "commits_prev_365d": 4, "trend": -2.0}
    assert classify(row)[0] == "active"


def test_few_people_needs_a_living_project():
    assert is_few({"state": "active", "bus_factor": 1, "active_humans": 5})
    assert not is_few({"state": "quiet", "bus_factor": 1, "active_humans": 1})
    assert not is_few({"state": "active", "bus_factor": 3, "active_humans": 9})


def test_banned_words_absent_from_labels():
    joined = " ".join(STATE_LABEL.values()).lower()
    for word in ("abandon", "unsafe", "dead", "compromise"):
        assert word not in joined


def test_assemble_end_to_end():
    universe = pd.DataFrame(
        {
            "name": ["Alpha_One", "beta", "gamma"],
            "rank": [1, 2, 3],
            "downloads": [300, 200, 100],
            "repo_key": ["r1", "r2", None],
            "archived": [False, False, None],
        }
    )
    requires = pd.DataFrame(
        {"name": ["alpha-one", "beta", "gamma"], "requires": [[], ["alpha-one"], ["beta"]]}
    )
    rows = pd.DataFrame(
        [("r1", T - 3, 0, 9, 0), ("r2", T - 800, 0, 9, 0)],
        columns=["repo_key", "day", "person", "n", "m"],
    )
    table, sim = assemble(universe, requires, rows, TODAY)
    t = table.set_index("name")
    assert t.loc["alpha-one", "state"] == "active"
    assert t.loc["alpha-one", "total_dependents"] == 2
    assert t.loc["beta", "state"] == "quiet"
    assert t.loc["gamma", "state"] == "unknown"
    assert pd.isna(t.loc["gamma", "bus_factor"])
    assert bool(t.loc["gamma", "few_people"]) is False
