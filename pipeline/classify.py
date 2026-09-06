"""Classify candidate items for AI-safety relevance using Claude.

Usage: python -m pipeline.classify data/candidates.json data/items.json

Each candidate is a raw record from a fetcher: {source, url, title, text,
opened?, closes?}. The classifier decides whether it belongs on the monitor,
writes the plain-language fields, and merges the result into items.json.
Items already present are not re-classified (saves cost); only their
closing date and retired flag are refreshed.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import anthropic

from .models import Classification, Item

TOPICS = [
    "frontier-models", "privacy", "copyright", "procurement", "deepfakes",
    "biometrics", "defence", "health", "children", "elections", "competition",
    "standards", "public-service", "research-funding", "international",
    "safety-institute", "employment", "finance", "critical-infrastructure",
]

SYSTEM = f"""You screen Canadian federal government intake channels (public consultations,
parliamentary calls for briefs, Canada Gazette notices, funding calls, standards reviews,
petitions) for a public monitor that helps Canadians get involved in shaping AI safety
and AI governance.

Mark an item relevant if a member of the public, researcher, or civil-society group could
plausibly influence how AI systems are governed, regulated, procured, funded, or made safe in
Canada by participating. Include items that are not labelled "AI" but clearly bear on it
(e.g. a privacy bill consultation, a deepfake election-integrity study, a medical-device
software rule). Exclude items where AI is only incidental.

Write for a general audience. Be concrete about how to participate: name the form, email
address, or portal if the text gives one. Use only these topic tags: {", ".join(TOPICS)}.
If a closing date is stated, return it as ISO 8601; otherwise leave it null.

The monitor is bilingual, so every item ships in both official languages. Write the English
fields first, then write summary_fr, why_it_matters_fr and how_to_participate_fr as Canadian
French of the same quality — idiomatic prose a francophone civil servant would recognise, not
a word-for-word calque. Keep proper nouns, programme names, portal names, email addresses and
dates accurate; use the official French name of a department, committee or programme when one
exists (e.g. "Innovation, Sciences et Développement économique Canada", "Comité permanent de
l'industrie et de la technologie de la Chambre des communes"). Write dates in French style
(23 septembre 2026) and use French typography (« » for quotes, a space before : ; ! ?).

For title_fr and body_fr: use the official French title and body name if the page text supplies
one; otherwise give a faithful French rendering. Leave title_fr null only for a title that has
no sensible French form."""

MODEL = "claude-opus-5"


def classify_one(client: anthropic.Anthropic, cand: dict) -> Classification:
    text = cand.get("text", "")[:12000]
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=1500,
        output_config={"effort": "low"},
        system=SYSTEM,
        messages=[{
            "role": "user",
            "content": (
                f"Source: {cand['source']}\nURL: {cand['url']}\nTitle: {cand['title']}\n"
                f"Opened: {cand.get('opened') or 'unknown'}\nCloses: {cand.get('closes') or 'unknown'}\n\n"
                f"Page text:\n{text}"
            ),
        }],
        output_format=Classification,
    )
    return resp.parsed_output


def main(candidates_path: str, items_path: str, threshold: float = 0.5) -> None:
    client = anthropic.Anthropic()
    candidates = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    items_file = Path(items_path)
    existing = {i["id"]: i for i in json.loads(items_file.read_text(encoding="utf-8"))} if items_file.exists() else {}
    today = date.today()

    added = 0
    for cand in candidates:
        cid = cand["id"]
        if cid in existing:
            # refresh mutable fields only
            if cand.get("closes"):
                existing[cid]["closes"] = cand["closes"]
            continue
        c = classify_one(client, cand)
        if not c.relevant or c.relevance < threshold:
            continue
        item = Item(
            id=cid, title=cand["title"], title_fr=cand.get("title_fr") or c.title_fr,
            body=cand.get("body", ""), body_fr=c.body_fr, type=c.type, url=cand["url"],
            opened=cand.get("opened"), closes=cand.get("closes") or c.closes, first_seen=today,
            summary=c.summary, summary_fr=c.summary_fr,
            why_it_matters=c.why_it_matters, why_it_matters_fr=c.why_it_matters_fr,
            how_to_participate=c.how_to_participate, how_to_participate_fr=c.how_to_participate_fr,
            topics=c.topics, relevance=c.relevance, source=cand["source"],
        )
        existing[cid] = json.loads(item.model_dump_json())
        added += 1

    items_file.write_text(json.dumps(list(existing.values()), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"classified {len(candidates)} candidates, added {added}, total {len(existing)}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
