# Data-source inventory

Verified 6 September 2026 unless noted. Fetcher kinds (`csv`, `json_api`, `rss`, `sitemap`, `html_index`) and their YAML fields are documented in [FORKING.md](FORKING.md). Tiers: 1 = machine-readable, cheap, high yield; 2 = HTML scraping, brittle; 3 = manual weekly watch. The machine-readable config lives in `data/sources.yaml`.

| Source | Tier | Format | Fields | Cadence | Languages | Status in prototype | Notes |
|---|---|---|---|---|---|---|---|
| **Consulting with Canadians** (Privy Council Office) | 1 | Open-data CSV on open.canada.ca; JSON schema published; no CKAN DataStore API | registration number, partner departments, subjects, title EN/FR, description EN/FR, start and end date, status (O open / P planned / C completed), profile page EN/FR, report link, owner org | "Continual"; dataset modified daily | EN + FR | Working: 4 AI-relevant candidates on the dry run | The "last two years" CSV has about 900 rows. Covers only what departments register: no committees, petitions or standards. The portal itself offers no RSS or email alerts, which is the gap this monitor fills |
| **Canada Gazette, Part I** | 1 | Official RSS (`p1-eng.xml`); Part II and Part III feeds also exist | title, link, publish date, summary | Fridays, 2 pm ET | EN + FR feeds | Working: 0 candidates that week (no AI-related notice) | Comment periods (30 or 75 days) are stated in the notice text, so the classifier extracts them from the fetched page. The open.canada.ca Gazette dataset is archived; RSS is the live feed |
| **House of Commons committees** (INDU, ETHI, SRSR, CHPC, others) | 2 | HTML study pages; XML available by appending `/xml` to most ourcommons.ca URLs | study title, meetings, witnesses, briefs, "submit a brief" link | Continuous during sittings | EN + FR | Index scrape wired; needs the XML endpoints for reliable results | Study IDs are stable once known; six current AI studies are in the seed data |
| **Senate committees** (SOCI, RIDR, TRCM) | 2 | HTML committee pages and orders of reference | study scope, order date, report deadline, clerk email | Continuous | EN + FR | Index scrape wired; returned 0 on dry run (selector too generic) | Briefs go by email to the clerk; no fixed deadline for most studies |
| **House of Commons e-petitions** | 2 | JS-driven site; search URL returned 404 to the fetcher | petition number, sponsor, open and close dates, signature count, status | Continuous | EN + FR | Disabled pending a working endpoint | Status text on the page ("Closed for signature") can contradict the stated window; treat as unverified until checked |
| **ISED public consultations** | 2 | HTML list page | title, link | Irregular | EN + FR | Working: 8 candidates on the dry run | Includes the flagship 2026 AI transparency consultation |
| **Office of the Privacy Commissioner consultations** | 2 | HTML list page | title, link | Irregular | EN + FR | Scrape wired; 0 candidates (page structure needs a tighter selector) | |
| **Standards Council of Canada notices of intent** | 2 → 3 | HTML; returned HTTP 403 to automated fetches | standard title, SDO, status | Irregular | EN + FR | Disabled; manual watch | Public reviews often run on the SDO's own site (CSA Group, DGSI) |
| **Digital Governance Standards Institute** | 3 | HTML product pages | draft standard, review window | Irregular | EN + FR | Manual watch | Two AI standards in review in 2026 |
| **CAISI / CIFAR research program** | 3 | cifar.ca blocks bots; SMApply portal for applications | call title, deadline | Annual (autumn Catalyst call, spring school) | EN + FR | Manual watch | |
| **Treasury Board Secretariat** | 3 | Canada.ca pages, GC Forms | AI Register feedback, Directive on Automated Decision-Making reviews | Irregular | EN + FR | Manual watch | 2026-27 AI Register engagement promised |
| **LEGISinfo** (bills) | 3 | HTML and a JSON export per bill | bill number, stage, committee referral | Continuous | EN + FR | Manual watch; candidate for a tier-1 fetcher | Committee referral is the trigger for a briefs window (C-34, C-36 pending) |
| **Others to add** | 3 | | | | | | Elections Canada (AI and deepfakes), Competition Bureau, OSFI (AI in finance), Health Canada (AI medical devices), Global Affairs (international AI agreements) |

## Coverage per unit of effort

1. Consulting with Canadians CSV: highest yield for the least work; already working.
2. Canada Gazette Part I RSS: zero effort, catches every regulatory comment period.
3. House of Commons XML: a day of work to move from index scraping to study-level XML; captures the six largest AI studies.
4. LEGISinfo bill tracking: half a day; turns "bill introduced" into "briefs window opening" alerts.
5. Petitions: needs investigation of the site's data endpoint; medium value.
6. Everything in tier 3 is best handled by the weekly human sweep.

## Known blockers

- The Standards Council site and cifar.ca refuse automated fetches. A browser-like fetch (Playwright) or a manual watch is required.
- GitHub Actions runners use shared IP ranges that some government sites throttle. If a fetcher fails repeatedly from Actions but works locally, route it through a small Cloudflare Worker or a low-cost proxy.
- Petition status text can contradict the stated signature window; the monitor shows both and marks the item unverified.
