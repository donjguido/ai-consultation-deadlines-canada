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
- This site and any sister sites for other geographies: https://donjguido.github.io/ai-consultation-deadlines-canada/forks.json (no sister sites are listed at present)
- JSON Feed 1.1, with status and deadline per item: https://donjguido.github.io/ai-consultation-deadlines-canada/feed.json
- Orientation for AI agents: https://donjguido.github.io/ai-consultation-deadlines-canada/llms.txt
- Every item as Markdown, in one fetch: https://donjguido.github.io/ai-consultation-deadlines-canada/llms-full.txt
- MCP server for live queries: `python -m mcp_server` (see [docs/MCP.md](docs/MCP.md))

The site is built to be read by crawlers, agents and screen readers as well as by browsers:
the item list is rendered into the HTML rather than only into JavaScript, the head carries
schema.org JSON-LD describing the dataset and every item, and each build also writes
`robots.txt` (crawling and AI use explicitly permitted, data CC BY 4.0) and `sitemap.xml`.

## Forking it for another geography

**Not yet, please.** The federal site comes first. Until it is stable and the Monday/Thursday
curation cadence has a track record behind it, we are not inviting anyone to stand up their
own version. Two forks (Ontario and Québec) were built and scored as design tests; both
repositories have since been made private, so `data/forks.yaml` is empty and this site lists
no sister sites. This section turns back into an invitation once the federal site is where we
want it.

The design is built to travel all the same, and nothing in the Python names a place.
Everything geography-specific lives in three data files: `data/site.yaml` (name, URL, author,
jurisdiction, languages, licence, prose, classifier scope, keyword pre-filter),
`data/sources.yaml` (which pages to fetch and how) and `data/items.json` (the store). The
four-status model, the classifier, the template, the feeds, the calendar, the digest, the MCP
server and the test suite all read that config, and `python -m pipeline.fork` rewrites
`site.yaml` for a new place without touching Python.

The mechanics are documented and still work: [docs/FORKING.md](docs/FORKING.md) is the full
guide, including the fetcher reference and how to add a language, and
[docs/FORK-RUBRIC.md](docs/FORK-RUBRIC.md) is the pass/fail checklist a fork attempt is scored
against. If you want to run one for your province, territory, city or country, please open an
issue saying so rather than launching it. Knowing who is waiting is genuinely useful, and we
would rather help you start once than watch a half-built sister site go stale.

## Feedback

Spotted a wrong status, a dead link, or a missing consultation? Feedback is welcome via pull request against the [original repo](https://github.com/donjguido/ai-consultation-deadlines-canada).

## Licence

Code MIT. Data CC BY 4.0. Government content reproduced under the Open Government Licence – Canada and parliamentary reproduction terms.

© 2026 Julian Guidote.
