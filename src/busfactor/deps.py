"""Build the dependency graph from the requirements each package declares on PyPI.

deps.dev returned an empty result for urllib3 when tested, so the graph comes from PyPI's own
JSON API, which serves the `requires_dist` a package published with its latest release. Only
required dependencies count: an optional extra is a choice, and counting it would overstate
what really breaks. Requirements with a python-version marker are kept, because they do apply
to somebody. Names follow PEP 503, so `Foo_Bar` and `foo-bar` are the same package.
"""

import re

import pandas as pd
from packaging.requirements import InvalidRequirement, Requirement

from .http import Client

_NAME = re.compile(r"[-_.]+")


def canon(name: str) -> str:
    """PEP 503 normalised package name."""
    return _NAME.sub("-", name).lower()


def required_names(requires_dist: list[str] | None) -> list[str]:
    """Names of non-optional dependencies, ignoring any that only apply to an extra."""
    out = set()
    for spec in requires_dist or []:
        try:
            req = Requirement(spec)
        except InvalidRequirement:
            continue
        if req.marker is not None and "extra" in str(req.marker):
            continue
        out.add(canon(req.name))
    return sorted(out)


def fetch_requires(names: list[str], client: Client | None = None) -> pd.DataFrame:
    """Return one row per package: its required deps and whether PyPI declared any metadata."""
    client = client or Client(min_interval=0.1)
    rows = []
    for name in names:
        r = client.get(f"https://pypi.org/pypi/{name}/json")
        if r is None:
            rows.append({"name": canon(name), "found": False, "declared": False, "requires": []})
            continue
        info = r.json()["info"]
        rd = info.get("requires_dist")
        rows.append(
            {
                "name": canon(name),
                "found": True,
                "declared": rd is not None,
                "requires": required_names(rd),
            }
        )
    return pd.DataFrame(rows)


def edges(requires: pd.DataFrame, universe: set[str]) -> pd.DataFrame:
    """Edges (dependent -> dependency) with both ends inside the tracked packages."""
    pairs = [
        (row.name_, dep)
        for row in requires.rename(columns={"name": "name_"}).itertuples()
        for dep in row.requires
        if dep in universe and dep != row.name_
    ]
    return pd.DataFrame(pairs, columns=["dependent", "dependency"]).drop_duplicates()
