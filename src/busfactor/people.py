"""Decide which commit authors are bots, and which author records are the same person.

Privacy is the point of this module. Emails and names exist only in memory while one repo is
processed. They are salted, hashed and merged into a small per-repo index (0, 1, 2 ...), and
that index is all that leaves this module. A salt that changes per run can't link anyone
across runs, and an index can't be reversed into a person.

Merging is deliberately cautious: a false merge makes a project look smaller than it is, which
is the worse mistake for a site about projects with few people.
"""

import hashlib
import re
import secrets

_BOT_NAME = re.compile(
    r"""
    \[bot\]$ | (^|[-_ .])bots?($|[-_ .\d]) | updatebot | pytorchbot | boringbot
    | \brobot\b | -robot | dependabot | renovate | github-actions
    | ^github$ | ^github\ action | ^actions-user$ | web-flow | pre-commit-ci | pyup | greenkeeper
    | snyk | codecov | deepsource | imgbot | all-?contributors | mergify | semantic-release
    | release-please | weblate | transifex | crowdin | lokalise | sourcery | restyled
    | stainless | copybara | yoshi-automation | owlbot | automation | automated | autobuild
    | auto-?update | auto-?merge | azure-sdk | azclibot | openapi-generator
    | ^travis(\ ?ci)?$ | travis-ci | circleci | ^jenkins$ | jenkins- | zuul
    | ^copilot$ | swe-agent | ^claude(\ code)?$ | ^cursor(\ ?agent)?$ | ^codex$
    | homu$ | ^bors | svn2git | cvs2svn | ^autofix | ^ci$ | -ci$ | ^cibuild
    | ^release-?manager$ | versioneer | sync-?bot | fossabot | gitter-badger | scrutinizer
    | ^unknown$ | ^none$ | ^root$ | ^nobody$
    """,
    re.IGNORECASE | re.VERBOSE,
)
_BOT_EMAIL = re.compile(
    r"""
    \[bot\]@ | (^|[-_.+])bot@ | ^noreply@github\.com$ | ^actions@github\.com$
    | ^action@github\.com$ | automation@ | ^ci@ | -ci@ | robot@ | ^noreply@ | ^no-reply@
    | ^build@ | ^release@ | weblate
    """,
    re.IGNORECASE | re.VERBOSE,
)
_NOREPLY = re.compile(r"^(?:\d+\+)?([^@]+)@users\.noreply\.(?:github\.com|gitlab\.com)$", re.I)


def is_bot(name: str, email: str) -> bool:
    """True when the author record looks like automation, by name or email pattern."""
    return bool(_BOT_NAME.search((name or "").strip()) or _BOT_EMAIL.search((email or "").strip()))


def _norm_name(name: str) -> str | None:
    """Lowercased name usable for merging, or None when too generic to trust.

    A single short word ("alex") can easily be two people, so it doesn't merge on its own.
    """
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    if len(n) < 5 or (" " not in n and len(n) < 8):
        return None
    return n


class PersonIndex:
    """Union-find over salted hashes of emails and names, with a per-repo integer output."""

    def __init__(self) -> None:
        self._salt = secrets.token_bytes(16)
        self._parent: dict[bytes, bytes] = {}

    def _h(self, kind: str, value: str) -> bytes:
        return hashlib.blake2b(kind.encode() + b"\0" + value.encode(), key=self._salt).digest()[:12]

    def _find(self, x: bytes) -> bytes:
        self._parent.setdefault(x, x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def _union(self, a: bytes, b: bytes) -> None:
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            self._parent[rb] = ra

    def add(self, name: str, email: str) -> bytes:
        """Record one author record and return an opaque key for it."""
        email = (email or "").strip().lower()
        norm = _norm_name(name)
        keys = []
        m = _NOREPLY.match(email)
        if m:
            login = m.group(1)
            keys.append(self._h("login", login))
            keys.append(self._h("name", login))  # people often commit as their login too
        elif email:
            keys.append(self._h("email", email))
        if norm:
            keys.append(self._h("name", norm))
        if not keys:
            keys.append(self._h("email", "unknown"))
        for k in keys[1:]:
            self._union(keys[0], k)
        return keys[0]

    def resolve(self, keys: set[bytes]) -> dict[bytes, int]:
        """Map each key to a small integer, equal for merged identities."""
        roots: dict[bytes, int] = {}
        out: dict[bytes, int] = {}
        for k in keys:
            out[k] = roots.setdefault(self._find(k), len(roots))
        return out
