"""Choose today's top packages and record only the facts this project needs.

The list is the top 5,000 by last-month downloads as reported by ecosyste.ms. That rule looks at
popularity alone, never at health, so it can't favour the projects we want to find. The list
API returns maintainer names and emails, and those fields are dropped here, on arrival, so they
can't reach a cache, a log or a release asset.
"""

from datetime import UTC, datetime

import pandas as pd

from .config import PRIVATE_DIR, TOP_N
from .http import Client
from .repos import host_of, normalize_repo_url, repo_key

LIST_URL = "https://packages.ecosyste.ms/api/v1/registries/pypi.org/packages"
PER_PAGE = 1000


def _project_url(item: dict) -> str | None:
    """Best repo URL for a package. repo_metadata follows renames, so it is tried first."""
    meta = item.get("repo_metadata") or {}
    for candidate in (meta.get("html_url"), item.get("repository_url"), item.get("homepage")):
        url = normalize_repo_url(candidate)
        if url:
            return url
    return None


def slim(item: dict) -> dict:
    """Keep the safe fields of one API record. Nothing about people survives this."""
    url = _project_url(item)
    meta = item.get("repo_metadata") or {}
    return {
        "name": item["name"],
        "downloads": item.get("downloads"),
        "dependent_packages": item.get("dependent_packages_count"),
        "dependent_repos": item.get("dependent_repos_count"),
        "critical": bool(item.get("critical")),
        "has_repo_field": bool(item.get("repository_url")),
        "repo_key": repo_key(url) if url else None,
        "host": host_of(url),
        "archived": meta.get("archived"),
        "is_fork": meta.get("fork"),
        "has_funding": bool(item.get("funding_links")),
        "first_release": item.get("first_release_published_at"),
        "latest_release": item.get("latest_release_published_at"),
        "registry_status": item.get("status"),
        "_url": url,
        "_owner_kind": (meta.get("owner_record") or {}).get("kind"),
    }


def fetch_top(client: Client | None = None, top_n: int = TOP_N) -> pd.DataFrame:
    """Fetch the ranked list page by page. Fails loudly on a short page."""
    client = client or Client()
    rows: list[dict] = []
    for page in range(1, top_n // PER_PAGE + 2):
        r = client.get(
            LIST_URL,
            params={"sort": "downloads", "order": "desc", "per_page": PER_PAGE, "page": page},
        )
        items = r.json() if r else []
        rows.extend(slim(i) for i in items)
        if len(rows) >= top_n or len(items) < PER_PAGE:
            break
    df = pd.DataFrame(rows).drop_duplicates("name")
    df = df.sort_values("downloads", ascending=False, kind="stable").head(top_n)
    if len(df) < top_n:
        raise RuntimeError(f"only {len(df)} packages returned, wanted {top_n}")
    df["rank"] = range(1, len(df) + 1)
    df["fetched_at"] = datetime.now(UTC).date().isoformat()
    return df.reset_index(drop=True)


def split_private(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate the publishable table from the URL map, which must stay encrypted."""
    private = df.loc[df["_url"].notna(), ["repo_key", "_url", "_owner_kind", "host"]]
    private = private.drop_duplicates("repo_key").rename(
        columns={"_url": "url", "_owner_kind": "owner_kind"}
    )
    return df.drop(columns=["_url", "_owner_kind"]), private


def save(df: pd.DataFrame, public_path, private_path=PRIVATE_DIR / "repo_map.parquet") -> None:
    public, private = split_private(df)
    public.to_parquet(public_path, index=False)
    private_path.parent.mkdir(parents=True, exist_ok=True)
    private.to_parquet(private_path, index=False)
