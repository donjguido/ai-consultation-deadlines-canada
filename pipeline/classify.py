"""Classify candidate items for AI-safety relevance using Claude.

Usage: python -m pipeline.classify data/candidates.json data/items.json

Each candidate is a raw record from a fetcher: {source, url, title, text,
opened?, closes?}. The classifier decides whether it belongs on the monitor,
writes the plain-language fields, and merges the result into items.json.
Items already present are not re-classified (saves cost); only their
closing date and retired flag are refreshed.

The prompt is jurisdiction-neutral. The part that names the place, the channels
being screened and the language conventions comes from the `classifier:` and
`languages:` blocks of data/site.yaml, so a fork changes the prompt by editing
that file rather than this one.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import anthropic

from .config import PRIMARY, SECONDARY, SITE, TRANSLATED_FIELDS, field as lang_field, strings
from .models import Classification, Item

TOPICS = [
    "frontier-models", "privacy", "copyright", "procurement", "deepfakes",
    "biometrics", "defence", "health", "children", "elections", "competition",
    "standards", "public-service", "research-funding", "international",
    "safety-institute", "employment", "finance", "critical-infrastructure",
]

MODEL = "claude-opus-5"


def _lang_name(lang: str) -> str:
    return strings(lang).get("language_name_en") or strings(lang).get("language_name") or lang


def build_system_prompt(site: dict = SITE, topics: list[str] = TOPICS) -> str:
    cfg = site.get("classifier", {})
    place = cfg.get("place") or site["jurisdiction"]["name"]
    scope = cfg.get("scope") or f"{site['jurisdiction']['level']} government intake channels in {place}"
    primary_name = _lang_name(PRIMARY)

    parts = [
        f"""You screen {scope} for a public monitor that helps people in {place} get involved in
shaping AI safety and AI governance.

Mark an item relevant if a member of the public, researcher, or civil-society group could
plausibly influence how AI systems are governed, regulated, procured, funded, or made safe in
{place} by participating. Include items that are not labelled "AI" but clearly bear on it
(e.g. a privacy bill consultation, a deepfake election-integrity study, a medical-device
software rule). Exclude items where AI is only incidental.

Write for a general audience, in {primary_name}. Be concrete about how to participate: name the
form, email address, or portal if the text gives one. Use only these topic tags: {", ".join(topics)}.
If a closing date is stated, return it as ISO 8601; otherwise leave it null."""
    ]

    if SECONDARY:
        names = ", ".join(_lang_name(x) for x in SECONDARY)
        parts.append(
            f"The monitor is multilingual, so every item ships in {primary_name} and {names}. "
            f"Write the {primary_name} fields first, then the translated fields for each other language."
        )
        official = cfg.get("official_names")
        for lang in SECONDARY:
            name = _lang_name(lang)
            style = (cfg.get("style") or {}).get(lang) or (
                f"Write idiomatic {name} of the same quality as the {primary_name}, not a word-for-word calque."
            )
            parts.append(
                f"For the {name} fields ({', '.join(lang_field(b, lang) for b in ('summary', 'why_it_matters', 'how_to_participate'))}): "
                f"{style.strip()} Keep proper nouns, programme names, portal names, email addresses and dates accurate"
                + (f"; {official.strip()}" if official else "") + "."
            )
            parts.append(
                f"For {lang_field('title', lang)} and {lang_field('body', lang)}: use the official {name} title and body "
                f"name if the page text supplies one; otherwise give a faithful {name} rendering. Leave "
                f"{lang_field('title', lang)} null only for a title that has no sensible {name} form."
            )
    return "\n\n".join(parts)


SYSTEM = build_system_prompt()


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
    assert resp.parsed_output is not None, "model returned no structured output"
    return resp.parsed_output


def to_item(cand: dict, c: Classification, today: date) -> Item:
    """Merge a fetcher candidate and its classification into a store record."""
    data: dict[str, Any] = dict(
        id=cand["id"], title=cand["title"], body=cand.get("body", ""), type=c.type, url=cand["url"],
        opened=cand.get("opened"), closes=cand.get("closes") or c.closes, first_seen=today,
        summary=c.summary, why_it_matters=c.why_it_matters, how_to_participate=c.how_to_participate,
        topics=c.topics, relevance=c.relevance, source=cand["source"],
    )
    for lang in SECONDARY:
        for base in TRANSLATED_FIELDS:
            f = lang_field(base, lang)
            # A fetcher may already carry an official translation (a bilingual CSV); prefer it.
            data[f] = cand.get(f) or getattr(c, f, None)
    return Item(**data)


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
        existing[cid] = json.loads(to_item(cand, c, today).model_dump_json())
        added += 1

    items_file.write_text(json.dumps(list(existing.values()), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"classified {len(candidates)} candidates, added {added}, total {len(existing)}")


def cli(argv: list[str] | None = None) -> None:
    import argparse
    p = argparse.ArgumentParser(prog="python -m pipeline.classify",
                                description="Classify fetched candidates into the store with the configured model.")
    p.add_argument("candidates", nargs="?", help="data/candidates.json from pipeline.fetch")
    p.add_argument("items", nargs="?", help="data/items.json, the store to update")
    p.add_argument("--print-prompt", action="store_true",
                   help="print the system prompt built from data/site.yaml and exit; needs no API key")
    p.add_argument("--threshold", type=float, default=0.5, help="minimum relevance to keep (default 0.5)")
    args = p.parse_args(argv)
    if args.print_prompt:
        print(SYSTEM)
        return
    if not (args.candidates and args.items):
        p.error("candidates and items paths are required (or pass --print-prompt)")
    main(args.candidates, args.items, args.threshold)


if __name__ == "__main__":
    cli()
