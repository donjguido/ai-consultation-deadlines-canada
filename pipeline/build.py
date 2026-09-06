"""Build every published artefact from data/items.json.

Usage: python -m pipeline.build data/items.json site

Writes, into the output directory:

    index.html      the site, with the item list rendered into the HTML (not
                    only into JavaScript) so crawlers and text-mode agents
                    read the same content a browser shows, plus schema.org
                    JSON-LD describing the dataset and every item
    items.json      full records, the JSON API
    feed.xml        RSS 2.0, English      feed-fr.xml   RSS 2.0, French
    feed.json       JSON Feed 1.1
    deadlines.ics   iCalendar feed of closing dates, subscribable by webcal://
    digest.md       weekly digest, English   digest-fr.md  French
    llms.txt        orientation page for AI agents (llmstxt.org convention)
    llms-full.txt   every item as Markdown, the whole corpus in one fetch
    robots.txt      crawling explicitly permitted, including for AI crawlers
    sitemap.xml     the readable URLs
    .nojekyll       stop GitHub Pages running the files through Jekyll
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote

from .models import Item

SITE_URL = "https://donjguido.github.io/canadian-ai-governance-monitor"  # GitHub Pages; swap for a custom domain later
TEMPLATE = Path(__file__).parent / "template.html"

# The site switches language in the browser; the feed and digest are static files,
# so each is written once per official language.
STRINGS = {
    "en": {
        "code": "en-ca", "feed_file": "feed.xml", "digest_file": "digest.md",
        "ics_file": "deadlines.ics", "calendar": "Calendar",
        "cal_name": "AI Consultation Deadlines Canada",
        "cal_desc": "Closing dates for federal consultations, calls for briefs, Gazette comment "
                    "periods, funding calls, standards reviews, and petitions where Canadians "
                    "can shape how AI is governed.",
        "deadline_prefix": "Deadline:",
        "cal_unverified": "⚠ This date has not been checked by a human yet. Confirm it on the official page.",
        "cal_tracked": "Tracked by the AI Consultation Deadlines Canada:",
        "alarm_7": "closes in 7 days", "alarm_1": "closes tomorrow",
        "site_title": "AI Consultation Deadlines Canada",
        "site_desc": "Federal consultations, calls for briefs, and other ways Canadians can shape AI safety.",
        "badge": {"new": "new", "closing_soon": "closing soon", "open": "open", "retired": "retired"},
        "closes": "Closes", "closed": "Closed", "no_deadline": "No stated deadline",
        "why": "Why it matters:", "how": "How to participate:",
        "week_of": "week of", "nothing": "Nothing this week.",
        "sec_closing": "Closing within 7 days", "sec_new": "New this fortnight",
        "sec_open": "Still open", "sec_retired": "Recently closed",
        "full_list": "Full list", "rss": "RSS",
    },
    "fr": {
        "code": "fr-ca", "feed_file": "feed-fr.xml", "digest_file": "digest-fr.md",
        "ics_file": "deadlines-fr.ics", "calendar": "Calendrier",
        "cal_name": "Échéances des consultations sur l'IA Canada",
        "cal_desc": "Dates de clôture des consultations fédérales, appels de mémoires, périodes "
                    "de commentaires de la Gazette, appels de financement, examens de normes et "
                    "pétitions où les Canadiens peuvent influencer la gouvernance de l'IA.",
        "deadline_prefix": "Échéance :",
        "cal_unverified": "⚠ Cette date n'a pas encore été vérifiée par une personne. Confirmez-la sur la page officielle.",
        "cal_tracked": "Suivi par Échéances des consultations sur l'IA Canada :",
        "alarm_7": ": clôture dans 7 jours", "alarm_1": ": clôture demain",
        "site_title": "Échéances des consultations sur l'IA Canada",
        "site_desc": "Consultations fédérales, appels de mémoires et autres façons pour les Canadiens d'influencer la gouvernance de l'IA.",
        "badge": {"new": "nouveau", "closing_soon": "se termine bientôt", "open": "ouvert", "retired": "retiré"},
        "closes": "Clôture", "closed": "Clôturé", "no_deadline": "Aucune échéance annoncée",
        "why": "Pourquoi c'est important :", "how": "Comment participer :",
        "week_of": "semaine du", "nothing": "Rien cette semaine.",
        "sec_closing": "Clôture dans les 7 jours", "sec_new": "Nouveautés des 14 derniers jours",
        "sec_open": "Toujours ouvert", "sec_retired": "Récemment clôturé",
        "full_list": "Liste complète", "rss": "Fil RSS",
    },
}


# Server-side rendering of the item list mirrors renderList() in template.html.
# Both must produce the same English markup: the client skips its first list
# render when the page loads in English, so this is what most readers see.
TYPE_LABEL = {
    "consultation": "Consultation", "call_for_briefs": "Call for briefs",
    "gazette_notice": "Gazette notice", "funding_call": "Funding call",
    "standards_review": "Standards review", "petition": "Petition", "other": "Other",
}
BADGE_LABEL = {"new": "New", "closing_soon": "Closing soon", "open": "Open", "retired": "Retired"}
BADGE_HINT = {
    "new": "opened in last 14 days", "open": "accepting input now",
    "closing_soon": "deadline within 7 days", "retired": "past deadline or withdrawn",
}
COLOR = {k: f"var(--{'soon' if k == 'closing_soon' else k})" for k in BADGE_LABEL}
BG = {k: v[:-1] + "-bg)" for k, v in COLOR.items()}


def esc(value) -> str:
    """HTML-escape exactly the characters the client-side esc() escapes."""
    return (str("" if value is None else value)
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def js_json(obj) -> str:
    """JSON for embedding in HTML: escape < so no string can close the script element."""
    return json.dumps(obj, ensure_ascii=False).replace("<", "\\u003c")


def primary(rec: dict) -> str:
    for b in ("retired", "closing_soon", "new"):
        if b in rec["badges"]:
            return b
    return "open"


def days_left_label(d: int) -> str:
    return "closes today" if d == 0 else "1 day left" if d == 1 else f"{d} days left"


def load_items(path: str) -> list[Item]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Item(**r) for r in raw]


def public_record(item: Item, today: date) -> dict:
    d = json.loads(item.model_dump_json())
    d["status"] = item.status(today)
    d["badges"] = item.badges(today)
    d["days_left"] = (item.closes - today).days if item.closes and item.status(today) == "open" else None
    return d


def sorted_records(items: list[Item], today: date) -> list[dict]:
    records = [public_record(i, today) for i in items]
    # open first (soonest close first, undated last), then retired newest-closed first
    def key(r):
        if r["status"] == "open":
            return (0, r["closes"] or "9999-12-31")
        return (1, "" if not r["closes"] else "".join(chr(255 - ord(c)) for c in r["closes"]))
    records.sort(key=key)
    return records


def render_stats_html(records: list[dict]) -> str:
    counts = {k: 0 for k in BADGE_LABEL}
    for r in records:
        for b in r["badges"]:
            counts[b] += 1
    return "".join(
        f'<button class="stat" style="--c:{COLOR[k]}" data-k="{k}" aria-pressed="false">\n'
        f'      <div class="n">{counts[k]}</div><div class="l">{BADGE_LABEL[k]}</div>'
        f'<div class="h">{BADGE_HINT[k]}</div></button>'
        for k in ("new", "open", "closing_soon", "retired")
    )


def has_upcoming_deadline(item: Item, today: date) -> bool:
    """Whether the item is worth putting in a calendar: still open, and the date
    is still ahead. Mirrors upcoming() in template.html, which re-checks against
    the reader's own date because the baked-in status ages between builds."""
    return item.closes is not None and item.closes >= today and item.status(today) == "open"


def render_cal_menu(item: Item) -> str:
    """Server-side twin of calMenu() in template.html, whitespace included."""
    return (
        f'<div class="cal">\n'
        f'    <button class="cal-btn" data-cal="{esc(item.id)}" aria-expanded="false" aria-haspopup="true">'
        f'\U0001F4C5 Add deadline to calendar</button>\n'
        f'    <div class="cal-menu" role="menu" hidden>\n'
        f'      <a role="menuitem" href="{esc(google_url(item))}" target="_blank" rel="noopener">Google Calendar</a>\n'
        f'      <a role="menuitem" href="{esc(outlook_url(item))}" target="_blank" rel="noopener">Outlook</a>\n'
        f'      <button role="menuitem" data-ics="{esc(item.id)}">Apple Calendar / .ics file</button>\n'
        f'    </div></div>'
    )


def render_items_html(records: list[dict], by_id: dict[str, Item], today: date) -> str:
    out = []
    for r in records:
        p = primary(r)
        if r["closes"]:
            label = "Closed" if p == "retired" else "Closes"
            when = f'<b>{label} <time datetime="{esc(r["closes"])}">{esc(r["closes"])}</time></b>'
            if r["days_left"] is not None:
                when += f'<span>{days_left_label(r["days_left"])}</span>'
        else:
            when = "<b>No stated deadline</b>"
        opened = (f'<span class="d">Opened <time datetime="{esc(r["opened"])}">{esc(r["opened"])}</time></span>'
                  if r["opened"] else "")
        shown = [b for b in r["badges"] if b != "open" or len(r["badges"]) == 1]
        badges = "".join(
            f'<span class="badge" style="--c:{COLOR[b]};--bg:{BG[b]}">{BADGE_LABEL[b]}</span>' for b in shown
        )
        warn = "" if r["verified"] else ' <span class="unverified" title="Not yet checked by a human">\u26a0</span>'
        how = (f'<p class="how"><strong>How to participate:</strong> {esc(r["how_to_participate"])}</p>'
               if r["how_to_participate"] else "")
        topics = "".join(f'<span class="topic">{esc(t)}</span>' for t in r["topics"])
        cal = render_cal_menu(by_id[r["id"]]) if has_upcoming_deadline(by_id[r["id"]], today) else ""
        out.append(
            f'<article class="item {p}" id="item-{esc(r["id"])}" style="--c:{COLOR[p]}">\n'
            f'      <div class="stripe" aria-hidden="true"></div>\n'
            f'      <div class="when">{when}{opened}</div>\n'
            f'      <div class="main">\n'
            f'        <h3><a href="{esc(r["url"])}" rel="noopener external">{esc(r["title"])}</a></h3>\n'
            f'        <div class="body">{esc(r["body"])}<span class="type">{TYPE_LABEL.get(r["type"], r["type"])}</span>'
            f'<span class="badges">{badges}</span>{warn}</div>\n'
            f'        <p>{esc(r["summary"])}</p>\n'
            f'        <p class="why"><em>Why it matters:</em> {esc(r["why_it_matters"])}</p>\n'
            f'        {how}\n'
            f'        <div class="topics">{topics}</div>\n'
            f'        {cal}\n'
            f'      </div></article>'
        )
    return "".join(out)


def render_jsonld(records: list[dict], today: date) -> str:
    """schema.org description of the monitor: the dataset, and every item in it.

    Items are CreativeWork rather than Event on purpose. A consultation has an
    open window but is not something you attend, and tagging it as an Event
    invites search engines to render it as one.
    """
    person = {"@type": "Person", "@id": f"{SITE_URL}/#curator",
              "name": "Julian Guidote", "url": "https://github.com/donjguido"}
    site = {
        "@type": "WebSite", "@id": f"{SITE_URL}/#website", "url": f"{SITE_URL}/",
        "name": STRINGS["en"]["site_title"], "alternateName": STRINGS["fr"]["site_title"],
        "description": STRINGS["en"]["site_desc"], "inLanguage": ["en-CA", "fr-CA"],
        "publisher": {"@id": person["@id"]},
        "license": "https://creativecommons.org/licenses/by/4.0/",
    }
    dates = sorted(r["closes"] for r in records if r["closes"])
    dataset = {
        "@type": "Dataset", "@id": f"{SITE_URL}/#dataset", "url": f"{SITE_URL}/",
        "name": "Canadian federal AI-governance participation channels",
        "description": (
            "Every open federal channel through which people in Canada can shape AI governance: "
            "public consultations, parliamentary calls for briefs, Canada Gazette comment periods, "
            "funding calls, standards reviews and e-petitions. Each record carries a plain-language "
            "summary, why it matters for AI safety, a concrete way to take part, and a status "
            "derived from the stated closing date."
        ),
        "creator": {"@id": person["@id"]}, "isAccessibleForFree": True,
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "dateModified": today.isoformat(),
        "inLanguage": ["en-CA", "fr-CA"],
        "spatialCoverage": {"@type": "Country", "name": "Canada"},
        "isPartOf": {"@id": site["@id"]},
        "keywords": ["AI governance", "AI safety", "Canada", "public consultation",
                     "regulation", "civic participation", "Canada Gazette", "e-petition"],
        "distribution": [
            {"@type": "DataDownload", "name": "Full records (JSON)",
             "encodingFormat": "application/json", "contentUrl": f"{SITE_URL}/items.json"},
            {"@type": "DataDownload", "name": "JSON Feed",
             "encodingFormat": "application/feed+json", "contentUrl": f"{SITE_URL}/feed.json"},
            {"@type": "DataDownload", "name": "RSS (English)",
             "encodingFormat": "application/rss+xml", "contentUrl": f"{SITE_URL}/feed.xml"},
            {"@type": "DataDownload", "name": "RSS (French)",
             "encodingFormat": "application/rss+xml", "contentUrl": f"{SITE_URL}/feed-fr.xml"},
            {"@type": "DataDownload", "name": "Every item as Markdown",
             "encodingFormat": "text/markdown", "contentUrl": f"{SITE_URL}/llms-full.txt"},
        ],
    }
    if dates:
        dataset["temporalCoverage"] = f"{dates[0]}/{dates[-1]}"

    elements = []
    for n, r in enumerate(records, 1):
        work = {
            "@type": "CreativeWork", "@id": f"{SITE_URL}/#item-{r['id']}",
            "name": r["title"], "url": r["url"], "description": r["summary"],
            "abstract": r["why_it_matters"], "inLanguage": "en-CA",
            "genre": TYPE_LABEL.get(r["type"], r["type"]),
            "creativeWorkStatus": "closing soon" if "closing_soon" in r["badges"] else r["status"],
            "keywords": r["topics"], "isPartOf": {"@id": dataset["@id"]},
            "publisher": {"@type": "GovernmentOrganization", "name": r["body"]},
            "spatialCoverage": {"@type": "Country", "name": "Canada"},
        }
        if r["title_fr"]:
            work["alternateName"] = r["title_fr"]
        if r["opened"]:
            work["datePublished"] = r["opened"]
        if r["closes"]:
            work["expires"] = r["closes"]
            work["temporalCoverage"] = f"{r['opened'] or r['first_seen']}/{r['closes']}"
        if r["how_to_participate"]:
            work["potentialAction"] = {
                "@type": "Action", "name": "Participate",
                "description": r["how_to_participate"],
                "target": {"@type": "EntryPoint", "urlTemplate": r["url"]},
            }
        elements.append({"@type": "ListItem", "position": n, "item": work})

    graph = [site, person, dataset, {
        "@type": "ItemList", "@id": f"{SITE_URL}/#items",
        "name": "Open and recently closed federal AI-governance channels",
        "numberOfItems": len(records),
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "itemListElement": elements,
    }]
    payload = js_json({"@context": "https://schema.org", "@graph": graph})
    return f'<script type="application/ld+json">{payload}</script>'


def build_site(items: list[Item], out: Path, today: date) -> list[dict]:
    records = sorted_records(items, today)
    open_n = sum(1 for r in records if r["status"] == "open")
    soon_n = sum(1 for r in records if "closing_soon" in r["badges"])
    desc = (
        f"Tracking {len(records)} federal consultations, calls for briefs, Canada Gazette comment "
        f"periods, funding calls, standards reviews and e-petitions where people in Canada can shape "
        f"AI governance. {open_n} open now, {soon_n} closing within 7 days. Each one has a "
        f"plain-language summary and a concrete way to take part. Bilingual, updated Mondays and Thursdays."
    )
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__DESC__", esc(desc))
    html = html.replace("__SITE_URL__", SITE_URL)
    html = html.replace("__COUNT__", f"Showing {len(records)} of {len(records)} items")
    html = html.replace("__BUILT__", today.isoformat())
    # Generated content goes in last so nothing inside it is scanned for placeholders.
    html = html.replace("<!--__STATS__-->", render_stats_html(records))
    html = html.replace("<!--__ITEMS__-->", render_items_html(records, {i.id: i for i in items}, today))
    html = html.replace("<!--__JSONLD__-->", render_jsonld(records, today))
    html = html.replace("/*__DATA__*/[]", js_json(records))
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "items.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    return records


def fr(item: Item, field: str) -> str:
    """French value of a field, falling back to English when the item is not yet translated."""
    return getattr(item, field + "_fr", None) or getattr(item, field)


def build_feed(items: list[Item], out: Path, today: date, lang: str = "en") -> None:
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    t = STRINGS[lang]
    entries = []
    for i in sorted(items, key=lambda x: x.first_seen, reverse=True):
        text = (lambda f: fr(i, f)) if lang == "fr" else (lambda f: getattr(i, f))
        badges = " · ".join(t["badge"][b].upper() for b in i.badges(today))
        if i.closes:
            closes = f"{t['closed'] if i.status(today) == 'retired' else t['closes']} {i.closes.isoformat()}"
        else:
            closes = t["no_deadline"]
        desc = escape(
            f"[{badges}] {text('body')}. {closes}. {text('summary')} "
            f"{t['why']} {text('why_it_matters')} {t['how']} {text('how_to_participate')}"
        )
        pub = datetime.combine(i.first_seen, datetime.min.time(), timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
        entries.append(
            f"<item><title>{escape(text('title'))}</title><link>{escape(i.url)}</link>"
            f"<guid isPermaLink=\"false\">{escape(i.id)}</guid><pubDate>{pub}</pubDate>"
            f"<description>{desc}</description>"
            + "".join(f"<category>{escape(x)}</category>" for x in i.topics)
            + "</item>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/"><channel>'
        f"<title>{escape(t['site_title'])}</title>"
        f"<link>{SITE_URL}/</link><description>{escape(t['site_desc'])}</description>"
        f'<atom:link href="{SITE_URL}/{t["feed_file"]}" rel="self" type="application/rss+xml"/>'
        f'<atom:link href="{SITE_URL}/" rel="alternate" type="text/html"/>'
        f"<language>{t['code']}</language><lastBuildDate>{now}</lastBuildDate>"
        "<generator>canadian-ai-governance-monitor</generator>"
        "<docs>https://www.rssboard.org/rss-specification</docs>"
        "<copyright>CC BY 4.0</copyright><ttl>720</ttl>" + "".join(entries) + "</channel></rss>"
    )
    (out / t["feed_file"]).write_text(xml, encoding="utf-8")


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


def cal_text(item: Item, lang: str = "en") -> tuple[str, str]:
    """Event title and body, shared by the .ics feed and the Google/Outlook links.
    Mirrors calText() in template.html; the two must agree in English, because
    build.py renders the English list and the client only re-renders on interaction."""
    t = STRINGS[lang]
    text = (lambda i, f: fr(i, f)) if lang == "fr" else (lambda i, f: getattr(i, f))
    parts = [text(item, "body"), text(item, "summary"), f"{t['why']} {text(item, 'why_it_matters')}"]
    if item.how_to_participate:
        parts.append(f"{t['how']} {text(item, 'how_to_participate')}")
    if not item.verified:
        parts.append(t["cal_unverified"])
    parts += [item.url, f"{t['cal_tracked']} {SITE_URL}"]
    return f"{t['deadline_prefix']} {text(item, 'title')}", "\n".join(parts)


# JavaScript's encodeURIComponent leaves these alone; Python's quote() would not.
_URI_SAFE = "-_.!~*'()"


def _qs(pairs: list[tuple[str, str]]) -> str:
    """Query string byte-identical to the client's qs() helper."""
    return "&".join(f"{quote(k, safe=_URI_SAFE)}={quote(v, safe=_URI_SAFE)}" for k, v in pairs)


def google_url(item: Item, lang: str = "en") -> str:
    """Google Calendar's event template: one event per URL, so single deadlines only."""
    title, details = cal_text(item, lang)
    closes = item.closes
    assert closes is not None
    return "https://calendar.google.com/calendar/render?" + _qs([
        ("action", "TEMPLATE"), ("text", title), ("details", details),
        ("dates", f"{closes:%Y%m%d}/{closes + timedelta(days=1):%Y%m%d}"),
    ])


def outlook_url(item: Item, lang: str = "en") -> str:
    title, details = cal_text(item, lang)
    closes = item.closes
    assert closes is not None
    return "https://outlook.live.com/calendar/0/deeplink/compose?" + _qs([
        ("path", "/calendar/action/compose"), ("rru", "addevent"),
        ("subject", title), ("body", details),
        ("startdt", closes.isoformat()), ("enddt", (closes + timedelta(days=1)).isoformat()),
        ("allday", "true"),
    ])


def ics_event(item: Item, stamp: str, lang: str = "en") -> list[str]:
    """One all-day VEVENT on the closing date, with 7-day and 1-day reminders."""
    closes = item.closes
    if closes is None:  # nothing to put in a calendar
        return []
    t = STRINGS[lang]
    summary, description = cal_text(item, lang)
    title = fr(item, "title") if lang == "fr" else item.title
    lines = [
        "BEGIN:VEVENT",
        f"UID:{item.id}@canadian-ai-governance-monitor",
        f"DTSTAMP:{stamp}",
        f"LAST-MODIFIED:{stamp}",
        f"DTSTART;VALUE=DATE:{closes:%Y%m%d}",
        f"DTEND;VALUE=DATE:{closes + timedelta(days=1):%Y%m%d}",
        f"SUMMARY:{_ics_text(summary)}",
        f"DESCRIPTION:{_ics_text(description)}",
        f"URL:{_ics_text(item.url)}",
        "TRANSP:TRANSPARENT",
    ]
    if item.topics:
        # CATEGORIES is a comma-separated list, so escape each value but not the separator.
        lines.append("CATEGORIES:" + ",".join(_ics_text(x) for x in item.topics))
    for trigger, label in (("-P7D", t["alarm_7"]), ("-P1D", t["alarm_1"])):
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_ics_text(title + ' ' + label)}",
            f"TRIGGER;VALUE=DURATION:{trigger}",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def build_calendar(items: list[Item], out: Path, today: date, lang: str = "en") -> None:
    """Publish deadlines.ics: every open item whose stated closing date is still ahead."""
    t = STRINGS[lang]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    upcoming = sorted(
        (i for i in items if has_upcoming_deadline(i, today)),
        key=lambda i: (i.closes, i.id),
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//AI Consultation Deadlines Canada//v0.1//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"NAME:{_ics_text(t['cal_name'])}",
        f"X-WR-CALNAME:{_ics_text(t['cal_name'])}",
        f"DESCRIPTION:{_ics_text(t['cal_desc'])}",
        f"X-WR-CALDESC:{_ics_text(t['cal_desc'])}",
        f"X-WR-CALLANG:{t['code']}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    for i in upcoming:
        lines += ics_event(i, stamp, lang)
    lines.append("END:VCALENDAR")
    text = "".join(_ics_fold(line) + "\r\n" for line in lines)
    (out / t["ics_file"]).write_bytes(text.encode("utf-8"))


def build_digest(items: list[Item], out: Path, today: date, lang: str = "en") -> None:
    """Plain-text weekly digest, ready to paste into the newsletter tool or send via API."""
    t = STRINGS[lang]
    text = (lambda i, f: fr(i, f)) if lang == "fr" else (lambda i, f: getattr(i, f))
    new = [i for i in items if i.is_new(today)]
    closing = [i for i in items if i.is_closing_soon(today)]
    open_ = [i for i in items if i.status(today) == "open" and i not in new and i not in closing]
    retired = [i for i in items if i.status(today) == "retired" and i.closes and (today - i.closes).days <= 14]

    def block(title, rows):
        if not rows:
            return f"## {title}\n\n{t['nothing']}\n\n"
        lines = [f"## {title}\n"]
        for i in rows:
            if i.closes:
                when = f"{t['closed'].lower() if i.status(today) == 'retired' else t['closes'].lower()} {i.closes.isoformat()}"
            else:
                when = t["no_deadline"].lower()
            lines.append(
                f"- **{text(i, 'title')}** ({text(i, 'body')}, {when})\n  {text(i, 'summary')}\n"
                f"  {t['how']} {text(i, 'how_to_participate')}\n  {i.url}"
            )
        return "\n".join(lines) + "\n\n"

    body = (
        f"# {t['site_title']}, {t['week_of']} {today.isoformat()}\n\n"
        + block(t["sec_closing"], closing)
        + block(t["sec_new"], new)
        + block(t["sec_open"], open_)
        + block(t["sec_retired"], retired)
        + f"{t['full_list']} : {SITE_URL}  ·  {t['rss']} : {SITE_URL}/{t['feed_file']}"
        + f"  ·  {t['calendar']} : {SITE_URL}/{t['ics_file']}\n"
        if lang == "fr" else
        f"# {t['site_title']}, {t['week_of']} {today.isoformat()}\n\n"
        + block(t["sec_closing"], closing)
        + block(t["sec_new"], new)
        + block(t["sec_open"], open_)
        + block(t["sec_retired"], retired)
        + f"{t['full_list']}: {SITE_URL}  ·  {t['rss']}: {SITE_URL}/{t['feed_file']}"
        + f"  ·  {t['calendar']}: {SITE_URL}/{t['ics_file']}\n"
    )
    (out / t["digest_file"]).write_text(body, encoding="utf-8")


def build_json_feed(records: list[dict], out: Path, today: date) -> None:
    """JSON Feed 1.1 -- the same items as feed.xml, but self-describing for parsers
    that would rather not touch XML."""
    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": STRINGS["en"]["site_title"],
        "home_page_url": f"{SITE_URL}/",
        "feed_url": f"{SITE_URL}/feed.json",
        "description": STRINGS["en"]["site_desc"],
        "language": "en-CA",
        "authors": [{"name": "Julian Guidote", "url": "https://github.com/donjguido"}],
        "items": [],
    }
    for r in sorted(records, key=lambda x: x["first_seen"], reverse=True):
        when = (f"{'Closed' if r['status'] == 'retired' else 'Closes'} {r['closes']}"
                if r["closes"] else "No stated deadline")
        feed["items"].append({
            "id": f"{SITE_URL}/#item-{r['id']}",
            "url": r["url"],
            "external_url": r["url"],
            "title": r["title"],
            "content_text": (f"{r['body']}. {when}. {r['summary']} "
                             f"Why it matters: {r['why_it_matters']} "
                             f"How to participate: {r['how_to_participate']}"),
            "summary": r["summary"],
            "date_published": f"{r['first_seen']}T00:00:00Z",
            "tags": r["topics"],
            # Namespaced extension: the monitor's own fields, so a client can filter
            # on status or deadline without re-parsing the prose.
            "_monitor": {
                "status": r["status"], "badges": r["badges"], "type": r["type"],
                "body": r["body"], "opened": r["opened"], "closes": r["closes"],
                "days_left": r["days_left"], "verified": r["verified"],
                "relevance": r["relevance"],
            },
        })
    (out / "feed.json").write_text(json.dumps(feed, indent=2, ensure_ascii=False), encoding="utf-8")


def _md_line(r: dict) -> str:
    when = (f"{'closed' if r['status'] == 'retired' else 'closes'} {r['closes']}"
            if r["closes"] else "no stated deadline")
    return f"- [{r['title']}]({r['url']}): {r['body']}, {when}. {r['summary']}"


def build_llms(records: list[dict], out: Path, today: date) -> None:
    """llms.txt, per the llmstxt.org convention: a short, linked orientation page an
    agent can read first to find out what is here and where the structured data lives."""
    open_recs = [r for r in records if r["status"] == "open"]
    soon = [r for r in records if "closing_soon" in r["badges"]]
    fresh = [r for r in records if "new" in r["badges"]]
    retired = [r for r in records if r["status"] == "retired"]
    text = f"""# AI Consultation Deadlines Canada

> Every federal channel through which people in Canada can shape how AI is governed --
> public consultations, parliamentary calls for briefs, Canada Gazette comment periods,
> funding calls, standards reviews and e-petitions -- each with a plain-language summary,
> why it matters for AI safety, and a concrete way to take part.

Built {today.isoformat()}. {len(records)} items tracked: {len(open_recs)} open, {len(soon)} closing within 7 days, {len(retired)} retired. Curated by hand every Monday and Thursday; every record carries a `verified` flag saying whether a person has checked its dates and links against the source page.

Status is derived, not asserted: `new` means opened or first seen within 14 days,
`closing soon` means the stated closing date is within 7 days, `retired` means past that
date or withdrawn. Always confirm a deadline on the official page before submitting.

Content is bilingual (English and French); French fields are suffixed `_fr` and fall back
to English when a translation is not yet written. Data is CC BY 4.0 -- reuse it freely with
attribution to the AI Consultation Deadlines Canada. Underlying government content is
reproduced under the Open Government Licence - Canada.

## Structured data

- [items.json]({SITE_URL}/items.json): every record, full fields. Start here.
- [feed.json]({SITE_URL}/feed.json): JSON Feed 1.1, newest first, with a `_monitor` object per item carrying status, deadline and verification.
- [llms-full.txt]({SITE_URL}/llms-full.txt): every item as Markdown, the whole corpus in one fetch.
- [feed.xml]({SITE_URL}/feed.xml): RSS 2.0, English.
- [feed-fr.xml]({SITE_URL}/feed-fr.xml): RSS 2.0, French.
- [digest.md]({SITE_URL}/digest.md): this week's digest, English. [digest-fr.md]({SITE_URL}/digest-fr.md) for French.

## Live query

An MCP server exposes the same store as tools an agent can call directly -- `list_open`,
`closing_soon`, `list_new`, `search`, `get_item`, `list_topics`, `monitor_status` -- so an
assistant can answer "what is open right now" without fetching and re-parsing this site.
See [docs/MCP.md](https://github.com/donjguido/canadian-ai-governance-monitor/blob/main/docs/MCP.md).

## Closing within 7 days

{chr(10).join(_md_line(r) for r in soon) if soon else "- Nothing closing in the next 7 days."}

## New in the last 14 days

{chr(10).join(_md_line(r) for r in fresh) if fresh else "- Nothing new in the last 14 days."}

## All open items

{chr(10).join(_md_line(r) for r in open_recs) if open_recs else "- Nothing open."}

## Optional

- [Source repository](https://github.com/donjguido/canadian-ai-governance-monitor): pipeline, data model, source inventory.
- [Retired items]({SITE_URL}/items.json): past their closing date or withdrawn; kept in items.json with `"status": "retired"` for the record.
"""
    (out / "llms.txt").write_text(text, encoding="utf-8")


def build_llms_full(records: list[dict], out: Path, today: date) -> None:
    """The entire corpus as Markdown, so an agent can read everything in one request
    instead of crawling the page and re-deriving it from the DOM."""
    parts = [
        "# AI Consultation Deadlines Canada - full corpus",
        "",
        f"Generated {today.isoformat()} from {SITE_URL}/items.json. {len(records)} items.",
        "CC BY 4.0. Government content under the Open Government Licence - Canada.",
        "Status is derived from the stated closing date: new = within 14 days of opening,",
        "closing soon = closes within 7 days, retired = past the date or withdrawn.",
        "`verified: false` means no person has yet checked the dates and links.",
        "",
    ]
    for group, label in (("open", "Open"), ("retired", "Retired")):
        rows = [r for r in records if r["status"] == group]
        if not rows:
            continue
        parts += [f"## {label} ({len(rows)})", ""]
        for r in rows:
            parts.append(f"### {r['title']}")
            parts.append("")
            fields = [
                ("ID", r["id"]),
                ("Body", r["body"]),
                ("Type", TYPE_LABEL.get(r["type"], r["type"])),
                ("Status", "closing soon" if "closing_soon" in r["badges"] else r["status"]),
                ("Opened", r["opened"] or "not stated"),
                ("Closes", r["closes"] or "no stated deadline"),
                ("Days left", r["days_left"] if r["days_left"] is not None else "n/a"),
                ("Topics", ", ".join(r["topics"]) or "none"),
                ("Verified by a human", "yes" if r["verified"] else "no"),
                ("Source", r["url"]),
                ("Permalink", f"{SITE_URL}/#item-{r['id']}"),
            ]
            parts += [f"- {k}: {v}" for k, v in fields]
            parts += [
                "",
                f"Summary: {r['summary']}",
                "",
                f"Why it matters: {r['why_it_matters']}",
                "",
                f"How to participate: {r['how_to_participate'] or 'See the source page.'}",
                "",
            ]
            if r["title_fr"]:
                parts += [f"Titre (fr): {r['title_fr']}", ""]
            if r["summary_fr"]:
                parts += [f"Resume (fr): {r['summary_fr']}", ""]
    (out / "llms-full.txt").write_text("\n".join(parts) + "\n", encoding="utf-8")


# Crawlers named here are the ones that read robots.txt under their own user agent;
# the wildcard group already allows everything, so these blocks exist to say so
# unambiguously to AI crawlers that treat an absent rule as a reason to back off.
AI_AGENTS = [
    "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-User",
    "Claude-SearchBot", "anthropic-ai", "PerplexityBot", "Perplexity-User",
    "Google-Extended", "Applebot-Extended", "CCBot", "Amazonbot",
    "meta-externalagent", "DuckAssistBot", "cohere-ai", "Bytespider",
    "Diffbot", "TimpiBot", "YouBot", "Kagibot",
]


def build_robots(out: Path) -> None:
    """robots.txt for the published site.

    Note: on a github.io *project* page the file that crawlers actually read is
    https://<user>.github.io/robots.txt, at the domain root, which this repo does
    not own. This file is correct and becomes authoritative the moment the monitor
    moves to a custom domain; until then it documents the intent and is still read
    by tools that fetch it directly.
    """
    lines = [
        "# AI Consultation Deadlines Canada",
        "# A public register of Canadian federal channels for shaping AI governance.",
        "#",
        "# Crawling, indexing and machine reading are welcome, AI systems included.",
        "# Data is CC BY 4.0: reuse it with attribution to the Canadian AI Governance",
        "# Monitor, and link to each item's official source page rather than replacing it.",
        "# Underlying government content is under the Open Government Licence - Canada.",
        "#",
        "# Prefer the structured outputs over scraping the HTML:",
        f"#   {SITE_URL}/llms.txt        orientation for agents",
        f"#   {SITE_URL}/llms-full.txt   every item as Markdown",
        f"#   {SITE_URL}/items.json      full records",
        f"#   {SITE_URL}/feed.json       JSON Feed 1.1",
        "",
        "User-agent: *",
        "Allow: /",
        "",
    ]
    for agent in AI_AGENTS:
        lines += [f"User-agent: {agent}", "Allow: /", ""]
    lines += [f"Sitemap: {SITE_URL}/sitemap.xml", ""]
    (out / "robots.txt").write_text("\n".join(lines), encoding="utf-8")


def build_sitemap(out: Path, today: date) -> None:
    urls = [
        (f"{SITE_URL}/", "1.0"),
        (f"{SITE_URL}/?lang=fr", "0.8"),
        (f"{SITE_URL}/llms.txt", "0.6"),
        (f"{SITE_URL}/llms-full.txt", "0.6"),
        (f"{SITE_URL}/digest.md", "0.4"),
        (f"{SITE_URL}/digest-fr.md", "0.4"),
    ]
    body = "".join(
        f"<url><loc>{escape(u)}</loc><lastmod>{today.isoformat()}</lastmod>"
        f"<changefreq>weekly</changefreq><priority>{p}</priority></url>"
        for u, p in urls
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + body + "</urlset>")
    (out / "sitemap.xml").write_text(xml, encoding="utf-8")


def main(items_path: str, out_dir: str) -> None:
    today = date.today()
    items = load_items(items_path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = build_site(items, out, today)
    for lang in ("en", "fr"):
        build_feed(items, out, today, lang)
        build_calendar(items, out, today, lang)
        build_digest(items, out, today, lang)
    build_json_feed(records, out, today)
    build_llms(records, out, today)
    build_llms_full(records, out, today)
    build_robots(out)
    build_sitemap(out, today)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    counts = {b: sum(1 for i in items if b in i.badges(today)) for b in ["new", "open", "closing_soon", "retired"]}
    print(f"built {len(items)} items -> {out}  {counts}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
