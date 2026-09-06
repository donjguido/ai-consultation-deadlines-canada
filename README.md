# Canadian AI Governance Monitor

A public monitor of every federal channel through which Canadians can shape how AI is governed: consultations, parliamentary calls for briefs, Canada Gazette comment periods, funding calls, standards reviews, and e-petitions. Each item is labelled new, open, closing soon, or retired, with a plain-language summary and a concrete way to participate.

Status: **prototype, 6 September 2026**. Live at https://donjguido.github.io/canadian-ai-governance-monitor/. Updated every Mondays and Thursdays (no automatic schedule — run the workflow manually, e.g. via `workflow_dispatch` or `gh workflow run`, on that cadence).

## Documents

- [docs/DESIGN.md](docs/DESIGN.md): design plan (scope, status model, architecture, site design, distribution, quality, roadmap)
- [docs/SOURCES.md](docs/SOURCES.md): data-source inventory with what works today
- [docs/MCP.md](docs/MCP.md): MCP server so AI assistants can query the monitor

## Layout

```
data/items.json        canonical store (26 real items as of 2026-09-06)
data/sources.yaml      source inventory and fetcher config
pipeline/models.py     data model and status rules (new = 14 days, closing soon = 7 days)
pipeline/fetch.py      fetchers: Consulting with Canadians CSV, RSS, HTML index pages
pipeline/classify.py   Claude structured-output classifier
pipeline/build.py      renders site/, feed.xml + feed-fr.xml, deadlines.ics + deadlines-fr.ics, items.json, digest.md + digest-fr.md
pipeline/template.html website template (EN/FR toggle, light and dark)
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

Every Monday and Thursday: open the diff of `data/items.json`, check items with `"verified": false` against their source page, set the flag, confirm the French fields match the English, and retire dead items with a `retired_reason`. Commit, then trigger the workflow (push to `main` or `gh workflow run daily.yml`) to rebuild and deploy.

## Outputs

For people:

- Website: https://donjguido.github.io/canadian-ai-governance-monitor/ (French at https://donjguido.github.io/canadian-ai-governance-monitor/?lang=fr)
- RSS: https://donjguido.github.io/canadian-ai-governance-monitor/feed.xml (French: `/feed-fr.xml`)
- Calendar: https://donjguido.github.io/canadian-ai-governance-monitor/deadlines.ics (French: `/deadlines-fr.ics`) — every open item with a stated closing date, as an all-day event with 7-day and 1-day reminders. Subscribe to it (`webcal://donjguido.github.io/canadian-ai-governance-monitor/deadlines.ics`) and Google, Outlook and Apple Calendar re-read it as deadlines are added, changed, or pass.
- Weekly digest: https://donjguido.github.io/canadian-ai-governance-monitor/digest.md (French: `/digest-fr.md`)

For machines:

- Full records (JSON): https://donjguido.github.io/canadian-ai-governance-monitor/items.json
- JSON Feed 1.1, with status and deadline per item: https://donjguido.github.io/canadian-ai-governance-monitor/feed.json
- Orientation for AI agents: https://donjguido.github.io/canadian-ai-governance-monitor/llms.txt
- Every item as Markdown, in one fetch: https://donjguido.github.io/canadian-ai-governance-monitor/llms-full.txt
- MCP server for live queries: `python -m mcp_server` (see [docs/MCP.md](docs/MCP.md))

The site is built to be read by crawlers, agents and screen readers as well as by browsers:
the item list is rendered into the HTML rather than only into JavaScript, the head carries
schema.org JSON-LD describing the dataset and every item, and each build also writes
`robots.txt` (crawling and AI use explicitly permitted, data CC BY 4.0) and `sitemap.xml`.

## Feedback

Spotted a wrong status, a dead link, or a missing consultation? Feedback is welcome via pull request against the [original repo](https://github.com/donjguido/canadian-ai-governance-monitor).

## Licence

Code MIT. Data CC BY 4.0. Government content reproduced under the Open Government Licence – Canada and parliamentary reproduction terms.

© 2026 Julian Guidote.
