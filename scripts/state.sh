#!/usr/bin/env bash
# Move pipeline state to and from the "state" release.
# pull fetches the newest copy first, so a job never overwrites newer data with older local data.
# A name ending in .enc is encrypted with BF_STATE_KEY, because it holds repo URLs.
set -euo pipefail
REPO="${GITHUB_REPOSITORY:-AnoopIbrampur/bus-factor}"
cmd="$1"; shift
case "$cmd" in
  pull)  # pull <asset> <local path>: leaves no file if the asset doesn't exist yet
    asset="$1"; dest="$2"; mkdir -p "$(dirname "$dest")"
    if gh release download state -R "$REPO" -p "$asset" -O "$dest.tmp" --clobber 2>/dev/null; then
      if [[ "$asset" == *.enc ]]; then
        openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BF_STATE_KEY -in "$dest.tmp" -out "$dest"
        rm "$dest.tmp"
      else
        mv "$dest.tmp" "$dest"
      fi
    else
      rm -f "$dest.tmp"; echo "no asset $asset yet"
    fi ;;
  push)  # push <local path> <asset>
    src="$1"; asset="$2"; tmp="$(mktemp -d)/$asset"
    if [[ "$asset" == *.enc ]]; then
      openssl enc -aes-256-cbc -pbkdf2 -pass env:BF_STATE_KEY -in "$src" -out "$tmp"
    else
      cp "$src" "$tmp"
    fi
    for i in 1 2 3 4; do
      gh release upload state -R "$REPO" "$tmp" --clobber && exit 0
      sleep $((i * 20))
    done
    exit 1 ;;
esac
