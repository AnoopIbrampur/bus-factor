"""A public record is only worth anything if it can't be quietly rewritten."""

from datetime import date

import numpy as np
import pandas as pd

from busfactor.forecast import Logit
from busfactor.health import FEATURES, day_number
from busfactor.live import (
    PHRASES,
    freeze_payload,
    grade,
    model_id,
    model_to_json,
    predict,
    read_frozen,
    reasons,
    week_of,
    write_frozen,
)

TODAY = date(2026, 11, 9)


def scored():
    return pd.DataFrame(
        {
            "repo_key": ["bb", "aa", "cc"],
            "packages": [["b"], ["a"], ["c"]],
            "prob": [0.9, 0.1, 0.5],
            "baseline_prob": [0.5, 0.2, 0.3],
        }
    )


def payload():
    return freeze_payload(scored(), TODAY, "m1", "b1", "D15")


def test_every_feature_has_plain_words():
    assert set(PHRASES) == set(FEATURES)
    text = " ".join(t for pair in PHRASES.values() for t in pair).lower()
    for word in ("abandon", "unsafe", "compromise", "takeover"):
        assert word not in text


def test_frozen_file_is_not_a_ranking():
    keys = [p["repo_key"] for p in payload()["predictions"]]
    assert keys == sorted(keys)


def test_a_week_can_only_be_frozen_once(tmp_path):
    first = write_frozen(payload(), tmp_path)
    original = first.read_bytes()
    changed = payload()
    changed["predictions"][0]["prob"] = 0.99
    assert write_frozen(changed, tmp_path) is None
    assert first.read_bytes() == original


def test_nothing_is_graded_before_it_is_due(tmp_path):
    write_frozen(payload(), tmp_path)
    rows = pd.DataFrame(columns=["repo_key", "day", "person", "n", "m"])
    out = grade(read_frozen(tmp_path), rows, date(2027, 6, 1))
    assert out["weeks"][0]["graded"] is False
    assert out["next_due"] == "2027-11-09"


def test_grading_after_the_window(tmp_path):
    write_frozen(payload(), tmp_path)
    t = day_number(TODAY)
    rows = pd.DataFrame(
        [("aa", t + 10, 0, 1, 0), ("bb", t - 5, 0, 1, 0), ("bb", t + 10, -1, 9, 0)],
        columns=["repo_key", "day", "person", "n", "m"],
    )
    w = grade(read_frozen(tmp_path), rows, date(2027, 12, 1))["weeks"][0]
    assert w["graded"] and w["n_graded"] == 2  # cc has no history, so it can't be graded
    assert w["quiet"] == 1  # bb only had bot activity in the window


def test_week_name_is_a_monday():
    assert week_of(date(2026, 11, 12)) == date(2026, 11, 9)


def fitted():
    rng = np.random.default_rng(0)
    n = 300
    x = pd.DataFrame({c: rng.uniform(0, 50, n) for c in FEATURES})
    x["trend"] = rng.normal(0, 1, n)
    x["quiet"] = (x["days_since_human"] + rng.normal(0, 10, n) > 25).astype(int)
    return Logit(FEATURES).fit(x, x, "quiet"), x


def test_stored_numbers_match_the_fitted_model():
    m, x = fitted()
    spec = model_to_json(m, "logistic")
    assert np.allclose(predict(spec, x), m.predict(x), atol=1e-9)
    assert model_id(spec) == model_id(spec)


def test_reasons_are_only_upward_and_short():
    m, x = fitted()
    out = reasons(model_to_json(m, "logistic"), x.head(5))
    assert len(out) == 5 and all(len(r) <= 3 for r in out)
