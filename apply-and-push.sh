#!/usr/bin/env bash
set -euo pipefail

REPO="${1:-$HOME/warsaw_city}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$HERE/custom_components/warsaw_city"

if [ ! -d "$REPO/.git" ]; then
  echo "ERROR: $REPO is not a git repository"
  echo "Run: $0 /path/to/ha-warsaw-city"
  exit 1
fi

mkdir -p "$REPO/custom_components/warsaw_city"

cp "$SRC/api.py" "$REPO/custom_components/warsaw_city/api.py"
cp "$SRC/sensor.py" "$REPO/custom_components/warsaw_city/sensor.py"
cp "$SRC/const.py" "$REPO/custom_components/warsaw_city/const.py"
cp "$SRC/manifest.json" "$REPO/custom_components/warsaw_city/manifest.json"

cd "$REPO"

git add   custom_components/warsaw_city/api.py   custom_components/warsaw_city/sensor.py   custom_components/warsaw_city/const.py   custom_components/warsaw_city/manifest.json

if git diff --cached --quiet; then
  echo "No changes to commit."
else
  git commit -m "Release v0.3.7: more departures and filtered events"
  git push
fi

echo "v0.3.7 applied and pushed."
