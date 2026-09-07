"""data/items.json is the single source of truth. Every downstream artefact
loads it through the Item model, so a record that fails here would break the
site, the feeds and the MCP server at once. Run before every commit that touches it."""
import json
import re
from collections import Counter

import yaml

from pipeline.build import load_items
from pipeline.classify import TOPICS
from pipeline.fetch import FETCHERS
from pipeline.models import Item
from pipeline.config import SECONDARY, translated_fields
from tests.conftest import DATA

RETIRED_REASONS = {"closed", "withdrawn", "superseded"}
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _items():
    return load_items(str(DATA / "items.json"))


def test_store_is_a_json_list_that_validates():
    raw = json.loads((DATA / "items.json").read_text(encoding="utf-8"))
    assert isinstance(raw, list), "store must be a JSON list (empty is fine for a fresh fork)"
    assert len(_items()) == len(raw)


def test_ids_are_unique_slugs():
    items = _items()
    dupes = [k for k, n in Counter(i.id for i in items).items() if n > 1]
    assert not dupes, f"duplicate ids: {dupes}"
    bad = [i.id for i in items if not SLUG.match(i.id)]
    assert not bad, f"ids must be lowercase slugs: {bad}"


def test_urls_are_absolute_https():
    bad = [i.id for i in _items() if not i.url.startswith("https://")]
    assert not bad, f"non-https urls: {bad}"


def test_topics_come_from_the_closed_list():
    unknown = sorted({(i.id, t) for i in _items() for t in i.topics if t not in TOPICS})
    assert not unknown, f"topics not in classify.TOPICS: {unknown}"


def test_retired_items_carry_a_known_reason():
    bad = [(i.id, i.retired_reason) for i in _items() if i.retired and i.retired_reason not in RETIRED_REASONS]
    assert not bad, f"retired items need retired_reason in {sorted(RETIRED_REASONS)}: {bad}"


def test_dates_are_consistent():
    bad = [i.id for i in _items() if i.opened and i.closes and i.closes < i.opened]
    assert not bad, f"closes before opened: {bad}"


def test_required_prose_is_present():
    empty = [i.id for i in _items()
             if not i.title.strip() or not i.summary.strip() or not i.why_it_matters.strip()]
    assert not empty, f"blank title/summary/why_it_matters: {empty}"


def test_translated_fields_stay_on_the_model():
    # Missing translations are allowed (the site falls back per field), but the
    # fields themselves must exist for every configured secondary language.
    for lang in SECONDARY:
        for f in translated_fields(lang):
            assert f in Item.model_fields, f"{f} missing from Item for language {lang}"


def test_store_carries_no_field_for_an_unconfigured_language():
    """A record with title_de in a site that lists only fr is a sign the language
    list and the data have drifted apart."""
    raw = json.loads((DATA / "items.json").read_text(encoding="utf-8"))
    allowed = set(Item.model_fields)
    stray = sorted({k for r in raw for k in r if k not in allowed})
    assert not stray, f"fields not on the model: {stray}"


def test_sources_yaml_parses_and_has_unique_keys():
    cfg = yaml.safe_load((DATA / "sources.yaml").read_text(encoding="utf-8"))
    sources = cfg["sources"] or []
    keys = [s["key"] for s in sources]
    assert len(keys) == len(set(keys)), "duplicate source keys"
    for s in sources:
        assert s.get("kind") in FETCHERS, f"source {s['key']} has unknown kind {s.get('kind')!r}"
        assert s.get("body"), f"source {s['key']} has no body"
        if s["kind"] in ("csv", "json_api"):
            cols = s.get("columns") or {}
            assert cols.get("title"), f"{s['key']}: columns need at least title"
            assert cols.get("url") or s.get("url_template") or s.get("portal"), (
                f"{s['key']}: needs columns.url, or url_template / portal on the source")
