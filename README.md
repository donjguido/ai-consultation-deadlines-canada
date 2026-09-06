# Canadian AI Governance Monitor

A public monitor of every federal channel through which Canadians can shape how AI is governed: consultations, parliamentary calls for briefs, Canada Gazette comment periods, funding calls, standards reviews, and e-petitions. Each item is labelled new, open, closing soon, or retired, with a plain-language summary and a concrete way to participate.

Status: **prototype, 6 September 2026**. Live at https://donjguido.github.io/ai-safety-participation-monitor/. Updated every Mondays and Thursdays (no automatic schedule — run the workflow manually, e.g. via `workflow_dispatch` or `gh workflow run`, on that cadence).

## Documents

- [docs/DESIGN.md](docs/DESIGN.md): design plan (scope, status model, architecture, site design, distribution, quality, roadmap)
- [docs/SOURCES.md](docs/SOURCES.md): data-source inventory with what works today

## Layout

```
data/items.json        canonical store (26 real items as of 2026-09-06)
data/sources.yaml      source inventory and fetcher config
pipeline/models.py     data model and status rules (new = 14 days, closing soon = 7 days)
pipeline/fetch.py      fetchers: Consulting with Canadians CSV, RSS, HTML index pages
pipeline/classify.py   Claude structured-output classifier
pipeline/build.py      renders site/, feed.xml, items.json, digest.md
pipeline/template.html website template (bilingual, light and dark)
site/                  generated output (open index.html in a browser)
funding/               local only, not committed
.github/workflows/     manually-triggered run and GitHub Pages deploy
```

## Run it

```
pip install -r pipeline/requirements.txt
python -m pipeline.fetch data/candidates.json            # pull live candidates
ANTHROPIC_API_KEY=... python -m pipeline.classify data/candidates.json data/items.json
python -m pipeline.build data/items.json site
python -m http.server 8000 --directory site              # then open http://localhost:8000
```

The build step works without an API key; the seed store is already populated.

## Curation

Every Monday and Thursday: open the diff of `data/items.json`, check items with `"verified": false` against their source page, set the flag, add French titles, and retire dead items with a `retired_reason`. Commit, then trigger the workflow (push to `main` or `gh workflow run daily.yml`) to rebuild and deploy.

## Outputs

- Website: https://donjguido.github.io/ai-safety-participation-monitor/
- RSS: https://donjguido.github.io/ai-safety-participation-monitor/feed.xml
- JSON: https://donjguido.github.io/ai-safety-participation-monitor/items.json
- Weekly digest: https://donjguido.github.io/ai-safety-participation-monitor/digest.md

## Feedback

Spotted a wrong status, a dead link, or a missing consultation? Feedback is welcome via pull request against the [original repo](https://github.com/donjguido/ai-safety-participation-monitor).

## Licence

Code MIT. Data CC BY 4.0. Government content reproduced under the Open Government Licence – Canada and parliamentary reproduction terms.

© 2026 Julian Guidote.
