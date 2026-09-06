"""Site configuration: the one place geography and identity come from.

Reads data/site.yaml (override the path with MONITOR_SITE_CONFIG) and the per-language
UI strings in pipeline/strings/<lang>.yaml. Every other module -- models, fetch,
classify, build, triage, the MCP server and the tests -- asks this module rather than
carrying its own copy of the site name, URL, language list or licence.

A fork edits data/site.yaml (or runs `python -m pipeline.fork`) and nothing here.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
STRINGS_DIR = Path(__file__).parent / "strings"
SITE_FILE = Path(os.environ.get("MONITOR_SITE_CONFIG") or ROOT / "data" / "site.yaml")

# Prose fields that carry a translation per secondary language, as <field>_<lang>.
TRANSLATED_FIELDS = ("title", "body", "summary", "why_it_matters", "how_to_participate")

# Keys every `text:` block in site.yaml must define (for the primary language at least).
TEXT_KEYS = (
    "title", "page_title", "tagline", "description", "channels", "audience", "cadence",
    "calendar_description", "dataset_name",
)


def load_site(path: Path = SITE_FILE) -> dict[str, Any]:
    site = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    langs = site.setdefault("languages", {})
    langs.setdefault("primary", "en")
    langs["secondary"] = list(langs.get("secondary") or [])
    site["url"] = site["url"].rstrip("/")
    site.setdefault("locales", {})
    site.setdefault("keywords", [])
    site.setdefault("prefilter_keywords", [])
    site.setdefault("classifier", {})
    site.setdefault("licence", {})
    site.setdefault("author", {})
    site.setdefault("text", {})
    site["_path"] = str(path)
    return site


SITE: dict[str, Any] = load_site()
PRIMARY: str = SITE["languages"]["primary"]
SECONDARY: list[str] = SITE["languages"]["secondary"]
LANGS: list[str] = [PRIMARY, *SECONDARY]
SITE_URL: str = SITE["url"]
SLUG: str = SITE["slug"]
NAME: str = SITE["name"]
REPO: str = SITE.get("repo", "")
FORKS_FILE = Path(SITE["_path"]).parent / "forks.yaml"


def locale(lang: str) -> str:
    """BCP 47 tag for a language code; falls back to the bare code."""
    return SITE["locales"].get(lang, lang)


def suffix(lang: str) -> str:
    """Field suffix for a language: '' for the primary, '_fr' for a secondary."""
    return "" if lang == PRIMARY else f"_{lang}"


def field(base: str, lang: str) -> str:
    return base + suffix(lang)


def translated_fields(lang: str) -> list[str]:
    return [field(b, lang) for b in TRANSLATED_FIELDS]


def pick(rec: Any, base: str, lang: str) -> Any:
    """The value of a translatable field in `lang`, falling back to the primary language.
    Works on Item objects and on plain dicts."""
    get = rec.get if isinstance(rec, dict) else (lambda k, d=None: getattr(rec, k, d))
    if lang != PRIMARY:
        v = get(field(base, lang))
        if v:
            return v
    return get(base)


def output_name(stem: str, ext: str, lang: str) -> str:
    """feed.xml for the primary language, feed-fr.xml for a secondary one."""
    return f"{stem}{ext}" if lang == PRIMARY else f"{stem}-{lang}{ext}"


@lru_cache(maxsize=None)
def strings(lang: str) -> dict[str, Any]:
    """UI strings for a language, merged with the site's own prose for it.

    Missing site text falls back to the primary language, so a fork that has not yet
    translated its tagline gets a readable (if half-translated) page, not a blank."""
    path = STRINGS_DIR / f"{lang}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No UI strings for language {lang!r}: add {path.relative_to(ROOT)} (copy en.yaml)"
        )
    ui = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    text = dict(SITE["text"].get(PRIMARY) or {})
    text.update(SITE["text"].get(lang) or {})
    return {**ui, "text": text}


def plural(t: dict[str, Any], key: str, n: int, **kw: Any) -> str:
    """Pick the zero/one/other form of a string by count and fill its placeholders."""
    forms = t[key]
    if isinstance(forms, str):
        return forms.format(n=n, **kw)
    form = forms.get("zero") if n == 0 and "zero" in forms else forms.get("one") if n == 1 else forms["other"]
    return (form or forms["other"]).format(n=n, **kw)


def load_forks() -> list[dict[str, Any]]:
    """Sister sites from data/forks.yaml, or an empty list if the file is absent."""
    if not FORKS_FILE.exists():
        return []
    data = yaml.safe_load(FORKS_FILE.read_text(encoding="utf-8")) or {}
    return list(data.get("forks") or [])


def self_entry() -> dict[str, Any]:
    """This site described the way forks.yaml describes the others."""
    return {
        "name": NAME,
        "jurisdiction": SITE["jurisdiction"]["name"],
        "url": SITE_URL,
        "repo": REPO,
        "languages": LANGS,
    }
