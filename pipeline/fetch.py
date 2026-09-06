"""Fetch candidate items from every configured source.

Usage: python -m pipeline.fetch data/candidates.json

Each fetcher returns raw candidates: {id, source, body, url, title, text,
opened?, closes?, title_<lang>?}. A cheap keyword pre-filter (the
`prefilter_keywords` list in data/site.yaml) drops obviously unrelated records
so the LLM classifier (pipeline/classify.py) only sees plausible ones. Sources
are configured in data/sources.yaml; `kind` picks the fetcher:

    csv         a CSV export with a column mapping (a consultation registry's open data)
    json_api    a JSON endpoint with a field mapping
    rss         an RSS or Atom feed (official gazettes, department news)
    sitemap     an XML sitemap filtered by URL pattern, each page fetched
    html_index  an index page scraped for links matching a CSS selector

The first four are generic and need no Python to point at a new jurisdiction;
`html_index` is the model for anything that has no feed.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import feedparser
import requests
import yaml
from bs4 import BeautifulSoup

from .config import ROOT, SITE, SLUG, translated_fields, SECONDARY

UA = {"User-Agent": f"{SLUG}/{SITE.get('version', '1.0')} (+{SITE.get('repo') or SITE['url']})"}
SOURCES = yaml.safe_load((ROOT / "data" / "sources.yaml").read_text(encoding="utf-8"))

KEYWORDS = re.compile(r"\b(" + "|".join(SITE["prefilter_keywords"]) + r")\b", re.I) if SITE["prefilter_keywords"] else None


def relevant(text: str) -> bool:
    return True if KEYWORDS is None else bool(KEYWORDS.search(text or ""))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]


def fetch_page(url: str) -> tuple[str, str]:
    """(title, visible text) of a page; a failed fetch gives an empty title and a note."""
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        for t in soup(["script", "style", "nav", "header", "footer"]):
            t.decompose()
        return title, re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    except Exception as e:  # noqa: BLE001
        return "", f"(fetch failed: {e})"


def fetch_text(url: str) -> str:
    return fetch_page(url)[1]


def _get(row: Any, path: str | None) -> Any:
    """Dotted-path lookup into a dict (or a CSV row). Missing keys give None."""
    if not path:
        return None
    cur = row
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            cur = cur[int(part)] if int(part) < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur


def _record(cfg: dict, row: Any) -> dict | None:
    """Turn one row of a csv/json_api source into a candidate using its `columns` map.

    columns:
      id: registration_number        # optional; defaults to a slug of the title
      title: title_en
      title_fr: title_fr             # any <field>_<lang> the model has may be mapped
      url: profile_page_en
      opened: start_date
      closes: end_date
      status: status                 # optional, checked against `open_statuses`
      body: owner_org_title          # optional, falls back to the source's `body`
      text: [title_en, description_en, subjects]   # columns joined for the keyword filter
    """
    cols = cfg["columns"]
    status = _get(row, cols.get("status"))
    if cols.get("status") and cfg.get("open_statuses") and status not in cfg["open_statuses"]:
        return None
    title = _get(row, cols["title"])
    if not title:
        for lang in SECONDARY:
            title = _get(row, cols.get(f"title_{lang}"))
            if title:
                break
    if not title:
        return None
    text_cols = cols.get("text") or [cols["title"]]
    blob = " ".join(str(_get(row, c) or "") for c in text_cols)
    if not relevant(blob):
        return None
    raw_id = _get(row, cols.get("id"))
    rec = {
        "id": f"{cfg.get('id_prefix', cfg['key'] + '-')}{raw_id or slug(str(title))}",
        "source": cfg["key"],
        "body": str(_get(row, cols.get("body")) or cfg.get("body", "")),
        "url": str(_get(row, cols["url"]) or cfg.get("portal") or cfg.get("url") or ""),
        "title": str(title),
        "text": blob,
        "opened": (str(_get(row, cols.get("opened")) or "")[:10]) or None,
        "closes": (str(_get(row, cols.get("closes")) or "")[:10]) or None,
    }
    for lang in SECONDARY:
        for f in translated_fields(lang):
            if cols.get(f):
                v = _get(row, cols[f])
                if v:
                    rec[f] = str(v)
    return rec if rec["url"] else None


# ---------------------------------------------------------------- sources --

def csv_source(cfg: dict) -> list[dict]:
    """A CSV export with a `columns` mapping (see _record)."""
    r = requests.get(cfg["csv"] if "csv" in cfg else cfg["url"], headers=UA, timeout=60)
    r.raise_for_status()
    rows = csv.DictReader(io.StringIO(r.content.decode(cfg.get("encoding", "utf-8-sig"))),
                          delimiter=cfg.get("delimiter", ","))
    out = []
    for row in rows:
        rec = _record(cfg, row)
        if rec:
            out.append(rec)
    return out


def json_api(cfg: dict) -> list[dict]:
    """A JSON endpoint. `items_path` is a dotted path to the list (blank for a top-level
    list); `columns` maps candidate fields to dotted paths inside each element."""
    r = requests.get(cfg["url"], headers={**UA, "Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    data = r.json()
    rows = _get(data, cfg.get("items_path")) if cfg.get("items_path") else data
    if not isinstance(rows, list):
        raise ValueError(f"{cfg['key']}: items_path {cfg.get('items_path')!r} did not yield a list")
    out = []
    for row in rows:
        rec = _record(cfg, row)
        if rec:
            out.append(rec)
    return out


def rss(cfg: dict) -> list[dict]:
    """Generic RSS/Atom source (an official gazette, department news feeds)."""
    feed = feedparser.parse(cfg["url"])
    out = []
    for e in feed.entries:
        title, link = str(e.get("title", "")), str(e.get("link", ""))
        blob = f"{title} {e.get('summary', '')}"
        if not link or not relevant(blob):
            continue
        out.append({
            "id": f"{cfg['key']}-{slug(title)}",
            "source": cfg["key"],
            "body": cfg.get("body", ""),
            "url": link,
            "title": title,
            "text": fetch_text(link) if cfg.get("fetch_pages") else blob,
            "opened": str(e.get("published", ""))[:10] or None,
            "closes": None,  # the classifier extracts the comment deadline from page text
        })
    return out


def sitemap(cfg: dict) -> list[dict]:
    """An XML sitemap (or sitemap index). `include` is a regex the URL must match;
    `limit` caps how many pages are fetched per run. Each matching page is fetched
    and passes the keyword filter on its text; the title comes from <title>."""
    include = re.compile(cfg["include"]) if cfg.get("include") else None
    limit = int(cfg.get("limit", 200))
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    def locs(url: str, depth: int = 0) -> list[str]:
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        found = []
        if root.tag.endswith("sitemapindex") and depth < 2:
            for child in root.findall("sm:sitemap/sm:loc", ns):
                if child.text:
                    found += locs(child.text.strip(), depth + 1)
        else:
            found = [el.text.strip() for el in root.findall("sm:url/sm:loc", ns) if el.text]
        return found

    out = []
    for url in locs(cfg["url"]):
        if include and not include.search(url):
            continue
        if len(out) >= limit:
            break
        title, text = fetch_page(url)
        if not relevant(text):
            continue
        title = re.split(r"\s+[|\-–—]\s+", title)[0].strip() or text[:120].strip()
        out.append({
            "id": f"{cfg['key']}-{slug(title)}",
            "source": cfg["key"],
            "body": cfg.get("body", ""),
            "url": url,
            "title": title,
            "text": text,
            "opened": None,
            "closes": None,
        })
    return out


def html_index(cfg: dict) -> list[dict]:
    """Scrape an HTML index page for links matching a selector (committee study lists,
    a regulator's consultations page, a standards body's notices)."""
    r = requests.get(cfg["url"], headers=UA, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for a in soup.select(cfg["selector"]):
        title = a.get_text(" ", strip=True)
        href = a.get("href")
        if not href or not title or not relevant(title):
            continue
        url = urljoin(cfg["url"], str(href))
        out.append({
            "id": f"{cfg['key']}-{slug(title)}",
            "source": cfg["key"],
            "body": cfg.get("body", ""),
            "url": url,
            "title": title,
            "text": fetch_text(url),
            "opened": None,
            "closes": None,
        })
    return out


FETCHERS = {"csv": csv_source, "json_api": json_api, "rss": rss, "sitemap": sitemap, "html_index": html_index}


def main(out_path: str) -> None:
    candidates: list[dict] = []
    for cfg in SOURCES["sources"]:
        if not cfg.get("enabled", True):
            continue
        try:
            found = FETCHERS[cfg["kind"]](cfg)
            print(f"{cfg['key']:28s} {len(found):4d} candidates")
            candidates.extend(found)
        except Exception as e:  # noqa: BLE001
            print(f"{cfg['key']:28s} FAILED: {e}", file=sys.stderr)
    Path(out_path).write_text(json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {len(candidates)} candidates -> {out_path}")


if __name__ == "__main__":
    main(sys.argv[1])
