"""Shared fixtures. Everything here is offline: no network, no API key.

The fixtures read the language list from data/site.yaml, so a fork with a different
second language (or none) runs the same suite: translated sample text is generated
for whatever the first secondary language is, and the tests that need one skip
cleanly when there is none."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from pipeline.config import LANGS, PRIMARY, SECONDARY, SITE, SITE_URL, output_name, strings  # noqa: F401
from pipeline.models import Item

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TODAY = date(2026, 9, 7)  # fixed so status tests never drift with the calendar

LANG2 = SECONDARY[0] if SECONDARY else None  # the secondary language the fixtures translate into
needs_second_language = pytest.mark.skipif(LANG2 is None, reason="site has a single language")

_EN = {
    "title": "Test consultation <script>alert(1)</script>",
    "body": "Innovation, Science & Economic Development Canada",
    "summary": 'A "quoted" summary with an ampersand & angle <brackets>.',
    "why_it_matters": "It matters.",
    "how_to_participate": "Email consult@example.gc.ca",
}
_FR = {
    "title": "Consultation de test",
    "body": "Innovation, Sciences et Développement économique Canada",
    "summary": "Un résumé en français.",
    "why_it_matters": "C'est important.",
    "how_to_participate": "Écrire à consult@example.gc.ca",
}


def translated(field: str, lang: str | None = LANG2) -> str:
    """The sample translation make_item writes for a field, so assertions can look
    for it whatever the secondary language is."""
    if lang == "fr":
        return _FR[field]
    return f"{_EN[field].split('<')[0].strip()} [{lang}]"


def make_item(**overrides: Any) -> Item:
    base: dict[str, Any] = dict(
        id="test-item",
        type="consultation",
        url="https://example.gc.ca/consult?a=1&b=2",
        opened=TODAY - timedelta(days=3),
        closes=TODAY + timedelta(days=30),
        first_seen=TODAY - timedelta(days=3),
        topics=["privacy", "standards"],
        relevance=0.9,
        source="ised_consultations",
        verified=False,
        **_EN,
    )
    for lang in SECONDARY:
        for field in _EN:
            base[f"{field}_{lang}"] = translated(field, lang)
    base.update(overrides)
    return Item(**base)


def untranslated(**overrides: Any) -> Item:
    """An item with every translated field blank, for the fallback tests."""
    blanks = {f"{field}_{lang}": None for lang in SECONDARY for field in _EN}
    return make_item(**blanks, **overrides)


@pytest.fixture
def today() -> date:
    return TODAY


@pytest.fixture
def sample_items() -> list[Item]:
    """One item per status, plus edge cases, all relative to TODAY."""
    return [
        make_item(id="brand-new", opened=TODAY - timedelta(days=2), closes=TODAY + timedelta(days=40)),
        make_item(id="plain-open", opened=TODAY - timedelta(days=60), closes=TODAY + timedelta(days=40)),
        make_item(id="closing-soon", opened=TODAY - timedelta(days=60), closes=TODAY + timedelta(days=3)),
        make_item(id="new-and-closing", opened=TODAY - timedelta(days=1), closes=TODAY + timedelta(days=1)),
        make_item(id="no-deadline", opened=TODAY - timedelta(days=60), closes=None),
        make_item(id="expired", opened=TODAY - timedelta(days=90), closes=TODAY - timedelta(days=1)),
        make_item(id="retired-flag", retired=True, retired_reason="withdrawn"),
        untranslated(id="untranslated", verified=True),
    ]


@pytest.fixture
def sample_store(tmp_path: Path, sample_items: list[Item]) -> Path:
    path = tmp_path / "items.json"
    path.write_text(
        json.dumps([json.loads(i.model_dump_json()) for i in sample_items], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def real_store() -> Path:
    return DATA / "items.json"
