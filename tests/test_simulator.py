"""The simulator's counts are the most quoted numbers on the site, so check them by hand."""

import pandas as pd

from busfactor.deps import canon, edges, required_names
from busfactor.simulator import reach, reverse_graph, simulate

E = pd.DataFrame(
    [("b", "a"), ("c", "b"), ("d", "b"), ("d", "a"), ("e", "c"), ("c", "e")],
    columns=["dependent", "dependency"],
)
DL = {"a": 100, "b": 50, "c": 40, "d": 30, "e": 10, "z": 5}


def test_direct_and_indirect_counts():
    row = simulate(E, DL).set_index("name").loc["a"]
    assert row.n_direct == 2 and row.n_indirect == 2
    assert row.direct == ["b", "d"] and row.indirect == ["c", "e"]
    assert row.downloads_sum == 130 and row.downloads_max == 50


def test_a_cycle_ends_and_excludes_self():
    assert reach(reverse_graph(E), "c") == {"e": 1}


def test_package_nothing_needs():
    row = simulate(E, DL).set_index("name").loc["z"]
    assert row.n_direct == 0 and row.n_indirect == 0 and row.downloads_max == 0


def test_extras_are_not_required():
    got = required_names(
        ["Foo_Bar>=1", 'baz; extra == "test"', 'qux<2; python_version < "3.10"', "bad spec !!"]
    )
    assert got == ["foo-bar", "qux"]


def test_names_normalise():
    assert canon("Ruamel.YAML_clib") == "ruamel-yaml-clib"


def test_edges_stay_inside_universe():
    req = pd.DataFrame({"name": ["a", "b"], "requires": [["b", "out", "a"], []]})
    assert edges(req, {"a", "b"}).values.tolist() == [["a", "b"]]
