"""Shared fixtures. Everything here is offline: no network, no API key."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from pipeline.models import Item

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

TODAY = date(2026, 9, 7)  # fixed so status tests never drift with the calendar


def make_item(**overrides: Any) -> Item:
    base: dict[str, Any] = dict(
        id="test-item",
        title="Test consultation <script>alert(1)</script>",
        title_fr="Consultation de test",
        body="Innovation, Science & Economic Development Canada",
        body_fr="Innovation, Sciences et Développement économique Canada",
        type="consultation",
        url="https://example.gc.ca/consult?a=1&b=2",
        opened=TODAY - timedelta(days=3),
        closes=TODAY + timedelta(days=30),
        first_seen=TODAY - timedelta(days=3),
        summary='A "quoted" summary with an ampersand & angle <brackets>.',
        summary_fr="Un résumé en français.",
        why_it_matters="It matters.",
        why_it_matters_fr="C'est important.",
        how_to_participate="Email consult@example.gc.ca",
        how_to_participate_fr="Écrire à consult@example.gc.ca",
        topics=["privacy", "standards"],
        relevance=0.9,
        source="ised_consultations",
        verified=False,
    )
    base.update(overrides)
    return Item(**base)


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
        make_item(id="untranslated", title_fr=None, summary_fr=None, why_it_matters_fr=None,
                  how_to_participate_fr=None, body_fr=None, verified=True),
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
