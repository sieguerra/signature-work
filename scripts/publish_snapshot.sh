#!/usr/bin/env bash
# Build the static snapshot and publish it to GitHub Pages from a public repo
# that holds only the built site (this research repo can stay private).
#
#   scripts/publish_snapshot.sh <owner>/<repo>      e.g. sieguerra/groundloop
#
# Needs: the GitHub CLI logged in (gh auth status). The first run creates the
# public repo and turns on Pages. The site appears at
# https://<owner>.github.io/<repo>/ a minute or two after the push.
set -euo pipefail
repo="${1:?usage: scripts/publish_snapshot.sh <owner>/<repo>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
site="$root/dist/site"

"$root/.venv/bin/python" "$root/scripts/build_static_demo.py" --out "$site"

if ! gh repo view "$repo" >/dev/null 2>&1; then
  gh repo create "$repo" --public --description "Groundloop: agentic RAG that checks its own answers (read-only demo)"
fi

cd "$site"
rm -rf .git
git init -q -b main
git add -A
git -c user.name="$(git -C "$root" config user.name)" -c user.email="$(git -C "$root" config user.email)" \
  commit -q -m "Publish Groundloop snapshot $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q --force "https://github.com/$repo.git" main

gh api -X POST "repos/$repo/pages" -f "source[branch]=main" -f "source[path]=/" >/dev/null 2>&1 \
  || gh api -X PUT "repos/$repo/pages" -f "source[branch]=main" -f "source[path]=/" >/dev/null 2>&1 || true
owner="${repo%%/*}"; name="${repo##*/}"
echo "Published: https://$owner.github.io/$name/"
