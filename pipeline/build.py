"""Build the static site, RSS feed, iCalendar feed, JSON API, and weekly digest from data/items.json.

Usage: python -m pipeline.build data/items.json site
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path

from .models import Item

SITE_URL = "https://donjguido.github.io/canadian-ai-governance-monitor"  # GitHub Pages; swap for a custom domain later
TEMPLATE = Path(__file__).parent / "template.html"
ICS_NAME = "Canadian AI Governance Monitor: deadlines"


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
    html = html.replace("__SITE__", SITE_URL)
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


# ---- iCalendar -------------------------------------------------------------
# Google Calendar and Outlook have no "add these N events" URL, so a published
# .ics is the only way to hand someone every deadline at once. Publishing it as
# a file rather than generating it in the browser also makes it subscribable:
# the client re-reads it and picks up new items, changed dates and retirements.

ESC = "\\"


def _ics_text(value: str) -> str:
    """Escape a TEXT value per RFC 5545 section 3.3.11."""
    return (
        value.replace(ESC, ESC * 2)
        .replace(";", ESC + ";")
        .replace(",", ESC + ",")
        .replace("\r\n", ESC + "n")
        .replace("\n", ESC + "n")
    )


def _ics_fold(line: str) -> str:
    """Fold to 75 octets per RFC 5545 section 3.1, splitting only between characters."""
    chunks: list[str] = []
    cur, used, limit = "", 0, 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if used + n > limit:
            chunks.append(cur)
            cur, used, limit = "", 0, 74  # continuation lines carry a leading space
        cur += ch
        used += n
    chunks.append(cur)
    return "\r\n ".join(chunks)


def ics_event(item: Item, stamp: str) -> list[str]:
    """One all-day VEVENT on the closing date, with 7-day and 1-day reminders."""
    closes = item.closes
    if closes is None:  # nothing to put in a calendar
        return []
    desc = [item.body, item.summary, f"Why it matters: {item.why_it_matters}"]
    if item.how_to_participate:
        desc.append(f"How to participate: {item.how_to_participate}")
    if not item.verified:
        desc.append("⚠ This date has not been checked by a human yet. Confirm it on the official page.")
    desc += [item.url, f"Tracked by the Canadian AI Governance Monitor: {SITE_URL}"]
    lines = [
        "BEGIN:VEVENT",
        f"UID:{item.id}@canadian-ai-governance-monitor",
        f"DTSTAMP:{stamp}",
        f"LAST-MODIFIED:{stamp}",
        f"DTSTART;VALUE=DATE:{closes:%Y%m%d}",
        f"DTEND;VALUE=DATE:{closes + timedelta(days=1):%Y%m%d}",
        f"SUMMARY:{_ics_text('Deadline: ' + item.title)}",
        f"DESCRIPTION:{_ics_text(chr(10).join(desc))}",
        f"URL:{_ics_text(item.url)}",
        "TRANSP:TRANSPARENT",
    ]
    if item.topics:
        # CATEGORIES is a comma-separated list, so escape each value but not the separator.
        lines.append("CATEGORIES:" + ",".join(_ics_text(t) for t in item.topics))
    for trigger, label in (("-P7D", "closes in 7 days"), ("-P1D", "closes tomorrow")):
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_ics_text(item.title + ' ' + label)}",
            f"TRIGGER;VALUE=DURATION:{trigger}",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def build_calendar(items: list[Item], out: Path, today: date) -> None:
    """Publish deadlines.ics: every open item that has a stated closing date."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    upcoming = sorted(
        (i for i in items if i.status(today) == "open" and i.closes),
        key=lambda i: (i.closes, i.id),
    )
    caldesc = (
        "Closing dates for federal consultations, calls for briefs, Gazette comment periods, "
        "funding calls, standards reviews, and petitions where Canadians can shape how AI is governed."
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Canadian AI Governance Monitor//v0.1//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"NAME:{_ics_text(ICS_NAME)}",
        f"X-WR-CALNAME:{_ics_text(ICS_NAME)}",
        f"DESCRIPTION:{_ics_text(caldesc)}",
        f"X-WR-CALDESC:{_ics_text(caldesc)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    for i in upcoming:
        lines += ics_event(i, stamp)
    lines.append("END:VCALENDAR")
    text = "".join(_ics_fold(line) + "\r\n" for line in lines)
    (out / "deadlines.ics").write_bytes(text.encode("utf-8"))


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
        + f"Full list: {SITE_URL}  ·  RSS: {SITE_URL}/feed.xml  ·  Calendar: {SITE_URL}/deadlines.ics\n"
    )
    (out / "digest.md").write_text(text, encoding="utf-8")


def main(items_path: str, out_dir: str) -> None:
    today = date.today()
    items = load_items(items_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    build_site(items, out, today)
    build_feed(items, out, today)
    build_calendar(items, out, today)
    build_digest(items, out, today)
    counts = {b: sum(1 for i in items if b in i.badges(today)) for b in ["new", "open", "closing_soon", "retired"]}
    print(f"built {len(items)} items -> {out}  {counts}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
