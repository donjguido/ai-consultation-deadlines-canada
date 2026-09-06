# Changelog

All notable changes to AI Consultation Deadlines Canada. Releases are tagged in git;
the format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

Fixes from the first scored fork attempt (Ontario, `docs/fork-attempts/2026-09-06-ontario.md`).

### Added
- `docs/FORK-RUBRIC.md`: the pass/fail checklist a fork attempt is scored against.
- `python -m pipeline.classify --print-prompt` prints the classifier prompt without an API key.
- `url_template` on a `csv`/`json_api` source builds an item URL from row fields.
- `html_index` gains `fetch_pages: true` (filter on page text, not link text) and `max_pages`;
  `sitemap` gains `max_pages`, distinct from `limit`.
- Fetch validates `kind` and `columns.title` up front with the valid values in the message, and
  reports a column name the rows do not have once per source.

### Changed
- The scaffold writes `site.yaml` as a text template, so every documentation comment survives;
  secondary-language prose blocks start empty (per-key fallback) instead of as an untranslated
  copy, so a fresh fork's test suite is green. It also empties the inherited `site/`.
- `tests/test_fork.py` reads the parent site's name from its config instead of hardcoding it.

### Fixed
- The keyword pre-filter wrapped the whole alternation in word boundaries, so stem fragments
  (`biom[ée]tri`, `d[ée]cision automatis`) never matched. Fragments now match inside words;
  `compute` and `agent` carry their own boundaries.
- `pipeline.fetch` crashed on a `sources.yaml` with no sources.

## [1.1.0] - 2026-09-06

Made the repository forkable for other geographies without editing Python.

### Added
- `data/site.yaml`: one file for site identity, jurisdiction, language list, licence,
  per-language prose, classifier scope and the keyword pre-filter; `pipeline/config.py`
  loads it and every module reads from it.
- `pipeline/strings/<lang>.yaml`: reusable UI strings per language. Any number of
  languages, or one; translated item fields are generated as `<field>_<lang>`.
- Generic `csv`, `json_api` and `sitemap` fetchers configured entirely in `sources.yaml`.
- `python -m pipeline.fork`: scaffolds a fork (rewrites `site.yaml`, empties the store,
  writes a commented `sources.yaml` template, prints a checklist).
- `python -m pipeline.triage`: the curation report, now committed rather than local.
- `data/forks.yaml` → `forks.json`, listed in `llms.txt` and the footer, so sister sites
  can find each other.
- `docs/FORKING.md` and `docs/CURATION.md`.
- Tests for the config, the fetcher mapping and the fork scaffold, including a build of a
  bilingual, a monolingual and a new-language fork from an empty store.
- The GitHub repository is marked as a template.

### Changed
- The classifier prompt is jurisdiction-neutral; the place, scope and language style come
  from `site.yaml`.
- The template carries no site name, place, author or language pair; the build fills
  `data-i18n` slots from the strings files and injects them for the client.
- The Consulting with Canadians fetcher is now a `csv` source configured in YAML.
- The MCP server takes its name, URL, instructions and language list from the config and
  registers one digest resource per secondary language.
- Tests derive file names, languages and assertions from the config.

## [1.0.0] - 2026-09-06

First stable release of the federal tracker, and the reference template for forks in
other geographies.

### Added
- Four-status model (new, open, closing soon, retired) with 14- and 7-day windows and a
  human-set `verified` flag.
- Fetchers for the Consulting with Canadians CSV, Canada Gazette RSS, parliamentary
  committee pages and e-petitions; Claude structured-output classifier.
- Bilingual (EN/FR) static site with light and dark themes and a mobile layout.
- RSS and JSON feeds in both languages, `deadlines.ics` calendar export, Markdown
  digests, `items.json` API and `llms-full.txt`.
- Read-only MCP server over the published store.
- Offline pytest suite that blocks the deploy on a bad build or record.
- README section inviting forks for other provinces, cities and countries.

### Changed
- Renamed from "Canadian AI Governance Monitor" to "AI Consultation Deadlines Canada"
  so forks can share the "AI Consultation Deadlines" branding with their own place name.
- Repository and GitHub Pages moved to `ai-consultation-deadlines-canada`.

[1.1.0]: https://github.com/donjguido/ai-consultation-deadlines-canada/releases/tag/v1.1.0
[1.0.0]: https://github.com/donjguido/ai-consultation-deadlines-canada/releases/tag/v1.0.0
