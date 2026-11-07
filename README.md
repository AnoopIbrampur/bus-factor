# Frozen predictions

One file per week in `predictions/`, written once before the outcome exists and never changed.
The git history of this branch is the proof of when each forecast was made. The weekly job
refuses to commit anything but a new file.

Each row gives a hashed repo key, its package names, the chance of no human commit in the next
365 days, and the same chance from the simple comparison rule. Rows are sorted by the hash, so a
file isn't a ranked list. Scoring rules are D15 in `docs/decisions.md` on `main`.

Data is CC-BY-SA 4.0, derived in part from ecosyste.ms.
