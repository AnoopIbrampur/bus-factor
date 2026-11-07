"""Clone a repo's commit graph and reduce it to daily counts per anonymous person.

Git history is the only activity source that can be recomputed at any past date, which the
point-in-time rule needs. `--filter=tree:0 --single-branch` fetches commits without files, so
even very large projects stay small. Only the default branch counts: it is what shipped.

Dates: the committer date is the closest thing git has to "when this landed". Git records no
push date, so this is an approximation (see docs/data_audit.md). If a history rewrite has
stamped everything with one date, the author date is used instead.
"""

import os
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from .people import PersonIndex, is_bot

BOT = -1  # all automation in a repo is pooled under one id
MIN_TS = int(datetime(2000, 1, 1, tzinfo=UTC).timestamp())
_ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",  # a deleted repo must fail, not wait for a password
    "GIT_ASKPASS": "/bin/true",
    "GIT_NO_LAZY_FETCH": "1",
    "GIT_LFS_SKIP_SMUDGE": "1",
}


def clone(url: str, dest: Path, timeout: int) -> str:
    """Clone into dest and return 'ok', 'missing' or 'timeout'.

    Output is captured and discarded because logs on a public repo must not show URLs that
    contain usernames.
    """
    cmd = ["git", "clone", "-q", "--bare", "--filter=tree:0", "--single-branch", "--no-tags"]
    try:
        r = subprocess.run(
            [*cmd, url + ".git", str(dest)], env=_ENV, capture_output=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    return "ok" if r.returncode == 0 else "missing"


def read_log(path: Path, timeout: int) -> tuple[list[tuple[int, int, str, str, int]], str]:
    """Return (committer_ts, author_ts, name, email, n_parents) for each commit on HEAD."""
    fmt = "%ct%x00%at%x00%an%x00%ae%x00%P%x00"
    cmd = ["git", "-C", str(path), "log", "--no-mailmap", f"--format={fmt}", "HEAD"]
    try:
        r = subprocess.run(cmd, env=_ENV, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return [], "timeout"
    if r.returncode != 0:
        return [], "empty"
    fields = r.stdout.decode("utf-8", "replace").split("\0")
    rows = []
    for i in range(0, len(fields) - 4, 5):
        ct, at, name, email, parents = fields[i : i + 5]
        ct, at = ct.strip(), at.strip()
        if ct.isdigit() and at.isdigit():
            rows.append((int(ct), int(at), name, email, len(parents.split())))
    return rows, "ok"


def history_rewritten(rows: list[tuple[int, int, str, str, int]]) -> bool:
    """True when committer dates collapse onto far fewer days than author dates."""
    if len(rows) < 50:
        return False
    days_c = {r[0] // 86400 for r in rows}
    days_a = {r[1] // 86400 for r in rows}
    return len(days_c) < 0.2 * len(days_a)


def aggregate(rows, now_ts: int) -> list[tuple[int, int, int, int]]:
    """Reduce commits to (day_number, person, n_commits, n_merges) with no identifying data.

    Dates before 2000 or in the future are broken clocks, so they are dropped. day_number is
    days since 1970-01-01.
    """
    use_author = history_rewritten(rows)
    index = PersonIndex()
    tally: Counter[tuple[int, bytes | int]] = Counter()
    merges: Counter[tuple[int, bytes | int]] = Counter()
    keys: set[bytes] = set()
    for ct, at, name, email, parents in rows:
        ts = at if use_author else ct
        if ts < MIN_TS or ts > now_ts:
            continue
        who: bytes | int
        if is_bot(name, email):
            who = BOT
        else:
            who = index.add(name, email)
            keys.add(who)
        key = (ts // 86400, who)
        tally[key] += 1
        if parents > 1:
            merges[key] += 1
    ids = index.resolve(keys)
    combined: Counter[tuple[int, int]] = Counter()
    combined_m: Counter[tuple[int, int]] = Counter()
    for (day, who), n in tally.items():
        p = BOT if who == BOT else ids[who]
        combined[(day, p)] += n
        combined_m[(day, p)] += merges.get((day, who), 0)
    return [(d, p, n, combined_m[(d, p)]) for (d, p), n in sorted(combined.items())]


def harvest_repo(url: str, now_ts: int, clone_timeout: int = 600) -> tuple[str, list]:
    """Clone, read, aggregate and delete one repo. Returns (status, rows)."""
    tmp = Path(tempfile.mkdtemp(prefix="bf-"))
    try:
        status = clone(url, tmp / "r", clone_timeout)
        if status != "ok":
            return status, []
        rows, status = read_log(tmp / "r", 300)
        return status, aggregate(rows, now_ts) if rows else []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
