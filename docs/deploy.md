# Sharing Groundloop

There are two free ways to put Groundloop in front of other people. Most of the
time you want the first one.

| | Snapshot (GitHub Pages) | Live demo (Render free) |
|:--|:--|:--|
| What visitors can do | Browse every page, run, timeline, and theme | The same, plus ask new questions |
| Cost | Free | Free hosting. Live runs use your OpenAI key, capped per day |
| Always on | Yes | Sleeps after 15 minutes idle, about a minute to wake |
| Accounts needed | GitHub (you have it) | Render (free, no credit card) |
| OpenAI key online | No | Only if you set one |

Both run in public demo mode: one pinned system, nothing can be created,
uploaded, edited, or deleted, and no local paths or provider endpoint appear in
any response.

## 1. Snapshot on GitHub Pages

A snapshot is the console plus saved copies of the API responses for one
system. It needs no server and no key.

GitHub Pages is free only for public repositories, and this research repo is
private. So the snapshot goes to a separate public repo that contains only the
built site and the system's public notes and recorded runs, not this code base.

```bash
scripts/publish_snapshot.sh <your-github-name>/groundloop
```

That builds `dist/site`, creates the public repo on first use, pushes, and
turns on Pages. The link is `https://<your-github-name>.github.io/groundloop/`.
Run it again after recording new runs to refresh the snapshot.

Preview before publishing:

```bash
python scripts/build_static_demo.py
python -m http.server -d dist 8002   # open http://127.0.0.1:8002/site/
```

## 2. Live demo on Render

1. Sign up at render.com with GitHub (free plan, no card).
2. Choose **New > Blueprint**, pick this repository, and confirm. Render reads
   `render.yaml`.
3. In the service's **Environment** tab, set `OPENAI_API_KEY` (and
   `OPENAI_BASE_URL` if you use a compatible endpoint). Leave the key empty for
   a browse-only demo that costs nothing.
4. Open the `.onrender.com` link Render shows.

What the free plan means in practice:

- The service sleeps after 15 minutes without visitors. The first visit after
  that takes about a minute.
- Runs made on the demo are not kept across restarts. The recorded runs in
  `demo/traces/` are what every restart starts from.
- `GROUNDLOOP_DAILY_RUNS` (25 by default) caps live runs per day. A
  gpt-4o-mini run with recovery is a handful of model calls, so the cap keeps
  the worst case to a few cents a day.

## Settings

| Variable | Meaning |
|:--|:--|
| `GROUNDLOOP_DEMO=1` | Public demo mode (pinned, read-only, capped, scrubbed) |
| `GROUNDLOOP_DAILY_RUNS` | Live runs allowed per day in demo mode (default 25) |
| `GROUNDLOOP_SYSTEM` | System to open on, for example `dku` |
| `GROUNDLOOP_TRACES_ROOT` | Folder of recorded runs, relative to the repo |
| `HOST`, `PORT` | Where the server listens (hosts set `PORT`) |

## Refreshing the demo data

`demo/traces/dku/` holds the recorded runs the live demo serves, with the
provider endpoint removed. To refresh it from your local runs:

```bash
rm -rf demo/traces/dku && mkdir -p demo/traces/dku
cp -r experiments/output/dku/. demo/traces/dku/
python - <<'PY'
import json, pathlib, sys
sys.path.insert(0, "src")
from swrag.api.public import scrub
root = str(pathlib.Path(".").resolve())
for f in pathlib.Path("demo/traces/dku").rglob("*.json"):
    f.write_text(json.dumps(scrub(json.loads(f.read_text()), root), indent=2) + "\n")
PY
```
