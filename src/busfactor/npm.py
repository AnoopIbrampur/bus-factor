"""npm support: names, required dependencies and repo hints from the public npm registry.

npm names are already lowercase, and dots and underscores are meaningful, so PyPI's PEP 503 rule
doesn't apply. Each package's latest manifest gives its `dependencies`. Dev, peer, optional and
bundled dependencies are left out, as PyPI extras are (D9, D23). A manifest also lists people
(author, maintainers, contributors). Those fields are never read, so they can't reach a file.
"""

import re
from urllib.parse import quote

import pandas as pd

from .http import Client
from .repos import normalize_repo_url

REGISTRY = "https://registry.npmjs.org"
_SHORTHAND = re.compile(r"^(github|gitlab|bitbucket):([^/\s]+/[^/\s]+)$")
_HOSTS = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org"}
_BARE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def norm(name: str) -> str:
    """npm package name as tracked: trimmed and lowercase."""
    return name.strip().lower()


def manifest_url(name: str) -> str:
    """URL of the latest manifest. A scoped name's slash must be encoded."""
    return f"{REGISTRY}/{quote(name, safe='@')}/latest"


def repo_from_manifest(repository) -> str | None:
    """Normalise npm's `repository` field: a string, a shorthand like github:a/b, or a dict."""
    url = repository.get("url") if isinstance(repository, dict) else repository
    if not isinstance(url, str):
        return None
    url = url.strip()
    m = _SHORTHAND.match(url)
    if m:
        url = f"https://{_HOSTS[m.group(1)]}/{m.group(2)}"
    elif _BARE.match(url):  # "owner/repo" means GitHub in npm's own rules
        url = f"https://github.com/{url}"
    return normalize_repo_url(url)


def required_names(manifest: dict) -> list[str]:
    deps = manifest.get("dependencies")
    if not isinstance(deps, dict):
        return []
    return sorted({norm(n) for n in deps if isinstance(n, str) and n.strip()})


def fetch_requires(names: list[str], client: Client | None = None) -> pd.DataFrame:
    """One row per package: required dependencies, and a repo hint for filling gaps."""
    client = client or Client(min_interval=0.08)
    rows = []
    for name in names:
        r = client.get(manifest_url(name))
        if r is None:
            rows.append({"name": norm(name), "found": False, "requires": [], "repo_hint": None})
            continue
        manifest = r.json()
        rows.append(
            {
                "name": norm(name),
                "found": True,
                "requires": required_names(manifest),
                "repo_hint": repo_from_manifest(manifest.get("repository")),
            }
        )
    return pd.DataFrame(rows)
