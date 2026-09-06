"""Cost invariants for the classifier. It is never called here (no API key);
this only guards the constants the pilot budget was priced on."""
import inspect
import re

from pipeline import classify
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
    for f in ("summary", "summary_fr", "why_it_matters", "why_it_matters_fr",
              "how_to_participate", "how_to_participate_fr", "topics", "type", "relevance"):
        assert f in Classification.model_fields
