"""Checks for the D18 survival test: labels, censoring, leakage and the display rule."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from busfactor import survival
from busfactor.config import TEST_CUTOFFS, TRAIN_CUTOFFS
from busfactor.forecast import panel_row
from busfactor.health import day_number

AS_OF = date(2026, 11, 7)
COLS = ["repo_key", "day", "person", "n", "m"]


def frame(rows):
    return pd.DataFrame(rows, columns=COLS)


def synthetic(n_repos: int = 70, seed: int = 0) -> pd.DataFrame:
    """Repos that start, commit at their own pace, and sometimes stop for good."""
    rng = np.random.default_rng(seed)
    lo, hi = day_number(date(2014, 1, 1)), day_number(AS_OF)
    rows = []
    for r in range(n_repos):
        start = int(rng.integers(lo, day_number(date(2020, 1, 1))))
        stop = int(rng.integers(start + 400, hi + 2000))
        gap = float(rng.choice([4, 15, 60, 200]))
        day = start
        while day <= min(stop, hi):
            rows.append((f"r{r:03d}", day, int(rng.integers(0, 3)), 1, 0))
            day += 1 + int(rng.exponential(gap))
    return frame(rows)


def panel_of(rows: pd.DataFrame) -> pd.DataFrame:
    cutoffs = sorted(set(TRAIN_CUTOFFS) | set(TEST_CUTOFFS))
    return pd.concat([panel_row(rows, c) for c in cutoffs], ignore_index=True)


def test_worked_example_from_d18():
    cut = date(2023, 11, 1)
    t = day_number(cut)
    rows = frame([("a", t - 5, 0, 1, 0), ("a", t + 101, 0, 1, 0)])
    gap = survival.next_gap(rows, cut, AS_OF)
    keys = pd.Series(["a"])
    assert [survival.silent_through(gap, keys, h)[0] for h in survival.HORIZONS] == [1, 0, 0, 0]


def test_bot_commits_do_not_end_a_silence():
    cut = date(2023, 11, 1)
    t = day_number(cut)
    rows = frame([("a", t - 5, 0, 1, 0), ("a", t + 10, -1, 9, 0)])
    assert survival.next_gap(rows, cut, AS_OF).empty


def test_expand_uses_only_intervals_over_by_the_cutoff():
    cut = date(2023, 1, 1)
    t = day_number(cut)
    rows = frame([("hit", t - 3, 0, 1, 0), ("hit", t + 101, 0, 1, 0), ("silent", t - 3, 0, 1, 0)])
    base = panel_row(rows, cut)
    seen = cut + timedelta(days=200)  # intervals 0 and 1 have ended, 2 and 3 haven't
    out = survival.expand(base, survival.next_gap(rows, cut, seen), cut, seen)
    got = {(r.repo_key, r.interval): r.event for r in out.itertuples()}
    assert got == {("hit", 0): 0, ("hit", 1): 1, ("silent", 0): 0, ("silent", 1): 0}


def test_training_never_sees_a_commit_after_the_test_date():
    """Adding a commit after T to a training repo must not move any prediction for fold T."""
    rows = synthetic()
    test = TEST_CUTOFFS[1]
    t = day_number(test)
    makers = {k: survival.MAKERS[k] for k in ("logistic", "km", "commits_past_year")}
    base = survival.walk_forward(panel_of(rows), rows, AS_OF, makers)
    keys = sorted(rows["repo_key"].unique())[::2]  # half, so every fit still sees both classes
    extra = frame([(k, t + 10, 0, 50, 0) for k in keys] + [(k, t + 400, 1, 9, 0) for k in keys])
    later = pd.concat([rows, extra], ignore_index=True)
    moved = survival.walk_forward(panel_of(later), later, AS_OF, makers)
    a = base[base["cutoff"] == test.isoformat()].reset_index(drop=True)
    b = moved[moved["cutoff"] == test.isoformat()].reset_index(drop=True)
    for name in makers:
        np.testing.assert_allclose(a[name], b[name])
    assert (a["y"] != b["y"]).any()  # the outcome did change, as it should


def test_only_known_outcomes_are_scored():
    rows = synthetic(40, seed=1)
    makers = {"km": survival.MAKERS["km"]}
    items = survival.walk_forward(panel_of(rows), rows, AS_OF, makers)
    for (cutoff, h), _ in items.groupby(["cutoff", "horizon"]):
        assert date.fromisoformat(cutoff) + timedelta(days=int(h)) <= AS_OF
    last = items[items["cutoff"] == TEST_CUTOFFS[-1].isoformat()]
    assert sorted(last["horizon"].unique()) == [90, 180, 365]
    assert sorted(items[items["cutoff"] == "2024-11-01"]["horizon"].unique()) == [90, 180, 365, 730]


def test_curves_fall_and_stored_models_match():
    rows = synthetic(60, seed=2)
    panel = panel_of(rows)
    train = survival.training_rows(panel, rows, AS_OF, TRAIN_CUTOFFS)
    frame_ = panel[panel["cutoff"] == TEST_CUTOFFS[-1].isoformat()]
    for name in ("logistic", "lightgbm"):
        model = survival.MAKERS[name]().fit(train)
        s = model.survival(frame_)
        assert ((s >= 0) & (s <= 1)).all()
        assert (np.diff(s, axis=1) <= 1e-12).all()
        stored = survival.curve_from_json(survival.model_to_json(model, name), frame_)
        np.testing.assert_allclose(stored, s, rtol=1e-6, atol=1e-9)


def test_kaplan_meier_is_the_plain_share():
    train = pd.DataFrame({"interval": [0, 0, 0, 0, 1, 1], "event": [1, 0, 0, 0, 1, 0]})
    km = survival.KaplanMeier().fit(train)
    s = km.survival(pd.DataFrame(index=range(1)))
    assert s[0, 0] == pytest.approx(0.75)
    assert s[0, 1] == pytest.approx(0.75 * 0.5)


def test_display_keeps_points_in_order_around_the_frozen_year():
    out = survival.displayed(0.30, 0.25, 0.20, year=0.28)
    assert (out["s90"], out["s180"], out["s730"]) == (30, 28, 20)
    assert out["s_adjusted"] == ["s180"] and out["s_visible"] == ["s180"]
    tiny = survival.displayed(0.30, 0.2799, 0.20, year=0.28)
    assert tiny["s_adjusted"] == ["s180"] and tiny["s_visible"] == []
    assert out["s730_band"] == "Middle chance" and out["s90_band"] == "Higher chance"
    clean = survival.displayed(0.6, 0.5, 0.2, year=0.4)
    assert clean["s_adjusted"] == []
    edge = survival.displayed(0.0996, 0.0996, 0.01, year=0.05)
    assert edge["s90"] == 10 and edge["s90_band"] == "Lower chance"  # band uses the raw value
