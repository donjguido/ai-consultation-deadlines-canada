# Curation

The pipeline finds and drafts; a person verifies. The whole value of the site rests on that
second step, so this page spells it out. It applies to the Canadian site and to any fork.

## Cadence

Twice a week (Mondays and Thursdays here; a fork sets its own `cadence` text in
`data/site.yaml`). A quiet run takes ten minutes; a busy one under an hour.

## Engagement snapshot (Mondays)

Once a week, before the loop:

```
python -m pipeline.engagement
```

It appends one row to `data/engagement.csv`: Feedly subscribers per feed, GitHub views,
unique visitors and clones for the last 14 days (needs `gh auth login`), and, when
`analytics.goatcounter` is set in `site.yaml` and `GOATCOUNTER_TOKEN` is exported, the
week's page views and click events. The sources keep no history, so the CSV is the record.
A blank cell means the source was unreachable, not zero; commit the row with the curation.

## The loop

1. **Pull first.** The workflow commits back to `main` as `monitor-bot`, so `git pull` before
   touching `data/items.json`.

2. **Fetch and triage.**

   ```
   python -m pipeline.fetch data/candidates.json
   python -m pipeline.triage
   ```

   The triage report has five sections and nothing else:

   | Section | Meaning | What to do |
   |---|---|---|
   | SOURCE YIELD | candidates per enabled source | Zero from a source that normally yields means the page or feed moved. Note it; fix the selector only if it is quick. |
   | UNSEEN | candidate URLs not already in the store | The real work. Open each page and decide (relevance rule below). |
   | STALE | closing date passed, `retired_reason` not recorded | Set `retired: true` and a reason. |
   | NEEDS CHECK | open items that are unverified, or closing within 7 days | Open the page, confirm the date and the route in, set `verified: true`. |
   | NO \<LANGUAGE\> | items missing a translated field | Fill it, or the site silently shows a half-translated row. One section per secondary language. |

   Matching is by normalised URL, not id: fetcher ids never match curated ids.

3. **Decide each unseen candidate.** Include it when a member of the public, a researcher or a
   civil-society group could plausibly influence how AI systems are governed, regulated,
   procured, funded or made safe by taking part. Include things not labelled "AI" that bear on it
   (a privacy bill, a deepfake election-integrity study, a medical-device software rule).
   Exclude announcements with no way in, and items where AI is incidental.

   For a handful of items, write the record by hand; for ten or more, run the classifier
   (`python -m pipeline.classify data/candidates.json data/items.json` with `ANTHROPIC_API_KEY`
   set) and then verify what it wrote. Either way the record is not finished until a person has
   read the dates on the official page.

4. **Verify.** `verified: true` means exactly one thing: a person opened the official page in
   this run and read the closing date and the participation route there. Never set it from a
   search snippet, a feed summary or the classifier's extraction. If the page contradicts the
   store, the page wins. If the page is gone, retire the item.

5. **Retire.** A past-dated item already renders as retired; the reason is what is missing.
   `retired_reason` is one of:

   | Reason | Use when |
   |---|---|
   | `closed` | The stated window ended normally. |
   | `withdrawn` | The body pulled the consultation, or the page is gone. |
   | `superseded` | Replaced by a later call, bill stage or item in the store (link the new one in `how_to_participate`). |

   Retired items stay in the store so people can see what they missed.

6. **Rebuild, test, commit.**

   ```
   python -m pipeline.build data/items.json site
   python -m pytest
   git add data/items.json site
   git commit -m "Scan 2026-09-08: 2 new (ISED, INDU), verified 3, retired 1"
   ```

   The build prints badge counts; if you added two open items and the open count did not
   move, a date is wrong. A red test blocks the deploy, so run it before pushing.

7. **Deploy.** Push to `main` or run the workflow by hand. There is no automatic schedule.

## Record rules

| Field | Rule |
|---|---|
| `id` | Stable slug, `<body>-<year>-<topic>`. Never change one once published; it is the feed guid and the calendar UID. |
| `url` | The page a participant acts on, not a news release about it. Must be https. |
| `opened` / `closes` | ISO dates read on the page. `closes: null` for rolling calls. |
| `first_seen` | The date the monitor first recorded it. |
| `summary` | One or two sentences, plain language, about what is being decided. Original prose, not copied blocks. |
| `why_it_matters` | One sentence on why this channel bears on AI safety. Neutral: never a position on what people should say. |
| `how_to_participate` | The concrete next step: the form, the portal, the clerk's email, the deadline. The site bolds this line. |
| `topics` | 2 to 4 tags from `TOPICS` in `pipeline/classify.py`. |
| `relevance` | Confidence 0 to 1; below 0.5 leave it out. |
| `source` | The source key from `sources.yaml`. |
| translated fields | `title_<lang>`, `body_<lang>`, `summary_<lang>`, `why_it_matters_<lang>`, `how_to_participate_<lang>` for each secondary language. Prefer the wording of the source's own page in that language. Keep URLs, emails, amounts and dates identical across languages; a mismatch there is the one translation bug that can make someone miss a deadline. |

## Known traps

- Petition pages can show a status ("Closed for signature") that contradicts the stated window.
  Show both, keep `verified: false`, and note it.
- Gazette-style notices state a comment window (30 or 75 days) in the text rather than a date;
  compute it from the publication date and check the arithmetic.
- A candidate that is the same call as an existing item under a new URL is an update to the
  existing record, not a second item.
