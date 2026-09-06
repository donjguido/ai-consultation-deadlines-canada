"""MCP server for the Canadian AI Governance Monitor.

A thin, read-only Model Context Protocol server so that AI assistants can
answer questions like "what AI consultations are open in Canada right now?"
from the monitor's canonical data instead of guessing.

Data source
-----------
By default the server reads the public JSON API published by the site
(``items.json`` on GitHub Pages), cached in memory for a few minutes. Set
``MONITOR_ITEMS`` (or pass ``--items``) to a local path or alternate URL to
read a checkout of ``data/items.json`` / ``site/items.json`` instead.

Status (new / open / closing soon / retired) is recomputed at query time from
the rules in ``pipeline/models.py`` so the answer is right even if the site
was last rebuilt a few days ago.

Run
---
    python -m mcp_server                       # stdio (Claude Desktop, Claude Code, etc.)
    python -m mcp_server --http --port 8765    # streamable HTTP at /mcp for remote hosts
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Literal, Optional

import requests
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, Field

# Make ``pipeline.models`` importable whether run from the repo root or installed.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.models import CLOSING_SOON_DAYS, NEW_WINDOW_DAYS, Item  # noqa: E402

SITE_URL = "https://donjguido.github.io/canadian-ai-governance-monitor/"
DEFAULT_ITEMS_URL = SITE_URL + "items.json"
CACHE_TTL_SECONDS = 600

Lang = Literal["en", "fr"]
Status = Literal["new", "open", "closing_soon", "retired", "any"]

# ---------------------------------------------------------------------------
# Data access
# ---------------------------------------------------------------------------


class Store:
    """Loads items from a URL or local file and caches them briefly."""

    def __init__(self, location: str):
        self.location = location
        self._items: list[Item] = []
        self._loaded_at: float = 0.0
        self.fetched_at: Optional[str] = None

    @property
    def is_remote(self) -> bool:
        return self.location.startswith(("http://", "https://"))

    def _read_raw(self) -> list[dict]:
        if self.is_remote:
            resp = requests.get(self.location, timeout=20, headers={"User-Agent": "caigm-mcp/0.1"})
            resp.raise_for_status()
            return resp.json()
        return json.loads(Path(self.location).read_text(encoding="utf-8"))

    def items(self, force: bool = False) -> list[Item]:
        stale = time.monotonic() - self._loaded_at > CACHE_TTL_SECONDS
        if force or stale or not self._items:
            try:
                raw = self._read_raw()
            except Exception as exc:  # network or file error
                if self._items:
                    return self._items  # serve the last good copy
                raise ToolError(f"Could not load monitor data from {self.location}: {exc}") from exc
            # ``Item`` ignores the derived fields (status, badges, days_left) the site adds.
            self._items = [Item.model_validate(r) for r in raw]
            self._loaded_at = time.monotonic()
            self.fetched_at = date.today().isoformat()
        return self._items


STORE = Store(os.environ.get("MONITOR_ITEMS", DEFAULT_ITEMS_URL))

# ---------------------------------------------------------------------------
# Output models
# ---------------------------------------------------------------------------


class ItemSummary(BaseModel):
    """Compact record for list results."""

    id: str
    title: str
    body: str = Field(description="Department, committee, or agency")
    type: str
    status: str = Field(description="new | open | closing_soon | retired (a new item that is also closing soon reports closing_soon)")
    badges: list[str]
    opened: Optional[date] = None
    closes: Optional[date] = None
    days_left: Optional[int] = Field(default=None, description="Days until it closes; null if no closing date or retired")
    url: str
    topics: list[str]
    verified: bool = Field(description="True only if a human curator has checked the dates and link")


class ItemDetail(ItemSummary):
    """Full record for a single item."""

    summary: str
    why_it_matters: str
    how_to_participate: str
    first_seen: date
    relevance: float
    source: str
    retired_reason: Optional[str] = None


class TopicCount(BaseModel):
    topic: str
    open_items: int
    total_items: int


class MonitorStatus(BaseModel):
    site: str
    data_source: str
    data_fetched_on: Optional[str]
    today: date
    counts: dict[str, int]
    verified_open_items: int
    rules: dict[str, int]
    note: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pick(item: Item, field: str, lang: Lang) -> str:
    if lang == "fr":
        fr = getattr(item, f"{field}_fr", None)
        if fr:
            return fr
    return getattr(item, field)


def _status_of(item: Item, today: date) -> str:
    badges = item.badges(today)
    if "retired" in badges:
        return "retired"
    if "closing_soon" in badges:
        return "closing_soon"
    if "new" in badges:
        return "new"
    return "open"


def _summary(item: Item, today: date, lang: Lang) -> ItemSummary:
    is_open = item.status(today) == "open"
    return ItemSummary(
        id=item.id,
        title=_pick(item, "title", lang),
        body=_pick(item, "body", lang),
        type=item.type.value,
        status=_status_of(item, today),
        badges=item.badges(today),
        opened=item.opened,
        closes=item.closes,
        days_left=(item.closes - today).days if item.closes and is_open else None,
        url=item.url,
        topics=item.topics,
        verified=item.verified,
    )


def _detail(item: Item, today: date, lang: Lang) -> ItemDetail:
    base = _summary(item, today, lang).model_dump()
    return ItemDetail(
        **base,
        summary=_pick(item, "summary", lang),
        why_it_matters=_pick(item, "why_it_matters", lang),
        how_to_participate=_pick(item, "how_to_participate", lang),
        first_seen=item.first_seen,
        relevance=item.relevance,
        source=item.source,
        retired_reason=item.retired_reason,
    )


def _sort_key(item: Item):
    # Soonest closing first; undated items after dated ones.
    return (item.closes is None, item.closes or date.max, item.title)


def _filter(
    items: list[Item],
    today: date,
    *,
    status: Status = "any",
    type: Optional[str] = None,
    topic: Optional[str] = None,
    body: Optional[str] = None,
    include_retired: bool = False,
) -> list[Item]:
    out = []
    for it in items:
        st = _status_of(it, today)
        if status == "any":
            if st == "retired" and not include_retired:
                continue
        elif status == "open":
            if it.status(today) != "open":
                continue
        elif st != status:
            continue
        if type and it.type.value != type:
            continue
        if topic and topic.lower() not in [t.lower() for t in it.topics]:
            continue
        if body and body.lower() not in (it.body + " " + (it.body_fr or "")).lower():
            continue
        out.append(it)
    return sorted(out, key=_sort_key)


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = MCPServer(
    "Canadian AI Governance Monitor",
    instructions=(
        "Read-only access to the Canadian AI Governance Monitor: every federal channel "
        "through which Canadians can shape AI governance (consultations, parliamentary "
        "calls for briefs, Canada Gazette comment periods, funding calls, standards "
        "reviews, e-petitions). Start with list_open or closing_soon for what is "
        "actionable now; use get_item for the summary, why it matters, and how to "
        "participate; use search for keyword or topic lookups. Items with verified=false "
        "have been machine-classified but not yet checked by a human curator, so confirm "
        "dates against the linked source page before relying on them. Data is refreshed "
        "on Mondays and Thursdays."
    ),
)


@mcp.tool()
def list_open(
    type: Optional[str] = None,
    topic: Optional[str] = None,
    lang: Lang = "en",
    limit: int = 50,
) -> list[ItemSummary]:
    """List every currently open channel for participation, soonest closing first.

    Args:
        type: Optional filter: consultation, call_for_briefs, gazette_notice,
            funding_call, standards_review, petition, other.
        topic: Optional topic tag filter (see list_topics).
        lang: "en" or "fr" for titles and body names.
        limit: Maximum number of items to return.
    """
    today = date.today()
    items = _filter(STORE.items(), today, status="open", type=type, topic=topic)
    return [_summary(i, today, lang) for i in items[:limit]]


@mcp.tool()
def closing_soon(days: int = CLOSING_SOON_DAYS, lang: Lang = "en") -> list[ItemSummary]:
    """List open items whose closing date falls within the next N days (default 7, the
    monitor's own "closing soon" window), soonest first."""
    today = date.today()
    horizon = today + timedelta(days=days)
    items = [
        i for i in _filter(STORE.items(), today, status="open")
        if i.closes is not None and today <= i.closes <= horizon
    ]
    return [_summary(i, today, lang) for i in items]


@mcp.tool()
def list_new(lang: Lang = "en") -> list[ItemSummary]:
    """List items the monitor first saw (or that opened) within the last 14 days."""
    today = date.today()
    items = [i for i in _filter(STORE.items(), today, status="open") if i.is_new(today)]
    return [_summary(i, today, lang) for i in items]


@mcp.tool()
def search(
    query: str,
    include_retired: bool = False,
    lang: Lang = "en",
    limit: int = 25,
) -> list[ItemSummary]:
    """Keyword search across titles, summaries, bodies, and topic tags in both languages.

    All words in the query must appear somewhere in the item. Retired (closed) items
    are excluded unless include_retired is true.
    """
    words = [w.lower() for w in query.split() if w.strip()]
    if not words:
        raise ToolError("query must contain at least one word")
    today = date.today()
    hits = []
    for it in _filter(STORE.items(), today, include_retired=include_retired):
        haystack = " ".join(
            filter(None, [
                it.id, it.title, it.title_fr, it.body, it.body_fr, it.summary, it.summary_fr,
                it.why_it_matters, it.why_it_matters_fr, it.how_to_participate,
                it.how_to_participate_fr, it.type.value, " ".join(it.topics),
            ])
        ).lower()
        if all(w in haystack for w in words):
            hits.append(it)
    return [_summary(i, today, lang) for i in hits[:limit]]


@mcp.tool()
def get_item(id: str, lang: Lang = "en") -> ItemDetail:
    """Get the full record for one item by id: summary, why it matters, how to participate,
    dates, source link, and verification flag."""
    today = date.today()
    for it in STORE.items():
        if it.id == id:
            return _detail(it, today, lang)
    raise ToolError(f"No item with id {id!r}. Use search or list_open to find ids.")


@mcp.tool()
def list_topics() -> list[TopicCount]:
    """List the topic tags in use, with how many open and total items carry each."""
    today = date.today()
    counts: dict[str, list[int]] = {}
    for it in STORE.items():
        for t in it.topics:
            c = counts.setdefault(t, [0, 0])
            c[1] += 1
            if it.status(today) == "open":
                c[0] += 1
    return [
        TopicCount(topic=t, open_items=c[0], total_items=c[1])
        for t, c in sorted(counts.items(), key=lambda kv: (-kv[1][0], -kv[1][1], kv[0]))
    ]


@mcp.tool()
def monitor_status() -> MonitorStatus:
    """Counts by status, where the data came from, when it was fetched, and the status rules."""
    today = date.today()
    items = STORE.items()
    counts = {s: 0 for s in ["new", "open", "closing_soon", "retired"]}
    for it in items:
        for b in it.badges(today):
            counts[b] += 1
    return MonitorStatus(
        site=SITE_URL,
        data_source=STORE.location,
        data_fetched_on=STORE.fetched_at,
        today=today,
        counts=counts,
        verified_open_items=sum(1 for i in items if i.verified and i.status(today) == "open"),
        rules={"new_window_days": NEW_WINDOW_DAYS, "closing_soon_days": CLOSING_SOON_DAYS},
        note=(
            "Status counts overlap: an item can be both new and open. The store is curated "
            "every Monday and Thursday; verified=true means a human checked the item."
        ),
    )


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


@mcp.resource("monitor://items", mime_type="application/json")
def items_resource() -> str:
    """Every item in the monitor, with status recomputed for today, as JSON."""
    today = date.today()
    return json.dumps(
        [_detail(i, today, "en").model_dump(mode="json") for i in sorted(STORE.items(), key=_sort_key)],
        ensure_ascii=False,
        indent=2,
    )


@mcp.resource("monitor://items/{id}", mime_type="application/json")
def item_resource(id: str) -> str:
    """One item by id, as JSON."""
    return json.dumps(get_item(id).model_dump(mode="json"), ensure_ascii=False, indent=2)


def _digest(filename: str) -> str:
    if STORE.is_remote:
        resp = requests.get(SITE_URL + filename, timeout=20, headers={"User-Agent": "caigm-mcp/0.1"})
        resp.raise_for_status()
        return resp.text
    local = Path(STORE.location).resolve().parent / filename
    if not local.exists():
        local = REPO_ROOT / "site" / filename
    if not local.exists():
        raise ToolError(f"No {filename} found next to the local items file; run pipeline.build first.")
    return local.read_text(encoding="utf-8")


@mcp.resource("monitor://digest", mime_type="text/markdown")
def digest_resource() -> str:
    """The latest weekly digest (Markdown, English) as published on the site."""
    return _digest("digest.md")


@mcp.resource("monitor://digest-fr", mime_type="text/markdown")
def digest_fr_resource() -> str:
    """The latest weekly digest in French (Markdown) as published on the site."""
    return _digest("digest-fr.md")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m mcp_server", description=__doc__.split("\n\n")[0])
    parser.add_argument("--items", help="Local path or URL of items.json (default: the live site, or $MONITOR_ITEMS)")
    parser.add_argument("--http", action="store_true", help="Serve streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    if args.items:
        STORE.location = args.items
        STORE._items = []

    if args.http:
        mcp.run(transport="streamable-http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
