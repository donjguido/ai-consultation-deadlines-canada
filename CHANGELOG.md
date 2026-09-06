# Changelog

All notable changes to AI Consultation Deadlines Canada. Releases are tagged in git;
the format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

[1.0.0]: https://github.com/donjguido/ai-consultation-deadlines-canada/releases/tag/v1.0.0
