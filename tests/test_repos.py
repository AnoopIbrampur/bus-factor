"""Repo URLs arrive in many spellings, and each spelling must land on one key."""

from busfactor.repos import normalize_repo_url, repo_key


def test_spellings_collapse():
    want = "https://github.com/pallets/flask"
    for raw in [
        "https://github.com/pallets/flask",
        "https://github.com/Pallets/Flask.git",
        "git+https://github.com/pallets/flask.git",
        "git@github.com:pallets/flask.git",
        "git://github.com/pallets/flask",
        "https://www.github.com/pallets/flask/tree/main/src",
        "github.com/pallets/flask",
    ]:
        assert normalize_repo_url(raw) == want, raw


def test_rejects_non_repos():
    for raw in [None, "", "https://pypi.org/project/x", "https://github.com/onlyowner"]:
        assert normalize_repo_url(raw) is None


def test_key_is_stable_and_hides_url():
    key = repo_key("https://github.com/pallets/flask")
    assert key == repo_key("https://github.com/pallets/flask") and "pallets" not in key
