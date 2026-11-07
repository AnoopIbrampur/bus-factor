"""Build the dependency graph from the requirements each package declares on PyPI.

deps.dev returned an empty result for urllib3 when tested, so the graph comes from PyPI's own
JSON API, which serves the `requires_dist` a package published with its latest release. Only
required dependencies count: an optional extra is a choice, and counting it would overstate
what really breaks. Requirements with a python-version marker are kept, because they do apply
to somebody. Names follow PEP 503, so `Foo_Bar` and `foo-bar` are the same package.
"""

import re
from datetime import date

import pandas as pd
from packaging.requirements import InvalidRequirement, Requirement

from .http import Client
from .repos import normalize_repo_url

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


def repo_from_project_urls(info: dict) -> str | None:
    """Find a repo URL in PyPI metadata, for packages ecosyste.ms has no repo for."""
    urls = dict(info.get("project_urls") or {})
    urls["home_page"] = info.get("home_page")
    preferred = ("source", "code", "repo", "github", "git", "home")
    ordered = sorted(
        urls.items(),
        key=lambda kv: next((i for i, w in enumerate(preferred) if w in kv[0].lower()), 9),
    )
    for _, url in ordered:
        found = normalize_repo_url(url)
        if found:
            return found
    return None


def fetch_requires(names: list[str], client: Client | None = None) -> pd.DataFrame:
    """Return one row per package: its required deps and whether PyPI declared any metadata."""
    client = client or Client(min_interval=0.1)
    rows = []
    for name in names:
        r = client.get(f"https://pypi.org/pypi/{name}/json")
        if r is None:
            rows.append(
                {
                    "name": canon(name),
                    "found": False,
                    "declared": False,
                    "requires": [],
                    "repo_hint": None,
                }
            )
            continue
        info = r.json()["info"]
        rd = info.get("requires_dist")
        rows.append(
            {
                "name": canon(name),
                "found": True,
                "declared": rd is not None,
                "requires": required_names(rd),
                "repo_hint": repo_from_project_urls(info),
            }
        )
    return pd.DataFrame(rows)


def fetch_release_days(names: list[str], client: Client | None = None) -> pd.DataFrame:
    """Days on which each package uploaded a release. Upload times are set by PyPI."""
    client = client or Client(min_interval=0.1)
    rows = []
    for name in names:
        r = client.get(f"https://pypi.org/pypi/{name}/json")
        if r is None:
            continue
        for files in r.json().get("releases", {}).values():
            for f in files[:1]:
                when = date.fromisoformat(f["upload_time"][:10])
                rows.append((name, (when - date(1970, 1, 1)).days))
    return pd.DataFrame(rows, columns=["name", "day"]).drop_duplicates()


def edges(requires: pd.DataFrame, universe: set[str]) -> pd.DataFrame:
    """Edges (dependent -> dependency) with both ends inside the tracked packages."""
    pairs = [
        (row.name_, dep)
        for row in requires.rename(columns={"name": "name_"}).itertuples()
        for dep in row.requires
        if dep in universe and dep != row.name_
    ]
    return pd.DataFrame(pairs, columns=["dependent", "dependency"]).drop_duplicates()
