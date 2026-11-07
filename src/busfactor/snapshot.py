"""Read the late-2022 ecosyste.ms archive and pick the forecast cohort from it.

Taking the cohort from a list that existed in 2022 avoids survivor bias: today's top list can
only contain projects that survived. The archive is a Postgres custom-format dump, so
`pg_restore -a -t <table> -f -` turns it into COPY text, which this module reads from a pipe.
No Postgres server is needed. The maintainers tables are never restored.
"""

import json
import re
import sys
from collections import Counter

import pandas as pd

from .config import PRIVATE_DIR, TOP_N
from .repos import host_of, normalize_repo_url, repo_key

_ESC = re.compile(r"\\(.)")
_MAP = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}


def unescape(field: str) -> str | None:
    """Undo COPY text escaping. \\N is NULL."""
    if field == r"\N":
        return None
    if "\\" not in field:
        return field
    return _ESC.sub(lambda m: _MAP.get(m.group(1), m.group(1)), field)


def copy_tables(stream):
    """Yield (table, row dict) for every COPY row in a pg_restore text stream."""
    table, columns = None, None
    header = re.compile(r"^COPY (?:public\.)?(\w+) \((.*)\) FROM stdin;$")
    for line in stream:
        line = line.rstrip("\n")
        if table is None:
            m = header.match(line)
            if m:
                table = m.group(1)
                columns = [c.strip().strip('"') for c in m.group(2).split(",")]
            continue
        if line == r"\.":
            table = None
            continue
        values = line.split("\t")
        if len(values) == len(columns):
            yield table, dict(zip(columns, values, strict=True))


def repo_url_of(row: dict) -> str | None:
    meta = unescape(row["repo_metadata"])
    html = None
    archived = None
    if meta and meta != "{}":
        try:
            data = json.loads(meta)
            html, archived = data.get("html_url"), data.get("archived")
        except json.JSONDecodeError:
            pass
    row["_archived"] = archived
    for candidate in (html, unescape(row["repository_url"]), unescape(row["homepage"])):
        url = normalize_repo_url(candidate)
        if url:
            return url
    return None


def extract(stream) -> pd.DataFrame:
    """Return every PyPI package in the dump, keeping only non-personal fields."""
    rows = []
    seen: Counter[str | None] = Counter()
    for table, row in copy_tables(stream):
        if table != "packages":
            continue
        ecosystem = unescape(row["ecosystem"])
        seen[ecosystem] += 1
        if ecosystem == "pypi":
            url = repo_url_of(row)
            dl = unescape(row["downloads"])
            rows.append(
                {
                    "name": unescape(row["name"]),
                    "downloads": int(dl) if dl else None,
                    "downloads_period": unescape(row["downloads_period"]),
                    "dependent_packages": int(unescape(row["dependent_packages_count"]) or 0),
                    "dependent_repos": int(unescape(row["dependent_repos_count"]) or 0),
                    "status": unescape(row["status"]),
                    "archived_2022": row["_archived"],
                    "_url": url,
                }
            )
    if not rows:
        raise RuntimeError(f"no PyPI rows found; ecosystems seen: {seen.most_common(10)}")
    return pd.DataFrame(rows)


def cohort(packages: pd.DataFrame, top_n: int = TOP_N) -> pd.DataFrame:
    """Top packages by 2022 downloads. Popularity only: no outcome or health signal."""
    ranked = packages.dropna(subset=["downloads"]).sort_values(
        ["downloads", "name"], ascending=[False, True], kind="stable"
    )
    top = ranked.head(top_n).copy()
    top["rank_2022"] = range(1, len(top) + 1)
    has_url = top["_url"].map(lambda u: isinstance(u, str))
    top["repo_key"] = [
        repo_key(u) if ok else None for u, ok in zip(top["_url"], has_url, strict=True)
    ]
    top["host"] = [host_of(u) if ok else None for u, ok in zip(top["_url"], has_url, strict=True)]
    return top


def main() -> None:
    packages = extract(sys.stdin)
    ranked = packages.downloads.notna().sum()
    print(f"pypi packages in dump: {len(packages)}, with downloads: {ranked}")
    top = cohort(packages)
    print(
        f"cohort {len(top)}, lowest downloads {top.downloads.min()}, repos {top.repo_key.nunique()}"
    )
    print(f"no repo: {top.repo_key.isna().sum()}; hosts: {top.host.value_counts().to_dict()}")
    print(f"period: {top.downloads_period.value_counts(dropna=False).to_dict()}")
    PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    top.drop(columns=["_url"]).to_parquet("data/cohort.parquet", index=False)
    private = top.dropna(subset=["_url"])[["repo_key", "_url", "host"]].drop_duplicates("repo_key")
    private.rename(columns={"_url": "url"}).to_parquet(
        PRIVATE_DIR / "cohort_map.parquet", index=False
    )


if __name__ == "__main__":
    main()
