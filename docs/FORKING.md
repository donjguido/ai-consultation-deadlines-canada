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
| The README and changelog | `README.md`, `CHANGELOG.md` | Not touched by the scaffold: rewrite the README's first section, start a fresh changelog. |

Nothing in `pipeline/*.py`, `pipeline/template.html`, `mcp_server/` or `tests/` names a place.
The tests read the same config, so a fork's suite stays green without editing tests, and it is
green immediately after the scaffold, before any hand edit.

### `site.yaml` key reference

The scaffolded file carries a comment on every key. The ones people ask about:

| Key | Meaning |
|---|---|
| `slug` | Feed generator id, calendar UIDs, the user agent the fetchers send. |
| `copyright_year` | First year of the footer's copyright line. |
| `jurisdiction.level` | Adjective the generated prose uses: federal, provincial, municipal, EU. |
| `jurisdiction.schema_type` | schema.org type for the dataset's `spatialCoverage`: Country, State, City, AdministrativeArea. |
| `languages.primary` | The language the HTML is rendered in before any JavaScript runs. |
| `locales` | BCP 47 tag per language, for `<html lang>`, hreflang, feeds and date formatting. |
| `licence.data`, `licence.data_url` | The licence on the published dataset (items.json, feeds, calendars). |
| `text.<lang>.title` | Site name in the header and the feeds. |
| `text.<lang>.page_title` | The page `<title>` and the feed titles. |
| `text.<lang>.tagline` | One sentence under the site name. |
| `text.<lang>.description` | Meta description and schema.org description. |
| `text.<lang>.channels` | The kinds of channel monitored, as a list in prose. |
| `text.<lang>.audience` | Who can take part, e.g. "people in Ontario". |
| `text.<lang>.cadence` | How often the site is updated, e.g. "twice a week". |
| `text.<lang>.calendar_description` | Description of the `.ics` calendar. |
| `text.<lang>.dataset_name` | schema.org Dataset name. |
| `text.<lang>.government_licence` | The licence government content is reproduced under, e.g. "Open Government Licence - Ontario". `null` hides the licence line from the site, feeds and digest. |
| `classifier.scope` | One sentence describing the channels being screened; it opens the classifier prompt. |
| `classifier.place` | Used in "in <place>" throughout the prompt. |
| `classifier.official_names` | Optional. A free-text instruction on which naming conventions the translated fields follow, e.g. "use the official French name of a ministry or programme when one exists". |
| `classifier.style.<lang>` | One paragraph per secondary language on how to write it well: register, date format, typography. |
| `analytics.goatcounter` | Optional. A GoatCounter count URL (`https://<code>.goatcounter.com/count`). Empty, the page loads no analytics; set, it counts visits and clicks on item links, calendar buttons, feed links, topic chips and the language toggle as events, with no cookies and no identifiers. Create your own account; never inherit the parent's. |
| `newsletter.buttondown` | Optional. The username of a [Buttondown](https://buttondown.com/) account. Empty, the page shows no subscribe form and nothing posts anywhere; set, the page shows Buttondown's hosted form (addresses go to Buttondown, never to your repo) and `python -m pipeline.newsletter` files a fortnightly issue through its API. Needs the `BUTTONDOWN_API_KEY` repository secret. Create your own account; never inherit the parent's. |
| `prefilter_keywords` | Regex fragments, one alternation. A fragment matches anywhere inside a word unless it carries its own `\b`, so `biom[ée]tri` catches every inflection and `\bAI\b` stays a whole word. |

`version` is your site's own version string; it appears in the calendar PRODID and the fetchers'
user agent, so bump it when you release. `classifier.official_names` is a bare clause without a
final full stop; the prompt builder punctuates it.

`python -m pipeline.classify --print-prompt` prints the prompt your `classifier` block builds,
without an API key.

### If your primary language is not English

Everything reads the primary language from `site.yaml`, but three things are worth knowing
before you start a French-, German- or Spanish-first site:

- The scaffold's draft prose is English whatever the primary language. Replace the primary
  `text` block wholesale; the untranslated-copy test only guards the secondary blocks, so
  nothing else will catch an English primary block left in place.
- In `items.json` the unsuffixed fields (`title`, `summary`, `body`, ...) carry the primary
  language, and `<field>_<lang>` carries each secondary language. A French-primary site
  therefore has a French `title` and an English `title_en`. The classifier, the feeds, the
  MCP server and the site all follow that rule.
- The sentence frames the build fills in (the meta description, the schema.org dataset
  description, the lead of `llms.txt`) come from the primary language's strings file, so a
  new language needs those keys translated too. `date_style: long` in a strings file formats
  dates server-side with that file's `date_format` and `months_short`, and the page's client
  formatter uses the same locale, so the first paint and a re-render agree.
- The rest of `llms.txt` (the headings and the explanation of statuses) is English by design:
  it is addressed to agents, and English is the language they all read.

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
   `--slug` overrides the slug derived from the name (accents are transliterated, so an
   accented name still gives a clean slug); `--year` sets the copyright year; `--root` acts on
   another checkout. `--dry-run` shows the plan and the checklist without writing. The command rewrites
   `site.yaml` (keeping a comment on every key), empties `items.json`, resets `forks.yaml`
   (listing the original as a sister), replaces `sources.yaml` with a commented template of
   every fetcher kind, and empties the generated `site/` so the original's rendered pages do
   not survive into your first build. `python -m pytest` is green at this point.

   The scaffold does not touch `README.md` or `CHANGELOG.md`; rewrite the README's first
   section and start a fresh changelog before you publish.

3. **Rewrite the prose** in `data/site.yaml` → `text`. The scaffold generates a serviceable
   first draft from the place name, in English whatever the primary language is, and leaves
   each secondary block empty with the primary values shown as comments. A missing key falls
   back to the primary language per key, so the site builds before you translate, and
   `test_config.py` fails if a secondary block is mostly a copy of the primary. Set
   `government_licence`, which the scaffold leaves `null`, and fill in `classifier.official_names`
   and `classifier.style.<lang>` from the commented examples.

4. **Add sources** to `data/sources.yaml`. See the fetcher kinds below. Run
   `python -m pipeline.fetch data/candidates.json` and read the per-source counts. A source
   with a misspelt `kind` or a missing `columns.title` fails before anything is fetched, with
   the valid values in the message; a `columns.title` that names a column the rows do not
   have prints the row's real column names once. Zero yield from a source with no message
   means the URL or the pre-filter is wrong for it.

5. **Tune the pre-filter and the classifier block** in `site.yaml`. The pre-filter is a list of
   regex fragments; a term missing in one of your languages silently drops every record in it.
   `python -m pipeline.classify --print-prompt` shows the prompt your block produces.

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

10. **Score the experience** against [FORK-RUBRIC.md](FORK-RUBRIC.md) and file what you hit as
    an issue on the original. Every criterion there is a promise this page makes; a fail is a
    bug in the original, not in your fork.

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

**`sitemap`** — an XML sitemap or sitemap index. `include` is a regex on the URL. Every
matching page is fetched and passes the pre-filter on its text, so this is the fetcher that
works when a site has no feed and its index pages carry uninformative link text. `max_pages`
caps how many matching pages are fetched per run (default 500); `limit` caps how many
candidates the source contributes (default 200). Count the matching URLs before setting them:
a broad `include` on a large sitemap is a long crawl.

**`html_index`** — an index page scraped for links matching a CSS `selector`. By default the
pre-filter sees the link text only, so a page whose anchors read "Participate" or carry a
project name yields nothing. `fetch_pages: true` fetches each linked page first and filters on
its text, one request per link, capped by `max_pages` (default 100); a generic anchor text is
then replaced by the page title. The brittle one; it breaks when the page is restructured.
Treat that as expected maintenance.

**Building a URL from row fields.** A registry API that publishes a slug but no link (CKAN's
`name`, for example) can carry `url_template: https://data.example.gov/dataset/{name}` on the
source; `{...}` placeholders are dotted paths into the row. A real `columns.url` wins when the
row has one, and a placeholder the row cannot fill falls back to `portal`. Dotted paths accept
list indices, so `resources.0.url` reads the first resource's link.

For anything that blocks automated fetches or publishes only PDFs, list it under a Tier 3
comment and check it by hand on the curation sweep.

## Adding a language

1. Copy `pipeline/strings/en.yaml` to `pipeline/strings/<lang>.yaml` and translate every value.
   It is about sixty keys, and `test_config.py` enforces that every key is present and that the
   `type:` and `topic:` maps cover every member of the type vocabulary and the `TOPICS` list.
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
