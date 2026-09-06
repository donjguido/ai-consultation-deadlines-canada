"""Build the static site, RSS feed, JSON API, and weekly digest from data/items.json.

Usage: python -m pipeline.build data/items.json site
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path

from .models import Item

SITE_URL = "https://donjguido.github.io/canadian-ai-governance-monitor"  # GitHub Pages; swap for a custom domain later
TEMPLATE = Path(__file__).parent / "template.html"


def load_items(path: str) -> list[Item]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Item(**r) for r in raw]


def public_record(item: Item, today: date) -> dict:
    d = json.loads(item.model_dump_json())
    d["status"] = item.status(today)
    d["badges"] = item.badges(today)
    d["days_left"] = (item.closes - today).days if item.closes and item.status(today) == "open" else None
    return d


def build_site(items: list[Item], out: Path, today: date) -> None:
    records = [public_record(i, today) for i in items]
    # open first (soonest close first, undated last), then retired newest-closed first
    def key(r):
        if r["status"] == "open":
            return (0, r["closes"] or "9999-12-31")
        return (1, "" if not r["closes"] else "".join(chr(255 - ord(c)) for c in r["closes"]))
    records.sort(key=key)
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("/*__DATA__*/[]", json.dumps(records, ensure_ascii=False))
    html = html.replace("__BUILT__", today.isoformat())
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "items.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


def build_feed(items: list[Item], out: Path, today: date) -> None:
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    entries = []
    for i in sorted(items, key=lambda x: x.first_seen, reverse=True):
        badges = " · ".join(b.replace("_", " ").upper() for b in i.badges(today))
        closes = f"Closes {i.closes.isoformat()}" if i.closes else "No stated deadline"
        desc = escape(f"[{badges}] {i.body}. {closes}. {i.summary} Why it matters: {i.why_it_matters} How to participate: {i.how_to_participate}")
        pub = datetime.combine(i.first_seen, datetime.min.time(), timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        entries.append(
            f"<item><title>{escape(i.title)}</title><link>{escape(i.url)}</link>"
            f"<guid isPermaLink=\"false\">{escape(i.id)}</guid><pubDate>{pub}</pubDate>"
            f"<description>{desc}</description>"
            + "".join(f"<category>{escape(t)}</category>" for t in i.topics)
            + "</item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
        "<title>Canadian AI Governance Monitor</title>"
        f"<link>{SITE_URL}</link><description>Federal consultations, calls for briefs, and other ways Canadians can shape AI safety.</description>"
        f"<language>en-ca</language><lastBuildDate>{now}</lastBuildDate>" + "".join(entries) + "</channel></rss>"
    )
    (out / "feed.xml").write_text(xml, encoding="utf-8")


def build_digest(items: list[Item], out: Path, today: date) -> None:
    """Plain-text weekly digest, ready to paste into the newsletter tool or send via API."""
    new = [i for i in items if i.is_new(today)]
    closing = [i for i in items if i.is_closing_soon(today)]
    open_ = [i for i in items if i.status(today) == "open" and i not in new and i not in closing]
    retired = [i for i in items if i.status(today) == "retired" and i.closes and (today - i.closes).days <= 14]

    def block(title, rows):
        if not rows:
            return f"## {title}\n\nNothing this week.\n\n"
        lines = [f"## {title}\n"]
        for i in rows:
            when = f"closes {i.closes.isoformat()}" if i.closes else "no stated deadline"
            lines.append(f"- **{i.title}** ({i.body}, {when})\n  {i.summary}\n  How to participate: {i.how_to_participate}\n  {i.url}")
        return "\n".join(lines) + "\n\n"

    text = (
        f"# Canadian AI Governance Monitor, week of {today.isoformat()}\n\n"
        + block("Closing within 7 days", closing)
        + block("New this fortnight", new)
        + block("Still open", open_)
        + block("Recently closed", retired)
        + f"Full list: {SITE_URL}  ·  RSS: {SITE_URL}/feed.xml\n"
    )
    (out / "digest.md").write_text(text, encoding="utf-8")


def main(items_path: str, out_dir: str) -> None:
    today = date.today()
    items = load_items(items_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    build_site(items, out, today)
    build_feed(items, out, today)
    build_digest(items, out, today)
    counts = {b: sum(1 for i in items if b in i.badges(today)) for b in ["new", "open", "closing_soon", "retired"]}
    print(f"built {len(items)} items -> {out}  {counts}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
