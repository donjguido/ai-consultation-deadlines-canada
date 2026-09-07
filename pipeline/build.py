"""Build every published artefact from data/items.json.

Usage: python -m pipeline.build data/items.json site

Writes, into the output directory:

    index.html      the site, with the item list rendered into the HTML (not
                    only into JavaScript) so crawlers and text-mode agents
                    read the same content a browser shows, plus schema.org
                    JSON-LD describing the dataset and every item
    items.json      full records, the JSON API
    feed.xml        RSS 2.0 in the primary language; feed-<lang>.xml per secondary language
    feed.json       JSON Feed 1.1
    deadlines.ics   iCalendar feed of closing dates, subscribable by webcal://
                    (deadlines-<lang>.ics per secondary language)
    digest.md       weekly digest (digest-<lang>.md per secondary language)
    llms.txt        orientation page for AI agents (llmstxt.org convention)
    llms-full.txt   every item as Markdown, the whole corpus in one fetch
    forks.json      this site and its sister sites, from data/forks.yaml
    robots.txt      crawling explicitly permitted, including for AI crawlers
    sitemap.xml     the readable URLs
    .nojekyll       stop GitHub Pages running the files through Jekyll

Every name, URL, language and licence comes from data/site.yaml via pipeline/config.py.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote

from .config import (
    LANGS, NAME, PRIMARY, REPO, SECONDARY, SITE, SITE_URL, SLUG, TRANSLATED_FIELDS,
    load_forks, locale, output_name, pick, plural, self_entry, strings,
)
from .models import Item

TEMPLATE = Path(__file__).parent / "template.html"

COLOR = {k: f"var(--{'soon' if k == 'closing_soon' else k})" for k in ("new", "closing_soon", "open", "retired")}
BG = {k: v[:-1] + "-bg)" for k, v in COLOR.items()}
BADGE_ORDER = ("new", "open", "closing_soon", "retired")


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


def days_left_label(d: int, lang: str = PRIMARY) -> str:
    return plural(strings(lang), "days_left", d)


def type_label(t: dict, type_: str) -> str:
    return t["type"].get(type_, type_)


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


# ---- server-side rendering ---------------------------------------------------
# Mirrors renderList() in template.html. Both must produce the same markup in the
# primary language: the client skips its first list render when the page loads in
# that language, so this is what most readers see.

def render_stats_html(records: list[dict], lang: str = PRIMARY) -> str:
    t = strings(lang)
    counts = {k: 0 for k in BADGE_ORDER}
    for r in records:
        for b in r["badges"]:
            counts[b] += 1
    return "".join(
        f'<button class="stat" style="--c:{COLOR[k]}" data-k="{k}" aria-pressed="false">\n'
        f'      <div class="n">{counts[k]}</div><div class="l">{t["badge"][k]}</div>'
        f'<div class="h">{t["badge_hint"][k]}</div></button>'
        for k in BADGE_ORDER
    )


def has_upcoming_deadline(item: Item, today: date) -> bool:
    """Whether the item is worth putting in a calendar: still open, and the date
    is still ahead. Mirrors upcoming() in template.html, which re-checks against
    the reader's own date because the baked-in status ages between builds."""
    return item.closes is not None and item.closes >= today and item.status(today) == "open"


def render_cal_menu(item: Item, lang: str = PRIMARY) -> str:
    """Server-side twin of calMenu() in template.html, whitespace included."""
    t = strings(lang)
    return (
        f'<div class="cal">\n'
        f'    <button class="cal-btn" data-cal="{esc(item.id)}" aria-expanded="false" aria-haspopup="true">'
        f'\U0001F4C5 {esc(t["add_cal"])}</button>\n'
        f'    <div class="cal-menu" role="menu" hidden>\n'
        f'      <a role="menuitem" href="{esc(google_url(item, lang))}" target="_blank" rel="noopener">Google Calendar</a>\n'
        f'      <a role="menuitem" href="{esc(outlook_url(item, lang))}" target="_blank" rel="noopener">Outlook</a>\n'
        f'      <button role="menuitem" data-ics="{esc(item.id)}">{esc(t["ics_one"])}</button>\n'
        f'    </div></div>'
    )


def fmt_date(iso: str | date | None, lang: str) -> str:
    """A date as the strings file for `lang` wants it: ISO as written when `date_style`
    is iso, else `date_format` filled with the day, the short month and the year. The
    client formatter in the template does the same with Intl, so the first paint and a
    re-render agree."""
    if not iso:
        return ""
    s = iso.isoformat() if isinstance(iso, date) else str(iso)
    t = strings(lang)
    if t.get("date_style") != "long" or not t.get("months_short") or not t.get("date_format"):
        return s
    try:
        y, m, d = (int(x) for x in s[:10].split("-"))
        return t["date_format"].format(d=d, mon=t["months_short"][m - 1], y=y)
    except (ValueError, IndexError):
        return s


def render_items_html(records: list[dict], by_id: dict[str, Item], today: date, lang: str = PRIMARY) -> str:
    t = strings(lang)
    out = []
    for r in records:
        p = primary(r)
        if r["closes"]:
            label = t["closed"] if p == "retired" else t["closes"]
            when = f'<b>{label} <time datetime="{esc(r["closes"])}">{esc(fmt_date(r["closes"], lang))}</time></b>'
            if r["days_left"] is not None:
                when += f'<span>{days_left_label(r["days_left"], lang)}</span>'
        else:
            when = f'<b>{esc(t["no_deadline"])}</b>'
        opened = (f'<span class="d">{esc(t["opened"])} <time datetime="{esc(r["opened"])}">{esc(fmt_date(r["opened"], lang))}</time></span>'
                  if r["opened"] else "")
        shown = [b for b in r["badges"] if b != "open" or len(r["badges"]) == 1]
        badges = "".join(
            f'<span class="badge" style="--c:{COLOR[b]};--bg:{BG[b]}">{t["badge"][b]}</span>' for b in shown
        )
        warn = "" if r["verified"] else f' <span class="unverified" title="{esc(t["unverified"])}">⚠</span>'
        how = (f'<p class="how"><strong>{esc(t["how"])}</strong> {esc(pick(r, "how_to_participate", lang))}</p>'
               if r["how_to_participate"] else "")
        topics = "".join(f'<span class="topic">{esc(t["topic"].get(x, x))}</span>' for x in r["topics"])
        cal = render_cal_menu(by_id[r["id"]], lang) if has_upcoming_deadline(by_id[r["id"]], today) else ""
        out.append(
            f'<article class="item {p}" id="item-{esc(r["id"])}" style="--c:{COLOR[p]}">\n'
            f'      <div class="stripe" aria-hidden="true"></div>\n'
            f'      <div class="when">{when}{opened}</div>\n'
            f'      <div class="main">\n'
            f'        <h3><a href="{esc(r["url"])}" rel="noopener external">{esc(pick(r, "title", lang))}</a></h3>\n'
            f'        <div class="body">{esc(pick(r, "body", lang))}<span class="type">{type_label(t, r["type"])}</span>'
            f'<span class="badges">{badges}</span>{warn}</div>\n'
            f'        <p>{esc(pick(r, "summary", lang))}</p>\n'
            f'        <p class="why"><em>{esc(t["why"])}</em> {esc(pick(r, "why_it_matters", lang))}</p>\n'
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
    t = strings(PRIMARY)
    author = SITE["author"]
    licence = SITE["licence"]
    person = {"@type": "Person", "@id": f"{SITE_URL}/#curator",
              "name": author.get("name", ""), "url": author.get("url", REPO)}
    site = {
        "@type": "WebSite", "@id": f"{SITE_URL}/#website", "url": f"{SITE_URL}/",
        "name": t["text"]["title"],
        "description": t["text"]["description"], "inLanguage": [locale(x) for x in LANGS],
        "publisher": {"@id": person["@id"]},
        "license": licence.get("data_url", ""),
    }
    alternates = [strings(x)["text"]["title"] for x in SECONDARY if strings(x)["text"]["title"] != t["text"]["title"]]
    if alternates:
        site["alternateName"] = alternates if len(alternates) > 1 else alternates[0]
    dates = sorted(r["closes"] for r in records if r["closes"])
    place = {"@type": SITE["jurisdiction"].get("schema_type", "Place"), "name": SITE["jurisdiction"]["name"]}
    dataset = {
        "@type": "Dataset", "@id": f"{SITE_URL}/#dataset", "url": f"{SITE_URL}/",
        "name": t["text"]["dataset_name"],
        "description": t["dataset_description"].format(audience=t["text"]["audience"], channels=t["text"]["channels"]),
        "creator": {"@id": person["@id"]}, "isAccessibleForFree": True,
        "license": licence.get("data_url", ""),
        "dateModified": today.isoformat(),
        "inLanguage": [locale(x) for x in LANGS],
        "spatialCoverage": place,
        "isPartOf": {"@id": site["@id"]},
        "keywords": list(SITE["keywords"]),
        "distribution": [
            {"@type": "DataDownload", "name": "Full records (JSON)",
             "encodingFormat": "application/json", "contentUrl": f"{SITE_URL}/items.json"},
            {"@type": "DataDownload", "name": "JSON Feed",
             "encodingFormat": "application/feed+json", "contentUrl": f"{SITE_URL}/feed.json"},
            *[{"@type": "DataDownload", "name": f"RSS ({strings(x).get('language_name_en', x)})",
               "encodingFormat": "application/rss+xml",
               "contentUrl": f"{SITE_URL}/{output_name('feed', '.xml', x)}"} for x in LANGS],
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
            "abstract": r["why_it_matters"], "inLanguage": locale(PRIMARY),
            "genre": type_label(t, r["type"]),
            "creativeWorkStatus": "closing soon" if "closing_soon" in r["badges"] else r["status"],
            "keywords": r["topics"], "isPartOf": {"@id": dataset["@id"]},
            "publisher": {"@type": "GovernmentOrganization", "name": r["body"]},
            "spatialCoverage": place,
        }
        alt = [r.get(f"title_{x}") for x in SECONDARY if r.get(f"title_{x}")]
        if alt:
            work["alternateName"] = alt if len(alt) > 1 else alt[0]
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
        "name": f"Open and recently closed {SITE['jurisdiction'].get('level', '')} AI-governance channels".replace("  ", " "),
        "numberOfItems": len(records),
        "itemListOrder": "https://schema.org/ItemListOrderAscending",
        "itemListElement": elements,
    }]
    payload = js_json({"@context": "https://schema.org", "@graph": graph})
    return f'<script type="application/ld+json">{payload}</script>'


# ---- template filling -------------------------------------------------------

def render_head_links() -> str:
    """Canonical, hreflang alternates, feed discovery and Open Graph locale tags."""
    lines = [f'<link rel="canonical" href="{SITE_URL}/">']
    for lang in LANGS:
        href = f"{SITE_URL}/" if lang == PRIMARY else f"{SITE_URL}/?lang={lang}"
        lines.append(f'<link rel="alternate" hreflang="{locale(lang).lower()}" href="{href}">')
    lines.append(f'<link rel="alternate" hreflang="x-default" href="{SITE_URL}/">')
    for lang in LANGS:
        t = strings(lang)
        hl = "" if lang == PRIMARY else f' hreflang="{locale(lang).lower()}"'
        lines.append(f'<link rel="alternate" type="application/rss+xml"{hl} title="{esc(t["text"]["title"])} — {esc(t["rss"])}" '
                     f'href="{output_name("feed", ".xml", lang)}">')
    t = strings(PRIMARY)
    lines += [
        f'<link rel="alternate" type="application/feed+json" title="{esc(t["text"]["title"])} — JSON Feed" href="feed.json">',
        f'<link rel="alternate" type="application/json" title="{esc(t["text"]["title"])} — full records" href="items.json">',
        f'<link rel="alternate" type="text/markdown" title="{esc(t["text"]["title"])} — every item as Markdown" href="llms-full.txt">',
        f'<meta property="og:locale" content="{locale(PRIMARY).replace("-", "_")}">',
        *[f'<meta property="og:locale:alternate" content="{locale(x).replace("-", "_")}">' for x in SECONDARY],
    ]
    return "\n".join(lines)


def render_lang_buttons() -> str:
    if len(LANGS) < 2:
        return ""
    return " ".join(
        f'<button type="button" data-lang="{lang}" aria-pressed="{"true" if lang == PRIMARY else "false"}" lang="{lang}">'
        f'{lang.upper()}<span class="sr-only"> — {esc(strings(lang)["language_name"])}</span></button>'
        for lang in LANGS
    )


def render_links_line(lang: str, today: date) -> str:
    """The 'built … · RSS · calendar · …' line in the header, one per language."""
    t = strings(lang)
    return (
        f'{esc(t["built"])} {today.isoformat()} · <a href="{output_name("feed", ".xml", lang)}">{esc(t["rss"])}</a>'
        f' · <a href="{output_name("deadlines", ".ics", lang)}">{esc(t["calendar"])}</a>'
        f' · <a href="items.json">{esc(t["json"])}</a>'
        f' · <a href="{output_name("digest", ".md", lang)}">{esc(t["digest"])}</a>'
        f' · <a href="llms.txt">llms.txt</a>'
    )


def render_forks_html() -> str:
    forks = load_forks()
    if not forks:
        return ""
    links = ", ".join(f'<a href="{esc(f["url"])}" rel="noopener">{esc(f["name"])}</a>' for f in forks)
    return f'<p class="forks"><span data-i18n="sister_sites">{esc(strings(PRIMARY)["sister_sites"])}</span> {links}</p>'


def ui_strings(lang: str, today: date) -> dict:
    """Everything the client script needs for one language, with site values filled in."""
    t = dict(strings(lang))
    licence = SITE["licence"]
    t["footer_credit"] = t["footer_credit"].format(
        year=SITE.get("copyright_year", today.year), author=esc(SITE["author"].get("name", "")),
        code_licence=esc(licence.get("code", "")), data_licence=esc(licence.get("data", "")), repo=esc(REPO),
    )
    t["cal_tracked"] = t["cal_tracked"].format(site=t["text"]["title"])
    t["links_line"] = render_links_line(lang, today)
    t["locale"] = locale(lang)
    t["ics_file"] = output_name("deadlines", ".ics", lang)
    return t


def fill_i18n(html: str, t: dict) -> str:
    """Fill every data-i18n element and data-i18n-* attribute with the primary-language
    string, so the page reads correctly before (or without) JavaScript."""
    def elem(m):
        key = m.group(3)
        return f"{m.group(1)}{t.get(key, key)}{m.group(4)}"
    html = re.sub(r'(<(\w+)\b[^>]*\bdata-i18n="([^"]+)"[^>]*>)(?:.*?)(</\2>)', elem, html, flags=re.S)
    def attr(m):
        name, key = m.group(1), m.group(2)
        return f'data-i18n-{name}="{key}" {name}="{esc(t.get(key, key))}"'
    return re.sub(r'\bdata-i18n-(placeholder|aria-label|content)="([^"]+)"\s+\1="[^"]*"', attr, html)


def build_site(items: list[Item], out: Path, today: date) -> list[dict]:
    records = sorted_records(items, today)
    t = strings(PRIMARY)
    open_n = sum(1 for r in records if r["status"] == "open")
    soon_n = sum(1 for r in records if "closing_soon" in r["badges"])
    desc = t["meta_description"].format(n=len(records), channels=t["text"]["channels"], audience=t["text"]["audience"],
                                        open=open_n, soon=soon_n, cadence=t["text"]["cadence"])
    ui = {lang: ui_strings(lang, today) for lang in LANGS}
    config = {
        "site": SITE_URL, "slug": SLUG, "name": NAME, "version": SITE.get("version", "1.0"),
        "primary": PRIMARY, "langs": LANGS, "locales": {x: locale(x) for x in LANGS},
        "fields": list(TRANSLATED_FIELDS),
    }
    html = TEMPLATE.read_text(encoding="utf-8")
    html = fill_i18n(html, {**ui[PRIMARY], **ui[PRIMARY]["text"]})
    html = html.replace("__DESC__", esc(desc))
    html = html.replace("__SITE_URL__", SITE_URL)
    html = html.replace("__SLUG__", esc(SLUG))
    html = html.replace("__LOCALE__", esc(locale(PRIMARY)))
    html = html.replace("__PLACE__", esc(SITE["jurisdiction"]["name"]))
    html = html.replace("__LICENCE_URL__", esc(SITE["licence"].get("data_url", "")))
    html = html.replace("__COUNT__", plural(t, "count", len(records), total=len(records)))
    html = html.replace("__BUILT__", today.isoformat())
    html = html.replace("<!--__HEAD_LINKS__-->", render_head_links())
    html = html.replace("<!--__LANG_BUTTONS__-->", render_lang_buttons())
    html = html.replace("<!--__FORKS__-->", render_forks_html())
    # Generated content goes in last so nothing inside it is scanned for placeholders.
    html = html.replace("<!--__STATS__-->", render_stats_html(records))
    html = html.replace("<!--__ITEMS__-->", render_items_html(records, {i.id: i for i in items}, today))
    html = html.replace("<!--__JSONLD__-->", render_jsonld(records, today))
    html = html.replace("/*__CONFIG__*/{}", js_json(config))
    html = html.replace("/*__L__*/{}", js_json(ui))
    html = html.replace("/*__DATA__*/[]", js_json(records))
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "items.json").write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    return records


# ---- feeds -------------------------------------------------------------------

def build_feed(items: list[Item], out: Path, today: date, lang: str = PRIMARY) -> None:
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    t = strings(lang)
    feed_file = output_name("feed", ".xml", lang)
    entries = []
    for i in sorted(items, key=lambda x: x.first_seen, reverse=True):
        text = lambda f: pick(i, f, lang)  # noqa: E731
        badges = " · ".join(t["badge"][b].upper() for b in i.badges(today))
        if i.closes:
            closes = f"{t['closed'] if i.status(today) == 'retired' else t['closes']} {fmt_date(i.closes, lang)}"
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
        f"<title>{escape(t['text']['title'])}</title>"
        f"<link>{SITE_URL}/</link><description>{escape(t['text']['description'])}</description>"
        f'<atom:link href="{SITE_URL}/{feed_file}" rel="self" type="application/rss+xml"/>'
        f'<atom:link href="{SITE_URL}/" rel="alternate" type="text/html"/>'
        f"<language>{locale(lang).lower()}</language><lastBuildDate>{now}</lastBuildDate>"
        f"<generator>{escape(SLUG)}</generator>"
        "<docs>https://www.rssboard.org/rss-specification</docs>"
        f"<copyright>{escape(SITE['licence'].get('data', ''))}</copyright><ttl>720</ttl>" + "".join(entries) + "</channel></rss>"
    )
    (out / feed_file).write_text(xml, encoding="utf-8")


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


def cal_text(item: Item, lang: str = PRIMARY) -> tuple[str, str]:
    """Event title and body, shared by the .ics feed and the Google/Outlook links.
    Mirrors calText() in template.html; the two must agree in the primary language,
    because build.py renders that list and the client only re-renders on interaction."""
    t = strings(lang)
    text = lambda f: pick(item, f, lang)  # noqa: E731
    parts = [text("body"), text("summary"), f"{t['why']} {text('why_it_matters')}"]
    if item.how_to_participate:
        parts.append(f"{t['how']} {text('how_to_participate')}")
    if not item.verified:
        parts.append("⚠ " + t["cal_unverified"])
    parts += [item.url, f"{t['cal_tracked'].format(site=t['text']['title'])} {SITE_URL}"]
    return f"{t['deadline_prefix']} {text('title')}", "\n".join(parts)


# JavaScript's encodeURIComponent leaves these alone; Python's quote() would not.
_URI_SAFE = "-_.!~*'()"


def _qs(pairs: list[tuple[str, str]]) -> str:
    """Query string byte-identical to the client's qs() helper."""
    return "&".join(f"{quote(k, safe=_URI_SAFE)}={quote(v, safe=_URI_SAFE)}" for k, v in pairs)


def google_url(item: Item, lang: str = PRIMARY) -> str:
    """Google Calendar's event template: one event per URL, so single deadlines only."""
    title, details = cal_text(item, lang)
    closes = item.closes
    assert closes is not None
    return "https://calendar.google.com/calendar/render?" + _qs([
        ("action", "TEMPLATE"), ("text", title), ("details", details),
        ("dates", f"{closes:%Y%m%d}/{closes + timedelta(days=1):%Y%m%d}"),
    ])


def outlook_url(item: Item, lang: str = PRIMARY) -> str:
    title, details = cal_text(item, lang)
    closes = item.closes
    assert closes is not None
    return "https://outlook.live.com/calendar/0/deeplink/compose?" + _qs([
        ("path", "/calendar/action/compose"), ("rru", "addevent"),
        ("subject", title), ("body", details),
        ("startdt", closes.isoformat()), ("enddt", (closes + timedelta(days=1)).isoformat()),
        ("allday", "true"),
    ])


def ics_event(item: Item, stamp: str, lang: str = PRIMARY) -> list[str]:
    """One all-day VEVENT on the closing date, with 7-day and 1-day reminders."""
    closes = item.closes
    if closes is None:  # nothing to put in a calendar
        return []
    t = strings(lang)
    summary, description = cal_text(item, lang)
    title = pick(item, "title", lang)
    lines = [
        "BEGIN:VEVENT",
        f"UID:{item.id}@{SLUG}",
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
    for trigger, key in (("-P7D", "alarm_7"), ("-P1D", "alarm_1")):
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_ics_text(t[key].format(x=title))}",
            f"TRIGGER;VALUE=DURATION:{trigger}",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def build_calendar(items: list[Item], out: Path, today: date, lang: str = PRIMARY) -> None:
    """Publish deadlines.ics: every open item whose stated closing date is still ahead."""
    t = strings(lang)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    upcoming = sorted(
        (i for i in items if has_upcoming_deadline(i, today)),
        key=lambda i: (i.closes, i.id),
    )
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{NAME}//v{SITE.get('version', '1.0')}//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"NAME:{_ics_text(t['text']['title'])}",
        f"X-WR-CALNAME:{_ics_text(t['text']['title'])}",
        f"DESCRIPTION:{_ics_text(t['text']['calendar_description'])}",
        f"X-WR-CALDESC:{_ics_text(t['text']['calendar_description'])}",
        f"X-WR-CALLANG:{locale(lang).lower()}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
    ]
    for i in upcoming:
        lines += ics_event(i, stamp, lang)
    lines.append("END:VCALENDAR")
    text = "".join(_ics_fold(line) + "\r\n" for line in lines)
    (out / output_name("deadlines", ".ics", lang)).write_bytes(text.encode("utf-8"))


# ---- digest ------------------------------------------------------------------

def build_digest(items: list[Item], out: Path, today: date, lang: str = PRIMARY) -> None:
    """Plain-text weekly digest, ready to paste into the newsletter tool or send via API."""
    t = strings(lang)
    sep = t.get("sep", ": ")
    text = lambda i, f: pick(i, f, lang)  # noqa: E731
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
                when = f"{t['closed'].lower() if i.status(today) == 'retired' else t['closes'].lower()} {fmt_date(i.closes, lang)}"
            else:
                when = t["no_deadline"].lower()
            lines.append(
                f"- **{text(i, 'title')}** ({text(i, 'body')}, {when})\n  {text(i, 'summary')}\n"
                f"  {t['how']} {text(i, 'how_to_participate')}\n  {i.url}"
            )
        return "\n".join(lines) + "\n\n"

    body = (
        f"# {t['text']['title']}, {t['week_of']} {today.isoformat()}\n\n"
        + block(t["sec_closing"], closing)
        + block(t["sec_new"], new)
        + block(t["sec_open"], open_)
        + block(t["sec_retired"], retired)
        + f"{t['full_list']}{sep}{SITE_URL}  ·  {t['rss']}{sep}{SITE_URL}/{output_name('feed', '.xml', lang)}"
        + f"  ·  {t['calendar']}{sep}{SITE_URL}/{output_name('deadlines', '.ics', lang)}\n"
    )
    (out / output_name("digest", ".md", lang)).write_text(body, encoding="utf-8")


# ---- machine-readable extras ---------------------------------------------------

def build_json_feed(records: list[dict], out: Path, today: date) -> None:
    """JSON Feed 1.1 -- the same items as feed.xml, but self-describing for parsers
    that would rather not touch XML."""
    t = strings(PRIMARY)
    feed = {
        "version": "https://jsonfeed.org/version/1.1",
        "title": t["text"]["title"],
        "home_page_url": f"{SITE_URL}/",
        "feed_url": f"{SITE_URL}/feed.json",
        "description": t["text"]["description"],
        "language": locale(PRIMARY),
        "authors": [{"name": SITE["author"].get("name", ""), "url": SITE["author"].get("url", REPO)}],
        "items": [],
    }
    for r in sorted(records, key=lambda x: x["first_seen"], reverse=True):
        when = (f"{t['closed'] if r['status'] == 'retired' else t['closes']} {r['closes']}"
                if r["closes"] else t["no_deadline"])
        feed["items"].append({
            "id": f"{SITE_URL}/#item-{r['id']}",
            "url": r["url"],
            "external_url": r["url"],
            "title": r["title"],
            "content_text": (f"{r['body']}. {when}. {r['summary']} "
                             f"{t['why']} {r['why_it_matters']} "
                             f"{t['how']} {r['how_to_participate']}"),
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


def build_forks(out: Path, today: date) -> None:
    """forks.json: this site plus every sister site listed in data/forks.yaml, so the
    family can be discovered from any one member."""
    forks = load_forks()
    note = "Sites built from the same template for other geographies. "
    # Only invite additions when there is a register to add to: an empty data/forks.yaml
    # means this site is not currently taking sister sites, and saying otherwise sends
    # agents and readers to a pull request nobody is waiting for.
    note += ("Add yours by pull request to data/forks.yaml in the template repo."
             if forks else "None are listed at present.")
    payload = {"generated": today.isoformat(), "self": self_entry(), "forks": forks,
               "template": REPO, "note": note}
    (out / "forks.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _md_line(r: dict) -> str:
    when = (f"{'closed' if r['status'] == 'retired' else 'closes'} {r['closes']}"
            if r["closes"] else "no stated deadline")
    return f"- [{r['title']}]({r['url']}): {r['body']}, {when}. {r['summary']}"


def build_llms(records: list[dict], out: Path, today: date) -> None:
    """llms.txt, per the llmstxt.org convention: a short, linked orientation page an
    agent can read first to find out what is here and where the structured data lives."""
    t = strings(PRIMARY)
    licence = SITE["licence"]
    open_recs = [r for r in records if r["status"] == "open"]
    soon = [r for r in records if "closing_soon" in r["badges"]]
    fresh = [r for r in records if "new" in r["badges"]]
    retired = [r for r in records if r["status"] == "retired"]
    forks = load_forks()
    gov = t["text"].get("government_licence")
    if SECONDARY:
        names = ", ".join(strings(x).get("language_name_en", x) for x in SECONDARY)
        suffixes = ", ".join(f"`_{x}`" for x in SECONDARY)
        lang_note = (f"Content is multilingual ({strings(PRIMARY).get('language_name_en', PRIMARY)} and {names}); "
                     f"translated fields are suffixed {suffixes} and fall back to {strings(PRIMARY).get('language_name_en', PRIMARY)} "
                     f"when a translation is not yet written.")
    else:
        lang_note = f"Content is in {strings(PRIMARY).get('language_name_en', PRIMARY)}."
    feeds = "\n".join(
        f"- [{output_name('feed', '.xml', x)}]({SITE_URL}/{output_name('feed', '.xml', x)}): RSS 2.0, {strings(x).get('language_name_en', x)}."
        for x in LANGS
    )
    digests = " ".join(
        f"[{output_name('digest', '.md', x)}]({SITE_URL}/{output_name('digest', '.md', x)})"
        + (": this week's digest." if x == PRIMARY else f" in {strings(x).get('language_name_en', x)}.")
        for x in LANGS
    )
    sisters = ""
    if forks:
        sisters = "\n## Sister sites\n\n" + "\n".join(
            f"- [{f['name']}]({f['url']}): {f.get('jurisdiction', '')}" for f in forks
        ) + f"\n- [forks.json]({SITE_URL}/forks.json): the same list, machine-readable.\n"
    lead = t["llms_lead"].format(audience=t["text"]["audience"], channels=t["text"]["channels"])
    built = t["llms_built"].format(date=today.isoformat(), n=len(records), open=len(open_recs), soon=len(soon),
                                   retired=len(retired), cadence=t["text"]["cadence"])
    text = f"""# {t['text']['title']}

> {lead}

{built}

Status is derived, not asserted: `new` means opened or first seen within 14 days,
`closing soon` means the stated closing date is within 7 days, `retired` means past that
date or withdrawn. Always confirm a deadline on the official page before submitting.

{lang_note} Data is {licence.get('data', '')} -- reuse it freely with
attribution to {t['text']['title']}.{f' Underlying government content is reproduced under the {gov}.' if gov else ''}

## Structured data

- [items.json]({SITE_URL}/items.json): every record, full fields. Start here.
- [feed.json]({SITE_URL}/feed.json): JSON Feed 1.1, newest first, with a `_monitor` object per item carrying status, deadline and verification.
- [llms-full.txt]({SITE_URL}/llms-full.txt): every item as Markdown, the whole corpus in one fetch.
{feeds}
- {digests}
- [forks.json]({SITE_URL}/forks.json): this site and its sister sites for other geographies.

## Live query

An MCP server exposes the same store as tools an agent can call directly -- `list_open`,
`closing_soon`, `list_new`, `search`, `get_item`, `list_topics`, `monitor_status` -- so an
assistant can answer "what is open right now" without fetching and re-parsing this site.
See [docs/MCP.md]({REPO}/blob/main/docs/MCP.md).
{sisters}
## Closing within 7 days

{chr(10).join(_md_line(r) for r in soon) if soon else "- Nothing closing in the next 7 days."}

## New in the last 14 days

{chr(10).join(_md_line(r) for r in fresh) if fresh else "- Nothing new in the last 14 days."}

## All open items

{chr(10).join(_md_line(r) for r in open_recs) if open_recs else "- Nothing open."}

## Optional

- [Source repository]({REPO}): pipeline, data model, source inventory.
- [Retired items]({SITE_URL}/items.json): past their closing date or withdrawn; kept in items.json with `"status": "retired"` for the record.
"""
    (out / "llms.txt").write_text(text, encoding="utf-8")


def build_llms_full(records: list[dict], out: Path, today: date) -> None:
    """The entire corpus as Markdown, so an agent can read everything in one request
    instead of crawling the page and re-deriving it from the DOM."""
    t = strings(PRIMARY)
    gov = t["text"].get("government_licence")
    parts = [
        f"# {t['text']['title']} - full corpus",
        "",
        f"Generated {today.isoformat()} from {SITE_URL}/items.json. {len(records)} items.",
        f"{SITE['licence'].get('data', '')}." + (f" Government content under the {gov}." if gov else ""),
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
                ("Type", type_label(t, r["type"])),
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
            for lang in SECONDARY:
                if r.get(f"title_{lang}"):
                    parts += [f"Title ({lang}): {r[f'title_{lang}']}", ""]
                if r.get(f"summary_{lang}"):
                    parts += [f"Summary ({lang}): {r[f'summary_{lang}']}", ""]
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
    t = strings(PRIMARY)
    gov = t["text"].get("government_licence")
    lines = [
        f"# {t['text']['title']}",
        f"# A public register of {SITE['jurisdiction'].get('level', '')} channels in {SITE['jurisdiction']['name']} for shaping AI governance.".replace("  ", " "),
        "#",
        "# Crawling, indexing and machine reading are welcome, AI systems included.",
        f"# Data is {SITE['licence'].get('data', '')}: reuse it with attribution to {t['text']['title']},",
        "# and link to each item's official source page rather than replacing it.",
        *([f"# Underlying government content is under the {gov}."] if gov else []),
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
    urls = [(f"{SITE_URL}/", "1.0")]
    urls += [(f"{SITE_URL}/?lang={x}", "0.8") for x in SECONDARY]
    urls += [(f"{SITE_URL}/llms.txt", "0.6"), (f"{SITE_URL}/llms-full.txt", "0.6")]
    urls += [(f"{SITE_URL}/{output_name('digest', '.md', x)}", "0.4") for x in LANGS]
    body = "".join(
        f"<url><loc>{escape(u)}</loc><lastmod>{today.isoformat()}</lastmod>"
        f"<changefreq>weekly</changefreq><priority>{p}</priority></url>"
        for u, p in urls
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + body + "</urlset>")
    (out / "sitemap.xml").write_text(xml, encoding="utf-8")


def build_all(items: list[Item], out: Path, today: date) -> list[dict]:
    """Every artefact, in the order the workflow expects. Used by main() and the tests."""
    out.mkdir(parents=True, exist_ok=True)
    records = build_site(items, out, today)
    for lang in LANGS:
        build_feed(items, out, today, lang)
        build_calendar(items, out, today, lang)
        build_digest(items, out, today, lang)
    build_json_feed(records, out, today)
    build_forks(out, today)
    build_llms(records, out, today)
    build_llms_full(records, out, today)
    build_robots(out)
    build_sitemap(out, today)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return records


def main(items_path: str, out_dir: str) -> None:
    today = date.today()
    items = load_items(items_path)
    out = Path(out_dir)
    build_all(items, out, today)
    counts = {b: sum(1 for i in items if b in i.badges(today)) for b in BADGE_ORDER}
    print(f"built {len(items)} items -> {out}  {counts}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
