# Canadian AI Governance Monitor: design plan

Version 0.1, 6 September 2026. Companion document: [SOURCES.md](SOURCES.md) (data-source inventory).

## 1. What it is

A public monitor that tells Canadians, in plain language, every federal channel through which they can currently shape how AI is governed: public consultations, parliamentary calls for briefs, Canada Gazette comment periods, funding and research calls, national-standard public reviews, and e-petitions. Each item is labelled **new**, **open**, **closing soon** (within seven days), or **retired**, and says concretely how to participate.

The gap it fills: the federal government publishes the raw data (the Consulting with Canadians open dataset, Gazette RSS feeds, committee pages) but offers no topic-based alerting, no cross-source view, and nothing that covers Parliament, standards bodies and petitions together. The only Canadian product that does this, Gnowit's Consultations Tracker, is sold to lobbyists at roughly $500 to $1,000 per month. Volunteer civic-tech cousins (openparliament.ca alerts, Tabs Toronto) cover Hansard and municipal agendas, not federal AI consultations.

## 2. Who it is for, and the one job

Primary audience: Canadians who care about AI safety but are not professional lobbyists. Researchers, students, civil-society staff, and engaged members of the public. Secondary: journalists and MPs' staff who want a single dated list.

The page has one job: within ten seconds, show what is open and what is about to close, and give a next step. Everything else (archives, feeds, API) supports that.

## 3. Scope

**In scope (federal only, v0.1):**

| Channel | Example | Why it counts |
|---|---|---|
| Departmental consultations | ISED's 2026 AI transparency consultation | Direct input into policy design |
| Parliamentary studies with calls for briefs | INDU, ETHI, SRSR, Senate SOCI/RIDR/TRCM AI studies | Briefs become the evidentiary record for legislation |
| Canada Gazette Part I comment periods | Proposed regulations on biometrics, medical AI | Legally mandated comment windows |
| Funding and research calls | CAISI Catalyst grants, Sovereign Compute program | Shapes what safety work gets resourced |
| National-standard public reviews | CAN/DGSI 138 clinical AI | Standards become de facto rules |
| E-petitions | e-7550 on AI data centres | Low-cost mass participation, forces a government response |
| Bills on the committee path | C-34 (chatbot duties), C-36 (privacy) | Briefs window opens on referral; worth watching before it opens |

**Out of scope for v0.1:** provincial and municipal channels, private-sector or university consultations, events and webinars, and news. These are natural extensions once the federal spine is reliable.

**Relevance rule:** an item is included when a member of the public could plausibly influence how AI systems are governed, regulated, procured, funded, or made safe in Canada. That includes items not labelled "AI" (a privacy bill, a deepfake election-integrity study). It excludes items where AI is incidental.

## 4. Status model

Status is computed from dates, not typed by hand, so it never goes stale.

| Badge | Rule | Rationale |
|---|---|---|
| **New** | Opened, or first observed by the monitor, within the last 14 days, and still open | Long enough to survive a weekly digest cycle |
| **Open** | No closing date, or closing date in the future, and not withdrawn | Default state |
| **Closing soon** | Closes within 7 days | Matches the user's request; also the realistic minimum time to draft a short brief |
| **Retired** | Closing date has passed, or curator marked withdrawn or superseded | Kept visible for six months so people can see what they missed and what the follow-up is |

An item can be both New and Closing soon (a short Gazette comment window). Items with no stated deadline (rolling committee briefs) stay Open until the study reports; the curator retires them with a reason. A fifth state, **Upcoming** (bill introduced but not yet referred to committee), is a likely v0.2 addition; in v0.1 these are shown as Open with "not yet open" in the how-to-participate field.

Every item carries a **verified** flag. Unverified items (dates taken from a search snippet or classifier extraction) show a warning mark on the site until a human checks the source page. This is the main quality control.

## 5. Architecture

Static-first. Nothing runs on a server; a scheduled job regenerates flat files once a day.

```
sources.yaml ──► fetch.py ──► candidates.json ──► classify.py ──► items.json
                 (CSV, RSS,     (keyword           (Claude,           (canonical
                  HTML index)    pre-filter)        structured out)    store, in git)
                                                                          │
                        ┌──────────┬───────────────┬───────────────┬───────┤
                        ▼          ▼               ▼               ▼       ▼
                   index.html  feed(-fr).xml  deadlines(-fr).ics items.json digest(-fr).md
                   (site,EN/FR) (RSS, EN/FR)  (calendar, EN/FR)  (JSON API) (email, EN/FR)
```

**Fetch.** Each source in `data/sources.yaml` maps to one of three fetchers: the Consulting with Canadians open-data CSV (tier 1, structured, bilingual, has dates), RSS (Canada Gazette Part I, tier 1), and HTML index scraping (committee pages, ISED and OPC consultation lists, tier 2). A broad bilingual keyword filter drops obviously irrelevant records before any model call.

**Classify.** Each new candidate goes once to Claude with a structured-output schema: relevant or not, confidence, type, plain-language summary, why it matters for AI safety, how to participate, topic tags from a controlled vocabulary, and the closing date if stated in the page text. The same call returns the French of every prose field, so an item arrives in the store bilingual rather than waiting on a translation pass. Items already in the store are never re-classified; only their closing date and retired flag are refreshed. This keeps model cost proportional to new items, not to the size of the archive.

**Store.** `data/items.json` is the single canonical file, committed to git on every run. Git history is the audit trail: anyone can see when an item appeared, when its date changed, and who verified it. No database is needed at this scale (hundreds of items).

**Build.** One script renders five outputs from the store: the website (a single self-contained HTML file with the data inlined, filterable client-side, EN/FR toggle), the RSS feed, an iCalendar feed of closing dates, a JSON copy for programmatic use, and a Markdown digest ready to paste or send.

**Schedule.** No automatic cron: the curator triggers the pipeline manually (push to `main` or `workflow_dispatch`) every Monday and Thursday, and it deploys to GitHub Pages.

**Curate.** The human step is a weekly 30- to 60-minute review: open the diff of `items.json`, check unverified items against their source pages, set `verified: true`, add French titles where the source is English-only, retire dead items with a reason, and add anything from the tier-3 watch list (CAISI, TBS, DGSI, LEGISinfo) that the fetchers cannot reach. Edits are plain JSON commits; no admin UI is needed yet.

## 6. The website

Design intent: a reference tool that reads like a briefing sheet, not a marketing page. Choices made in the prototype:

- **Summary strip first.** Four counts (New, Open, Closing soon, Retired) that double as filters. The Closing-soon count is the number a returning visitor wants.
- **List, not cards.** Each item is a row with a coloured status stripe, a monospace date column (closing date, days left, opened date), then the title, body, type, summary, "why it matters", and a bolded "how to participate" line. Rows are sorted soonest-closing first, undated open items next, retired items last.
- **Filters that reflect the data.** Type and department dropdowns, the eight most-used topic tags as chips, and free-text search. Filters are built from the data, so they never list empty categories.
- **Bilingual from day one.** Every item carries both languages — title, body, summary, why-it-matters and how-to-participate — alongside the UI strings, topic labels and date formats; the toggle persists per browser. A missing French field falls back to English rather than rendering blank.
- **Colour carries state.** The accent is the green of the Commons chamber. New is blue, Closing soon is amber, Retired is grey; these are semantic and separate from the accent. Light and dark themes are both designed.
- **The deadline is the deliverable, so it goes in the calendar.** Every open item with a stated closing date carries an *Add deadline to calendar* menu (Google, Outlook, or an `.ics` download for Apple Calendar and Outlook desktop), and a single *Add all deadlines* button covers the whole set. Knowing a consultation closes on the 23rd is worthless if the user forgets on the 22nd; this is the shortest path from reading the page to acting on it.
- **Honesty markers.** A warning glyph on unverified items and a footer that explains exactly how badges are computed and tells people to confirm deadlines on the official page. The same honesty carries into the calendar: an unverified item's event body says the date has not been checked, rather than being silently dropped from the feed.
- **Readable without JavaScript.** `build.py` renders the item list into the HTML itself, not only into the script that powers filtering; the page a crawler, a screen reader, or a text-mode agent gets is the page a browser shows. The client skips its first render in English so the two are byte-identical. Filters and the language toggle are the only JavaScript-only parts, and they hide themselves when scripting is off.
- **Structured for machines as well as people.** schema.org JSON-LD in the head describes the monitor as a `Dataset` and every entry as a `CreativeWork` with its status, deadline, department and topics, so a search engine or agent can read the state of a consultation without parsing prose. Proper document landmarks, a heading outline, labelled controls, a skip link, `<time>` elements on every date, and a per-item anchor (`#item-<id>`) make the same structure available to assistive technology.

## 7. Distribution channels

| Channel | Status | Notes |
|---|---|---|
| Website | v0.1 built | GitHub Pages, custom `.ca` domain |
| RSS | v0.1 built | One feed; per-topic feeds are a small addition |
| Calendar | v0.1 built | `deadlines.ics` and `deadlines-fr.ics`: every open item whose stated closing date is still ahead, as an all-day event with reminders a week and a day before. Past deadlines are filtered out server-side at build time and again in the browser, which knows the reader's real date between the twice-weekly builds. Subscribable by `webcal://`, so Google, Outlook and Apple Calendar re-read it as deadlines are added, changed or pass. Per-item buttons use the Google and Outlook web templates, which take one event per URL; anything bulk goes through the `.ics` |
| JSON | v0.1 built | Same records as the site; lets others build on it |
| Email digest | Text generated; sending not wired | Weekly Monday digest plus an instant alert when an item enters Closing soon. Buttondown or a self-hosted Listmonk instance; both read the RSS feed or accept the digest by API |
| MCP server | Built (`mcp_server/`, see [MCP.md](MCP.md)) | A thin read-only server exposing `list_open`, `closing_soon`, `list_new`, `search`, `get_item`, `list_topics` and `monitor_status` over the published `items.json`, plus `monitor://` resources. Stdio by default (free to run); streamable HTTP available if a host is ever funded |
| Social | Not planned yet | The RSS feed can drive a Bluesky or Mastodon bot for free if wanted |

### Machine readability

Agents and crawlers are a first-class audience, not an afterthought: a lot of the people this monitor is meant to reach will meet it through an assistant rather than by visiting the site. Every build therefore also publishes

- `llms.txt` — an orientation page in the llmstxt.org shape: what this is, how status is derived, what the licence allows, and where the structured data lives.
- `llms-full.txt` — the entire corpus as Markdown, so an agent can read everything in one fetch instead of crawling and re-deriving it.
- `feed.json` — JSON Feed 1.1, with a namespaced `_monitor` object per item carrying status, deadline, days left and the verified flag.
- `robots.txt` — crawling and AI training explicitly permitted, with the licence terms and a pointer to the structured outputs stated in the file itself, plus named `Allow` groups for the AI crawlers that back off when no rule mentions them.
- `sitemap.xml`, a canonical URL, `hreflang` alternates for both official languages (French is addressable at `?lang=fr`), and Open Graph metadata.

One caveat worth recording: on a `github.io` **project** page the `robots.txt` crawlers actually read is the one at the domain root, which this repo does not own. The file published here is correct and becomes authoritative as soon as the monitor moves to the custom `.ca` domain; until then it documents intent and is still read by tools that fetch it directly.

## 8. Quality, ethics, and failure modes

- **Missed items are invisible.** Mitigation: broad keyword filter, weekly human sweep of the tier-3 watch list, and a public "report a missing consultation" link that files a GitHub issue.
- **Wrong deadlines are worse than none.** Mitigation: the verified flag, dates shown alongside the source link, and the footer instruction to confirm on the official page. Closing-soon alerts are only sent for verified items.
- **Classifier drift.** Mitigation: log every classification with its confidence; sample ten per week for review; keep a small labelled set (the 26 seed items) as a regression test.
- **Source changes.** Government sites restructure without notice. Mitigation: each fetcher fails independently and loudly in the Actions log; a fetcher returning zero candidates for seven days triggers a review.
- **Neutrality.** The monitor describes channels; it does not tell people what to say. The "why it matters" line is limited to why the channel bears on AI safety, not to a position.
- **Privacy.** No accounts, no analytics beyond aggregate page counts, subscriber emails held only by the newsletter provider.
- **Licensing.** Government content is used under the Open Government Licence – Canada and the parliamentary reproduction terms; the monitor's own code is MIT and its data CC BY 4.0.

## 9. Roadmap

1. Harden fetchers: fix petitions, add ourcommons.ca XML and LEGISinfo bill tracking.
2. Run the classifier from GitHub Actions on a manual Monday/Thursday trigger and publish the site, RSS and JSON from GitHub Pages.
3. Email digest (weekly plus closing-soon alerts).
4. ~~MCP server so assistants can query the store directly.~~ Done: `mcp_server/`, see [MCP.md](MCP.md).
5. Provincial coverage once the federal spine is reliable.

## 10. What is in the prototype today

- `pipeline/` — fetch, classify, and build scripts; data model with the status logic; site template.
- `data/items.json` — 26 real items as of 6 September 2026 (13 open, 4 of them new, 13 retired), each with source link, dates, summary, why-it-matters, how-to-participate, topics, a verified flag, and French for every prose field.
- `data/sources.yaml` — source inventory with tiers and known issues.
- `site/` — generated website, RSS feed, iCalendar feed, JSON, and weekly digest, the feed, calendar and digest in both official languages. Only two of the thirteen open items currently state a closing date, so `deadlines.ics` holds two events; the rest are rolling committee briefs with no announced deadline.
- `.github/workflows/daily.yml` — manually-triggered run and deployment (Monday/Thursday cadence, no automatic cron).

Not yet done: live classification run against an API key (the classifier is written and the fetchers return real candidates; the seed store was curated from research rather than a model run), petition and Senate fetchers, email sending.
