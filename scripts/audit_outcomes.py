"""Hand-audit helper: what does "no human commit for 12 months" really look like?

Before locking the outcome, a random sample of labelled-quiet repos is pulled together with public
signals that git commits don't show. A person reads the table and classifies each one. Output
goes to the terminal only and is never saved, because repo names can contain usernames. The
docs record counts.

Run locally with the decrypted cohort map in data/private/.
"""

import json
import subprocess
import sys
from datetime import date

import pandas as pd

from busfactor.forecast import panel_row
from busfactor.repos import normalize_repo_url

CUTOFF = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date(2023, 11, 1)
N = int(sys.argv[2]) if len(sys.argv) > 2 else 40


def api(path: str) -> dict:
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else {}


def main() -> None:
    from pathlib import Path

    from busfactor.build import load_rows

    cohort = pd.read_parquet("data/cohort.parquet")
    m = pd.read_parquet("data/private/cohort_map.parquet").set_index("repo_key")["url"]
    rows = load_rows(Path("data"))
    rows = rows[rows["repo_key"].isin(set(cohort["repo_key"].dropna()))]
    release = pd.read_parquet("data/release_days.parquet")
    panel = panel_row(rows, CUTOFF, release)
    print(
        len(panel),
        "eligible;",
        int(panel.quiet.sum()),
        "quiet;",
        int(panel.quiet_strict.sum()),
        "strict",
    )
    sample = panel[panel.quiet == 1].sample(min(N, int(panel.quiet.sum())), random_state=11)
    name_of = (
        cohort.dropna(subset=["repo_key"]).drop_duplicates("repo_key").set_index("repo_key")["name"]
    )
    for row in sample.itertuples():
        url = m[row.repo_key]
        slug = "/".join(url.split("/")[-2:])
        info = api(f"repos/{slug}") if "github.com" in url else {}
        moved = normalize_repo_url(info.get("html_url")) != url if info else None
        print(
            json.dumps(
                {
                    "pkg": name_of.get(row.repo_key),
                    "strict": row.quiet_strict,
                    "c365": row.commits_365d,
                    "humans": row.active_humans,
                    "days": row.days_since_human,
                    "archived": info.get("archived"),
                    "moved": moved,
                    "pushed": (info.get("pushed_at") or "")[:10],
                    "open_issues": info.get("open_issues_count"),
                    "stars": info.get("stargazers_count"),
                    "desc": (info.get("description") or "")[:90],
                }
            )
        )


if __name__ == "__main__":
    main()
