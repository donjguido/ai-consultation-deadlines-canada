"""Fetch candidate items from every configured federal source.

Usage: python -m pipeline.fetch data/candidates.json

Each fetcher returns raw candidates: {id, source, body, url, title, text,
opened?, closes?}. A cheap keyword pre-filter drops obviously unrelated
records so the LLM classifier (pipeline/classify.py) only sees plausible
ones. Sources are configured in data/sources.yaml.
"""
from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path

import feedparser
import requests
import yaml
from urllib.parse import urljoin
from bs4 import BeautifulSoup

UA = {"User-Agent": "AI-Safety-Participation-Monitor/0.1 (+contact: see repository README)"}
SOURCES = yaml.safe_load((Path(__file__).parent.parent / "data" / "sources.yaml").read_text(encoding="utf-8"))

# Broad on purpose: false positives are cheap (the classifier rejects them);
# false negatives are invisible. Bilingual because many records are FR-first.
KEYWORDS = re.compile(
    r"\b(artificial intelligence|intelligence artificielle|\bAI\b|\bIA\b|machine learning|apprentissage automatique|"
    r"algorithm|algorithme|automated decision|d[ée]cision automatis|deepfake|hypertrucage|synthetic (media|content)|"
    r"biometric|biom[ée]tri|facial recognition|reconnaissance faciale|large language|mod[èe]le de langage|"
    r"chatbot|agent(ic)?\b|compute|data cent(er|re)|privacy|vie priv[ée]e|digital safety|s[ée]curit[ée] num[ée]rique|"
    r"online harm|frontier model|AI safety|s[ûu]ret[ée] de l'IA|robot|autonomous|autonome|generative|g[ée]n[ée]rative)\b",
    re.I,
)


def relevant(text: str) -> bool:
    return bool(KEYWORDS.search(text or ""))


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]


def fetch_text(url: str) -> str:
    try:
        r = requests.get(url, headers=UA, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "header", "footer"]):
            t.decompose()
        return re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    except Exception as e:  # noqa: BLE001
        return f"(fetch failed: {e})"


# ---------------------------------------------------------------- sources --

def consulting_with_canadians(cfg: dict) -> list[dict]:
    """Privy Council Office open-data CSV. Status: O=open, P=planned, C=completed."""
    r = requests.get(cfg["csv"], headers=UA, timeout=60)
    r.raise_for_status()
    rows = csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))
    out = []
    for row in rows:
        if row.get("status") not in ("O", "P"):
            continue
        blob = " ".join([row.get("title_en", ""), row.get("title_fr", ""), row.get("description_en", ""),
                         row.get("description_fr", ""), row.get("subjects", "")])
        if not relevant(blob):
            continue
        out.append({
            "id": f"cwc-{row['registration_number']}",
            "source": "consulting_with_canadians",
            "body": row.get("owner_org_title", ""),
            "url": row.get("profile_page_en") or cfg["portal"],
            "title": row.get("title_en") or row.get("title_fr"),
            "title_fr": row.get("title_fr"),
            "text": blob,
            "opened": row.get("start_date") or None,
            "closes": row.get("end_date") or None,
        })
    return out


def rss(cfg: dict) -> list[dict]:
    """Generic RSS/Atom source (Canada Gazette Part I, department news feeds)."""
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


def html_index(cfg: dict) -> list[dict]:
    """Scrape an HTML index page for links matching a selector (committee study lists,
    OPC consultations page, ISED consultations page, SCC notices)."""
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


FETCHERS = {"consulting_with_canadians": consulting_with_canadians, "rss": rss, "html_index": html_index}


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
