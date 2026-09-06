# Forking this monitor for another geography

The pipeline is built so that a province, a city, another country or a regional body can run
its own AI Consultation Deadlines site by editing three data files and no Python. This page is
the complete guide; the README has the short version.

## What is geography-specific, and where it lives

| Concern | File | What to change |
|---|---|---|
| Site name, URL, repo, author, licence, jurisdiction, language list, keywords, per-language prose | `data/site.yaml` | Everything. `python -m pipeline.fork` writes a first draft. |
| Which pages to fetch and how | `data/sources.yaml` | Replace the Canadian sources with yours (see fetcher kinds below). |
| The keyword pre-filter that runs before the classifier | `data/site.yaml` → `prefilter_keywords` | Add terms in every language your sources publish in. |
| The classifier prompt's jurisdiction block | `data/site.yaml` → `classifier` | `place`, `scope`, and per-language `style` notes. The prompt itself in `pipeline/classify.py` is neutral. |
| UI strings per language | `pipeline/strings/<lang>.yaml` | English and French ship. For another language, copy `en.yaml` to `<lang>.yaml` and translate. |
| The store | `data/items.json` | Starts empty. |
| Sister sites | `data/forks.yaml` | The original is listed; add siblings as you find them. |

Nothing in `pipeline/*.py`, `pipeline/template.html`, `mcp_server/` or `tests/` names a place.
The tests read the same config, so a fork's suite stays green without editing tests.

## Step by step

1. **Create your repo** from the template (the GitHub "Use this template" button; the repo is
   marked as a template) or fork it. Keep the "AI Consultation Deadlines" prefix plus your place
   name if you want the family of sites to be recognisable together.

2. **Scaffold.** From the repo root:

   ```
   python -m pipeline.fork --name "AI Consultation Deadlines Ontario" \
       --place Ontario --level provincial --schema-type State \
       --url https://you.github.io/ai-consultation-deadlines-ontario \
       --repo https://github.com/you/ai-consultation-deadlines-ontario \
       --author "Your Name" --author-url https://github.com/you \
       --languages en,fr --locale en=en-CA --locale fr=fr-CA
   ```

   `--languages` is primary first; `--languages en` gives a monolingual site with no toggle.
   `--dry-run` shows the plan. The command rewrites `site.yaml`, empties `items.json`, resets
   `forks.yaml` (listing the original as a sister) and replaces `sources.yaml` with a commented
   template of every fetcher kind. It prints a checklist of what is left.

3. **Rewrite the prose** in `data/site.yaml` → `text`. The scaffold generates serviceable
   English from the place name and copies it under each secondary language; translate those.
   `test_config.py` fails if a secondary block is mostly an untranslated copy of the primary.

4. **Add sources** to `data/sources.yaml`. See the fetcher kinds below. Run
   `python -m pipeline.fetch data/candidates.json` and read the per-source counts; zero yield
   from a source you expected to work means the URL or column mapping is wrong.

5. **Tune the pre-filter and the classifier block** in `site.yaml`. The pre-filter is a list of
   regex fragments; a term missing in one of your languages silently drops every record in it.

6. **Run the tests:** `python -m pytest`. Offline, about 20 seconds. The suite validates the
   config, the strings files, the store and the build, and the deploy workflow refuses to
   publish if it fails.

7. **Classify and curate.** `ANTHROPIC_API_KEY=... python -m pipeline.classify data/candidates.json data/items.json`
   writes `verified: false` items. The human loop in [CURATION.md](CURATION.md) is what makes
   the site trustworthy; the pipeline never sets `verified` to true.

8. **Deploy.** Enable GitHub Pages (Settings → Pages → Source: GitHub Actions), add the
   `ANTHROPIC_API_KEY` secret, and run the "Monitor run" workflow. It rebuilds from the
   store even without the key.

9. **Tell the family.** Open a pull request on the original repo adding your site to
   `data/forks.yaml`. Every site publishes `forks.json` and lists its siblings in the footer and
   in `llms.txt`, so an agent that finds one can find all.

## Fetcher kinds

Each entry in `sources.yaml` has `key` (stable, becomes the `source` field on items), `kind`,
`body` (the owning organisation), and the fields below. `enabled: false` keeps an entry on
record without running it. `tier` and `notes` are documentation only.

**`csv`** — a registry's open-data CSV export.

```yaml
- key: registry
  kind: csv
  body: "Consultation registry"
  csv: https://example.gov/consultations.csv     # or url:
  portal: https://example.gov/consultations       # fallback url when a row has none
  id_prefix: reg-                                 # default "<key>-"
  open_statuses: [O, P]                           # rows whose status column is elsewhere are dropped
  encoding: utf-8-sig                             # default
  delimiter: ","                                  # default
  columns:
    id: registration_number     # optional; defaults to a slug of the title
    title: title_en
    title_fr: title_fr          # any <field>_<lang> for a configured language may be mapped
    url: profile_page_en
    opened: start_date          # first 10 characters are kept, so ISO datetimes work
    closes: end_date
    status: status
    body: owner_org_title       # optional; falls back to the source's body
    text: [title_en, description_en, subjects]   # joined for the keyword pre-filter
```

**`json_api`** — a JSON endpoint. Same `columns` contract; values are dotted paths.

```yaml
- key: registry_api
  kind: json_api
  body: "Consultation registry"
  url: https://example.gov/api/consultations?status=open
  items_path: data.items        # dotted path to the list; omit if the response is the list
  columns:
    id: id
    title: attributes.title
    url: links.self
    closes: attributes.closes_on
    text: [attributes.title, attributes.summary]
```

**`rss`** — an RSS or Atom feed. `fetch_pages: true` fetches each linked page so the classifier
can read a comment deadline that only appears in the notice text.

**`sitemap`** — an XML sitemap or sitemap index. `include` is a regex on the URL; `limit` caps
pages fetched per run (default 200). Every matching page is fetched and passes the pre-filter on
its text. Useful for a ministry site with no feed and a predictable URL scheme.

**`html_index`** — an index page scraped for links matching a CSS `selector`. The brittle one;
it breaks when the page is restructured. Treat that as expected maintenance.

For anything that blocks automated fetches or publishes only PDFs, list it under a Tier 3
comment and check it by hand on the curation sweep.

## Adding a language

1. Copy `pipeline/strings/en.yaml` to `pipeline/strings/<lang>.yaml` and translate every value.
   Keep the `{n}`, `{total}`, `{x}`, `{site}`, `{year}`, `{author}`, `{repo}` placeholders.
   Set `date_style: long` if readers expect a formatted date rather than ISO.
2. Add the code to `languages.secondary` and a BCP 47 tag to `locales` in `site.yaml`.
3. Add a `text.<lang>` block to `site.yaml` and a `classifier.style.<lang>` paragraph.
4. Rebuild. The model, the classifier, the feeds, the calendar, the digest, the MCP server and
   the site all pick the language up from the config: items gain `title_<lang>`,
   `summary_<lang>` and so on, and the build writes `feed-<lang>.xml`, `deadlines-<lang>.ics`
   and `digest-<lang>.md`.

Existing store records need no migration; a missing translation falls back to the primary
language per field, and `python -m pipeline.triage` lists what is untranslated.

## What stays the same

The four-status model and its windows, the `verified` flag, the `TOPICS` vocabulary in
`pipeline/classify.py` (add tags there, with labels in each strings file), the model and effort
the classifier runs at, and the single-store architecture. These are the invariants the tests
guard, and the reason the family of sites can share tooling.
