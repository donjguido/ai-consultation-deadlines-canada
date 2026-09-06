"""Cost invariants for the classifier. It is never called here (no API key);
this only guards the constants the pilot budget was priced on, and that the
prompt is built from site.yaml rather than carrying a place of its own."""
import inspect
import re

from pipeline import classify
from pipeline.config import SECONDARY, SITE, strings, translated_fields
from pipeline.models import Classification


def test_model_and_effort_are_the_budgeted_ones():
    assert classify.MODEL == "claude-opus-5"
    src = inspect.getsource(classify.classify_one)
    assert '"effort": "low"' in src, "classifier effort must stay low (see CLAUDE.md)"


def test_max_tokens_is_not_raised_casually():
    src = inspect.getsource(classify.classify_one)
    m = re.search(r"max_tokens=(\d+)", src)
    assert m and int(m.group(1)) <= 1500


def test_topics_is_a_closed_list_of_slugs():
    assert len(classify.TOPICS) == len(set(classify.TOPICS))
    assert all(t == t.lower() and " " not in t for t in classify.TOPICS)
    assert "privacy" in classify.TOPICS


def test_classification_produces_every_field_the_site_renders():
    for f in ("summary", "why_it_matters", "how_to_participate", "topics", "type", "relevance"):
        assert f in Classification.model_fields
    for lang in SECONDARY:
        for f in translated_fields(lang):
            assert f in Classification.model_fields, f"{f} missing from Classification"


def test_prompt_names_the_configured_place_and_languages():
    place = SITE["classifier"].get("place") or SITE["jurisdiction"]["name"]
    assert place in classify.SYSTEM
    assert "in Canada" not in classify.build_system_prompt({**SITE, "classifier": {"place": "Elsewhere"},
                                                            "jurisdiction": {"name": "Elsewhere", "level": "x"}})
    for lang in SECONDARY:
        name = strings(lang).get("language_name_en", lang)
        assert name in classify.SYSTEM
        assert f"summary_{lang}" in classify.SYSTEM
    for t in classify.TOPICS:
        assert t in classify.SYSTEM
