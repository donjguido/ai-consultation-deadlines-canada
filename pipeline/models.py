"""Canonical data model for a monitored initiative.

One record per intake channel (consultation, call for briefs, gazette notice,
funding call, standards review, petition). The pipeline stores these in
data/items.json; the site, RSS feed, email digest and MCP server all read from
that single file.

Translated prose fields are generated from the language list in data/site.yaml:
for each secondary language <lang>, the model carries title_<lang>, body_<lang>,
summary_<lang>, why_it_matters_<lang> and how_to_participate_<lang>, all optional.
The site, feeds and digest fall back to the primary language per field.
"""
from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field, create_model

from .config import SECONDARY, TRANSLATED_FIELDS, field as lang_field, strings

NEW_WINDOW_DAYS = 14        # "new" = opened (or first seen) within this many days
CLOSING_SOON_DAYS = 7       # "closing soon" = closes within this many days


class ItemType(str, Enum):
    consultation = "consultation"
    call_for_briefs = "call_for_briefs"
    regulatory_notice = "regulatory_notice"
    funding_call = "funding_call"
    standards_review = "standards_review"
    petition = "petition"
    other = "other"


def _lang_name(lang: str) -> str:
    try:
        return strings(lang).get("language_name_en") or strings(lang).get("language_name") or lang
    except FileNotFoundError:
        return lang


class _ItemBase(BaseModel):
    id: str = Field(description="Stable slug, e.g. ised-2026-ai-strategy")
    title: str
    body: str = Field(description="Department, committee, or agency")
    type: ItemType
    url: str
    opened: Optional[date] = None
    closes: Optional[date] = None
    first_seen: date = Field(description="Date the monitor first observed the item")
    summary: str = Field(description="1-2 sentence plain-language summary")
    why_it_matters: str = Field(description="1 sentence on AI-safety relevance")
    how_to_participate: str = Field(default="", description="Concrete next step: email, form, portal")
    topics: list[str] = Field(default_factory=list)
    relevance: float = Field(ge=0, le=1, description="Classifier confidence that this is AI-safety relevant")
    source: str = Field(description="Source key from sources.yaml")
    retired: bool = False
    retired_reason: Optional[str] = None  # closed | withdrawn | superseded
    verified: bool = Field(default=False, description="A human checked dates and links")

    # ---- derived status ------------------------------------------------
    def status(self, today: date | None = None) -> str:
        today = today or date.today()
        if self.retired or (self.closes and self.closes < today):
            return "retired"
        return "open"

    def is_new(self, today: date | None = None) -> bool:
        today = today or date.today()
        anchor = self.opened or self.first_seen
        return self.status(today) == "open" and (today - anchor).days <= NEW_WINDOW_DAYS

    def is_closing_soon(self, today: date | None = None) -> bool:
        today = today or date.today()
        return (
            self.status(today) == "open"
            and self.closes is not None
            and today <= self.closes <= today + timedelta(days=CLOSING_SOON_DAYS)
        )

    def badges(self, today: date | None = None) -> list[str]:
        b = []
        if self.status(today) == "retired":
            return ["retired"]
        if self.is_new(today):
            b.append("new")
        if self.is_closing_soon(today):
            b.append("closing_soon")
        b.append("open")
        return b


def _item_translations() -> dict:
    fields = {}
    for lang in SECONDARY:
        name = _lang_name(lang)
        for base in TRANSLATED_FIELDS:
            fields[lang_field(base, lang)] = (
                Optional[str], Field(default=None, description=f"{name} {base.replace('_', ' ')}"),
            )
    return fields


if TYPE_CHECKING:  # the static view; at runtime the class also carries the translated fields
    class Item(_ItemBase): ...
else:
    Item = create_model("Item", __base__=_ItemBase, **_item_translations())
    Item.__doc__ = "A monitored initiative; see the module docstring."


class _ClassificationBase(BaseModel):
    """What the LLM returns for each candidate item."""
    relevant: bool = Field(description="True if the initiative could shape AI safety or AI governance in the jurisdiction")
    relevance: float = Field(ge=0, le=1)
    type: ItemType
    summary: str
    why_it_matters: str
    how_to_participate: str
    topics: list[str] = Field(description="2-4 tags from the controlled vocabulary")
    closes: Optional[date] = Field(default=None, description="Closing date if stated in the text")


def _classification_translations() -> dict:
    fields = {}
    for lang in SECONDARY:
        name = _lang_name(lang)
        for base in ("summary", "why_it_matters", "how_to_participate"):
            fields[lang_field(base, lang)] = (str, Field(description=f"{name} translation of {base}"))
        fields[lang_field("title", lang)] = (
            Optional[str],
            Field(default=None, description=f"Official {name} title if the source gives one, otherwise a faithful {name} rendering"),
        )
        fields[lang_field("body", lang)] = (
            Optional[str],
            Field(default=None, description=f"Official {name} name of the department, committee, or agency"),
        )
    return fields


if TYPE_CHECKING:
    class Classification(_ClassificationBase): ...
else:
    Classification = create_model("Classification", __base__=_ClassificationBase, **_classification_translations())
