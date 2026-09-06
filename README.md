# AI Consultation Deadlines Canada

A public tracker of every federal channel through which Canadians can shape how AI is governed: consultations, parliamentary calls for briefs, Canada Gazette comment periods, funding calls, standards reviews, and e-petitions. Each item is labelled new, open, closing soon, or retired, with a plain-language summary and a concrete way to participate.

Status: **version 1.1.0, 6 September 2026** (see [CHANGELOG.md](CHANGELOG.md)). Live at https://donjguido.github.io/ai-consultation-deadlines-canada/. Updated every Mondays and Thursdays (no automatic schedule — run the workflow manually, e.g. via `workflow_dispatch` or `gh workflow run`, on that cadence).

## Documents

- [docs/DESIGN.md](docs/DESIGN.md): design plan (scope, status model, architecture, site design, distribution, quality, roadmap)
- [docs/SOURCES.md](docs/SOURCES.md): data-source inventory with what works today
- [docs/MCP.md](docs/MCP.md): MCP server so AI assistants can query the monitor
- [docs/CURATION.md](docs/CURATION.md): the twice-weekly human loop, the triage report, the retire-reason rules
- [docs/FORKING.md](docs/FORKING.md): how to run this for another geography without touching Python

## Layout

```
data/site.yaml         site identity: name, URL, author, jurisdiction, languages, licence,
                       per-language prose, classifier scope, keyword pre-filter
data/sources.yaml      source inventory and fetcher config
data/items.json        canonical store (26 real items as of 2026-09-06)
data/forks.yaml        sister sites for other geographies, published as forks.json
pipeline/config.py     loads site.yaml and the per-language strings; every module reads it
pipeline/strings/      UI strings per language (en.yaml, fr.yaml; add <lang>.yaml for more)
pipeline/models.py     data model and status rules (new = 14 days, closing soon = 7 days)
pipeline/fetch.py      fetchers: csv, json_api, rss, sitemap (generic, YAML-configured), html_index
pipeline/classify.py   Claude structured-output classifier; prompt built from site.yaml
pipeline/build.py      renders site/, feeds, calendars, digests, items.json, llms.txt, forks.json
pipeline/triage.py     the curation report: yield, unseen, stale, needs-check, untranslated
pipeline/fork.py       scaffolds a fork for another geography
pipeline/template.html website template (language toggle, light and dark)
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

### Tests

```
pip install pytest -r mcp_server/requirements.txt
python -m pytest
```

Offline and quick. The suite checks the status rules, validates `data/items.json`,
renders the site into a temp directory and inspects every artefact, checks the
iCalendar feed against the parts of RFC 5545 that fail silently in a calendar client
(CRLF endings, 75-octet folding, escaped separators), and exercises the MCP server.
The deploy workflow runs it before fetching anything and again after classification,
so a failing test blocks the deploy. Run it before committing changes to the pipeline,
the template, or the store.

## Curation

Every Monday and Thursday: fetch, run `python -m pipeline.triage`, work its UNSEEN, STALE, NEEDS CHECK and NO FRENCH sections against the source pages, set `verified`, retire dead items with a `retired_reason`, rebuild, test, commit, then trigger the workflow (push to `main` or `gh workflow run daily.yml`). The full loop and the record rules are in [docs/CURATION.md](docs/CURATION.md).

## Outputs

For people:

- Website: https://donjguido.github.io/ai-consultation-deadlines-canada/ (French at https://donjguido.github.io/ai-consultation-deadlines-canada/?lang=fr)
- RSS: https://donjguido.github.io/ai-consultation-deadlines-canada/feed.xml (French: `/feed-fr.xml`)
- Calendar: https://donjguido.github.io/ai-consultation-deadlines-canada/deadlines.ics (French: `/deadlines-fr.ics`) — every open item whose closing date is still ahead, as an all-day event with reminders a week and a day before. Subscribe to it (`webcal://donjguido.github.io/ai-consultation-deadlines-canada/deadlines.ics`) and Google, Outlook and Apple Calendar re-read it as deadlines are added, changed, or pass.
- Weekly digest: https://donjguido.github.io/ai-consultation-deadlines-canada/digest.md (French: `/digest-fr.md`)

For machines:

- Full records (JSON): https://donjguido.github.io/ai-consultation-deadlines-canada/items.json
- Sister sites for other geographies: https://donjguido.github.io/ai-consultation-deadlines-canada/forks.json
- JSON Feed 1.1, with status and deadline per item: https://donjguido.github.io/ai-consultation-deadlines-canada/feed.json
- Orientation for AI agents: https://donjguido.github.io/ai-consultation-deadlines-canada/llms.txt
- Every item as Markdown, in one fetch: https://donjguido.github.io/ai-consultation-deadlines-canada/llms-full.txt
- MCP server for live queries: `python -m mcp_server` (see [docs/MCP.md](docs/MCP.md))

The site is built to be read by crawlers, agents and screen readers as well as by browsers:
the item list is rendered into the HTML rather than only into JavaScript, the head carries
schema.org JSON-LD describing the dataset and every item, and each build also writes
`robots.txt` (crawling and AI use explicitly permitted, data CC BY 4.0) and `sitemap.xml`.

## Fork it for your own geography

The federal channels listed here are only one layer of Canadian governance, and Canada is only one country. We would explicitly love for other coders to fork this design and replicate it for their own geographies: a province or territory, a city, another national government, or a regional body like the EU.

The design is built to travel, and nothing in the Python names a place. Everything geography-specific lives in three data files: `data/site.yaml` (name, URL, author, jurisdiction, languages, licence, prose, classifier scope, keyword pre-filter), `data/sources.yaml` (which pages to fetch and how) and `data/items.json` (the store). The four-status model, the classifier, the template, the feeds, the calendar, the digest, the MCP server and the test suite all read that config. To start a fork:

1. Click "Use this template" (the repo is a GitHub template) or fork it.
2. Run the scaffold, which rewrites `site.yaml`, empties the store and leaves a commented `sources.yaml`:

   ```
   python -m pipeline.fork --name "AI Consultation Deadlines Ontario" --place Ontario --level provincial \
       --url https://you.github.io/ai-consultation-deadlines-ontario --repo https://github.com/you/... \
       --author "Your Name" --languages en,fr
   ```

   `--languages en` gives a single-language site; another language needs only a `pipeline/strings/<lang>.yaml`.
3. Add your registry, legislature, gazette and petition sources. The `csv`, `json_api`, `rss` and `sitemap` kinds are configured entirely in YAML.
4. Run `python -m pytest` (offline), then fetch, classify and curate. The `verified` flag is a human claim and the pipeline never sets it.
5. Open a pull request adding your site to `data/forks.yaml`; every site publishes `forks.json` and lists its siblings, so the family finds each other.

The full guide, including the fetcher reference and how to add a language, is [docs/FORKING.md](docs/FORKING.md); [docs/FORK-RUBRIC.md](docs/FORK-RUBRIC.md) is the pass/fail checklist a fork is scored against. Natural next forks in Canada are the provinces and territories, each of which runs its own consultation portal, legislative committees and gazette.

## Feedback

Spotted a wrong status, a dead link, or a missing consultation? Feedback is welcome via pull request against the [original repo](https://github.com/donjguido/ai-consultation-deadlines-canada).

## Licence

Code MIT. Data CC BY 4.0. Government content reproduced under the Open Government Licence – Canada and parliamentary reproduction terms.

© 2026 Julian Guidote.
