"""Turn the messy repository URLs in package metadata into one stable key per repo.

Many packages share a repo (the Azure and Google Cloud families), and the repo is what people
actually maintain, so the repo is the unit of analysis. The key is a hash because a repo URL
on a personal account contains a username, and we publish no usernames. The URL itself is only
kept in the encrypted private map.
"""

import hashlib
import re
from urllib.parse import urlsplit

KNOWN_HOSTS = {"github.com", "gitlab.com", "bitbucket.org", "codeberg.org", "git.sr.ht"}


def normalize_repo_url(url: str | None) -> str | None:
    """Return a canonical https URL for owner/repo on a known host, else None."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip().removeprefix("git+").removeprefix("scm:git:")
    url = re.sub(r"^git@([^:]+):", r"https://\1/", url)
    url = re.sub(r"^(ssh|git)://(git@)?", "https://", url)
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    host = parts.netloc.lower().split("@")[-1].removeprefix("www.")
    if host == "gitlab.com" or host.endswith(".gitlab.io"):
        host = "gitlab.com"
    bits = [b for b in parts.path.split("/") if b]
    if host not in KNOWN_HOSTS or len(bits) < 2:
        return None
    owner, repo = bits[0], bits[1]
    repo = repo.removesuffix(".git")
    if not owner or not repo:
        return None
    return f"https://{host}/{owner}/{repo}".lower()


def repo_key(normalized_url: str) -> str:
    """Stable short hash of a normalized URL, safe to publish."""
    return hashlib.sha256(normalized_url.encode()).hexdigest()[:16]


def host_of(normalized_url: str | None) -> str | None:
    return urlsplit(normalized_url).netloc if normalized_url else None
