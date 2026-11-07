"""Bot filtering and identity merging decide every headcount on the site."""

from busfactor.gitlog import BOT, aggregate
from busfactor.people import PersonIndex, is_bot


def test_bots_are_caught():
    for name, email in [
        ("dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com"),
        ("pre-commit-ci[bot]", "66853113+pre-commit-ci[bot]@users.noreply.github.com"),
        ("github-actions", "41898282+github-actions[bot]@users.noreply.github.com"),
        ("aws-sdk-python-automation", "github-aws-sdk-python-automation@amazon.com"),
        ("Renovate Bot", "bot@renovateapp.com"),
        ("Hosted Weblate", "hosted@weblate.org"),
        ("PyTorch UpdateBot", "pytorchupdatebot@users.noreply.github.com"),
        ("copilot-swe-agent[bot]", "198982749+Copilot@users.noreply.github.com"),
    ]:
        assert is_bot(name, email), name


def test_humans_are_not_bots():
    for name, email in [
        ("Abbot Costello", "ac@example.org"),
        ("Robert Botha", "r.botha@example.org"),
        ("Jane Smith", "jane@example.org"),
        ("Travis Example", "te@example.org"),
        ("Sam Jenkins", "sj@example.org"),
        ("Alex Robotham", "ar@example.org"),
    ]:
        assert not is_bot(name, email), name


def test_noreply_merges_with_same_login():
    idx = PersonIndex()
    a = idx.add("Jane Smith", "jane@example.org")
    b = idx.add("Jane Smith", "123+jsmith@users.noreply.github.com")
    c = idx.add("jsmith", "123+jsmith@users.noreply.github.com")
    ids = idx.resolve({a, b, c})
    assert len(set(ids.values())) == 1


def test_short_common_name_does_not_merge():
    idx = PersonIndex()
    a = idx.add("alex", "a@one.example")
    b = idx.add("alex", "b@two.example")
    assert len(set(idx.resolve({a, b}).values())) == 2


def test_aggregate_holds_no_identity_and_pools_bots():
    day = 20000 * 86400
    rows = [
        (day, day, "Jane Smith", "jane@example.org", 1),
        (day, day, "dependabot[bot]", "x[bot]@users.noreply.github.com", 1),
        (day + 86400, day, "Jane Smith", "jane2@example.org", 2),
    ]
    out = aggregate(rows, day + 10**6)
    assert all(isinstance(v, int) for row in out for v in row)
    assert (20000, BOT, 1, 0) in out
    assert (20001, 0, 1, 1) in out


def test_broken_dates_are_dropped():
    now = 20000 * 86400
    rows = [(now + 86400, now, "Jane Smith", "j@e.org", 1), (5, 5, "Jane Smith", "j@e.org", 1)]
    assert aggregate(rows, now) == []
