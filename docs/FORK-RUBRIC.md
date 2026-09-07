# Fork rubric — what "easy to fork" means, and how to check it

`docs/FORKING.md` promises that another geography can run this site by editing three data
files and no Python. This rubric turns that promise into pass/fail checks so a fork attempt
can be scored, and so a failed check points at the file that needs fixing.

Score it on a **fresh clone**, as someone who is not the author, for a **real target
geography** with real sources. Record the geography, the date, and the commit tested.

## Headline thresholds

A fork counts as *easy* only if all four hold:

| Threshold | Target |
|---|---|
| Files edited by hand | `data/site.yaml`, `data/sources.yaml`, `data/forks.yaml`, plus at most one new `pipeline/strings/<lang>.yaml`. Nothing else. |
| Python, template or test edits needed | 0 |
| Wall-clock from clone to a green `pytest` and a rendered site with real fetched candidates | under 2 hours, excluding time spent hunting for the geography's source URLs |
| Questions that could only be answered by asking the original author | 0 |

Keep a **friction log** alongside: every moment you had to stop, guess, read Python, or
work around something. Each entry is a candidate fix. Under five entries, none blocking, is
the bar.

## Criteria

Each is pass/fail. A criterion with a `grep` or command is checked with that command, not
by eye.

### A. Scaffold

- A1. `python -m pipeline.fork --dry-run ...` prints a plan that matches what the real run
  then does.
- A2. Immediately after the real scaffold, with no hand edits, `python -m pytest` is green
  and `python -m pipeline.build data/items.json site` renders an empty-store site.
- A3. The scaffold's printed checklist is complete: following it and nothing else gets to a
  working site. Any step you needed that it did not list is a friction-log entry.
- A4. The scaffolded `site.yaml` is valid and has no leftover original identity (name,
  URL, repo, author, jurisdiction, keywords).

### B. Configuration is the only surface

- B1. No place, author or language pair is named in code:
  `grep -rniE "canada|canadian|guidote|donjguido" --include=*.py --include=*.html --exclude=test_fork.py --exclude=test_template.py pipeline mcp_server tests`
  returns nothing. `test_fork.py` and `test_template.py` name the parent site on purpose,
  as the guards that enforce this criterion.
- B2. Every geography-specific string the fork changed lived in `data/` or
  `pipeline/strings/`. If you found one elsewhere, fail.
- B3. Every key in `site.yaml` is documented in `FORKING.md` or in a comment in the file
  itself. An undocumented key you had to reverse-engineer is a fail.

### C. Sources

- C1. At least one Tier-1 fetcher (`csv` or `json_api`) and at least one of `rss`,
  `sitemap` or `html_index` work for the new geography using only YAML.
- C2. `python -m pipeline.fetch` reports per-source counts, and a misconfigured source
  (wrong column name, wrong URL) produces a diagnosable message, not a silent zero or a
  stack trace.
- C3. The keyword pre-filter in `site.yaml` can be tuned per language and a term added
  there visibly changes the candidate count.
- C4. A source that cannot be automated can be recorded with `enabled: false` and a note,
  and still appears in the sources documentation output if any.

### D. Language

- D1. Monolingual fork (`--languages en`): builds with no toggle, no `-fr` artefacts, no
  empty translated fields, tests green.
- D2. Fork keeping the shipped pair (`en,fr`): translated prose blocks in `site.yaml` are
  the only translation work; `test_config.py` catches an untranslated copy.
- D3. New language (for example `de` or `es`): copying `en.yaml`, translating it, and
  adding the code to `site.yaml` is enough for items, feeds, calendar, digest and the site
  to gain that language. No code change.
- D4. Locale tags and date formatting follow `site.yaml` → `locales`.

### E. Classifier

- E1. The prompt built from `site.yaml` → `classifier` names the new place and scope; a
  dump of the prompt contains nothing about the original geography.
- E2. Classifying real candidates at the budgeted model and effort produces plausible
  items for the new place, with `verified: false`, in every configured language.
- E3. `test_classify_config.py` still passes: the fork did not need to change model,
  effort or `max_tokens`.

### F. Rendered output

- F1. After a build on real items, `grep -rniE "canada|gazette|donjguido" site/` finds
  only occurrences that come from `forks.json` (the sibling listing) or from item content
  that legitimately mentions the original.
- F2. Every artefact is present and carries the new identity: `index.html`, per-language
  feeds, `.ics` calendars, digests, `items.json`, `llms.txt`, `forks.json`, `robots.txt`
  or sitemap if generated.
- F3. Feeds and calendars validate (the build tests parse them; also open the `.ics` in a
  calendar client once).
- F4. `python -m mcp_server.smoke_test` passes against the fork's built `items.json`.
- F5. Mobile and desktop layouts render correctly with the new, possibly longer, site name.

### G. Tests as guardrails

- G1. The suite is green on the finished fork with zero edits to `tests/`.
- G2. Deliberately break one config value (a missing strings key, an untranslated block, a
  bad `sources.yaml` kind) and confirm the failing test names the file and the problem.
- G3. The deploy workflow refuses to publish on a red suite, and runs on `workflow_dispatch`
  in the fork with no YAML edits beyond secrets.

### H. Family and docs

- H1. Adding the fork to the original's `forks.yaml` makes it appear in the original's
  footer and `llms.txt`, and vice versa, after a rebuild.
- H2. `FORKING.md` was sufficient end to end. Every place it was wrong, stale or silent is
  a friction-log entry and a docs fix.
- H3. `README.md` points a newcomer to `FORKING.md` within the first screen.
- H4. Licence and attribution for government content are configurable and correct for the
  new jurisdiction (`text.<lang>.government_licence`, `licence.data`).

### I. Cost

- I1. Nothing in the fork raises the per-run cost above the original: same model, effort,
  `max_tokens`, and the pre-filter keeps classifier calls proportional to real candidates.

## Scoring sheet

Copy this block into the friction log for each attempt.

```
Geography:            
Date / commit:        
Time to green build:  
Files edited:         
Python/test edits:    
Author questions:     

A1 A2 A3 A4 | B1 B2 B3 | C1 C2 C3 C4 | D1 D2 D3 D4 | E1 E2 E3
F1 F2 F3 F4 F5 | G1 G2 G3 | H1 H2 H3 H4 | I1

Friction log:
1.
```

## What a fail should produce

A failed criterion is not the end of the test. Log it, keep going to the end so the whole
picture is visible, then fix in this order: anything that required a Python or test edit
(breaks the core promise), then docs gaps, then scaffold polish.
