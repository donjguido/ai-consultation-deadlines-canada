"""Triage a fetch run against the canonical store.

Usage: python -m pipeline.triage [candidates.json] [items.json]

Prints the sections the curation loop needs and nothing else:
  SOURCE YIELD    candidates per source (zero-yield sources are the failure signal)
  UNSEEN          candidates whose URL is not already in the store (the real work)
  STALE           items whose closing date has passed with no retired_reason recorded
  NEEDS CHECK     open items with verified:false, and items closing within 7 days
  NO <LANGUAGE>   items missing any translated field for a secondary language
                  (the site silently falls back to the primary language)

Candidate ids are fetcher-generated ("ised_consultations-<slug>") and will never
match hand-curated ids ("ised-2026-ai-transparency"), so matching is by URL.
See docs/CURATION.md for the loop this belongs to.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from .config import ROOT, SECONDARY, strings, translated_fields
from .models import CLOSING_SOON_DAYS


def norm(url: str) -> str:
    """Compare URLs ignoring scheme, www, query, fragment and trailing slash."""
    p = urlsplit((url or "").strip().lower())
    host = p.netloc.removeprefix("www.")
    return f"{host}{p.path.rstrip('/')}"


def parse_date(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def main(cand_path: str, items_path: str, today: date | None = None) -> None:
    today = today or date.today()
    items = json.loads(Path(items_path).read_text(encoding="utf-8"))
    cands = json.loads(Path(cand_path).read_text(encoding="utf-8")) if Path(cand_path).exists() else []
    known = {norm(i["url"]) for i in items}

    print(f"# Triage {today.isoformat()}  ({len(cands)} candidates, {len(items)} stored items)\n")

    print("## SOURCE YIELD")
    yield_ = Counter(c.get("source", "?") for c in cands)
    sources = yaml.safe_load((ROOT / "data" / "sources.yaml").read_text(encoding="utf-8")).get("sources") or []
    configured = [s["key"] for s in sources if s.get("enabled", True)]
    for key in configured:
        n = yield_.get(key, 0)
        print(f"  {key:28s} {n:4d}{'   <-- zero yield, check the fetcher' if n == 0 else ''}")
    for key, n in yield_.items():
        if key not in configured:
            print(f"  {key:28s} {n:4d}   (not enabled in sources.yaml)")

    print("\n## UNSEEN (candidate URLs not in the store)")
    unseen = [c for c in cands if norm(c["url"]) not in known]
    for c in unseen:
        print(f"  [{c.get('source', '?')}] {c.get('title', '(untitled)')[:90]}")
        print(f"      {c['url']}")
        print(f"      opened={c.get('opened') or '?'}  closes={c.get('closes') or '?'}")
    if not unseen:
        print("  (none)")

    print("\n## STALE (closing date passed, still not retired)")
    stale = [i for i in items if not i.get("retired") and (d := parse_date(i.get("closes"))) and d < today]
    for i in stale:
        print(f"  {i['id']:44s} closed {i['closes']}  verified={i.get('verified', False)}")
    if not stale:
        print("  (none)")

    print(f"\n## NEEDS CHECK (open items: unverified, or closing within {CLOSING_SOON_DAYS} days)")
    soon = today + timedelta(days=CLOSING_SOON_DAYS)
    flagged = False
    for i in items:
        d = parse_date(i.get("closes"))
        if i.get("retired") or (d and d < today):
            continue
        flags = []
        if not i.get("verified"):
            flags.append("unverified")
        if d and today <= d <= soon:
            flags.append(f"closing in {(d - today).days}d")
        if flags:
            flagged = True
            print(f"  {i['id']:44s} {', '.join(flags)}")
            print(f"      {i['url']}")
    if not flagged:
        print("  (none)")

    for lang in SECONDARY:
        name = strings(lang).get("language_name_en", lang).upper()
        print(f"\n## NO {name} (site falls back to the primary language for these)")
        fields = translated_fields(lang)
        gaps_found = False
        for i in items:
            gaps = [f for f in fields if not (i.get(f) or "").strip()]
            if gaps:
                gaps_found = True
                print(f"  {i['id']:44s} missing {', '.join(f[: -len(lang) - 1] for f in gaps)}")
        if not gaps_found:
            print("  (none)")


if __name__ == "__main__":
    main(
        sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "data" / "candidates.json"),
        sys.argv[2] if len(sys.argv) > 2 else str(ROOT / "data" / "items.json"),
    )
