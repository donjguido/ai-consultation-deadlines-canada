"""The fortnightly newsletter, offline: the delta against the last snapshot, the facts
rendered from the store, the stock framing, the Buttondown call (injected) and the cost
guard on the one model call. No network, no API key."""
import inspect
import re
from datetime import timedelta

from pipeline import classify, newsletter
from pipeline.config import LANGS, PRIMARY, SITE_URL, field as lang_field, strings
from pipeline.models import Item
from tests.conftest import TODAY, LANG2, needs_second_language


def _item(id_, **kw):
    base = dict(
        id=id_, title=f"Title {id_}", body="Ministry of Example", type="consultation",
        url=f"https://example.gc.ca/{id_}", first_seen=TODAY - timedelta(days=40),
        summary="Summary.", why_it_matters="Matters.", how_to_participate="Email x@example.gc.ca",
        topics=["privacy"], relevance=0.9, source="test",
    )
    base.update(kw)
    return Item(**base)


def _store():
    return [
        _item("brand-new", first_seen=TODAY - timedelta(days=2), closes=TODAY + timedelta(days=40)),
        _item("closing", closes=TODAY + timedelta(days=3)),
        _item("moved", closes=TODAY + timedelta(days=30)),
        _item("steady", closes=TODAY + timedelta(days=60)),
        _item("gone", closes=TODAY - timedelta(days=1)),
        _item("long-gone", closes=TODAY - timedelta(days=90)),
    ]


def _prev():
    """Snapshot from a fortnight ago: 'brand-new' unseen, 'moved' had another date, 'gone' was open."""
    return {
        "closing": {"status": "open", "closes": (TODAY + timedelta(days=3)).isoformat()},
        "moved": {"status": "open", "closes": (TODAY + timedelta(days=20)).isoformat()},
        "steady": {"status": "open", "closes": (TODAY + timedelta(days=60)).isoformat()},
        "gone": {"status": "open", "closes": (TODAY - timedelta(days=1)).isoformat()},
        "long-gone": {"status": "retired", "closes": (TODAY - timedelta(days=90)).isoformat()},
    }


def test_delta_sorts_items_into_the_four_sections():
    d = newsletter.delta(_store(), _prev(), TODAY)
    ids = lambda k: [i.id for i in d[k]]  # noqa: E731
    assert ids("new") == ["brand-new"]
    assert ids("closing") == ["closing"]
    assert ids("moved") == ["moved"]
    assert ids("retired") == ["gone"], "only items that closed since the last issue, not every retired item"
    assert ids("open") == ["steady"]
    assert newsletter.has_news(d)


def test_first_issue_uses_the_new_window_rather_than_dumping_the_store():
    d = newsletter.delta(_store(), None, TODAY)
    assert [i.id for i in d["new"]] == ["brand-new"]
    assert not d["retired"] and not d["moved"]


def test_quiet_fortnight_has_no_news():
    items = [_item("steady", closes=TODAY + timedelta(days=60))]
    prev = newsletter.snapshot(items, TODAY - timedelta(days=14))
    assert not newsletter.has_news(newsletter.delta(items, prev, TODAY))


def test_facts_come_from_the_store_and_carry_every_link():
    d = newsletter.delta(_store(), _prev(), TODAY)
    t = strings(PRIMARY)
    facts = newsletter.render_facts(d, PRIMARY, TODAY)
    for key in ("sec_closing", "sec_new", "sec_moved", "sec_retired"):
        assert f"### {t[key]}" in facts
    for id_ in ("brand-new", "closing", "moved", "gone"):
        assert f"https://example.gc.ca/{id_}" in facts
    assert "https://example.gc.ca/steady" not in facts, "unchanged open items are a count, not a list"
    assert "4 " in facts and SITE_URL in facts
    assert "long-gone" not in facts


@needs_second_language
def test_facts_render_in_the_secondary_language_with_fallback():
    items = _store()
    items[0] = _item("brand-new", first_seen=TODAY - timedelta(days=2), closes=TODAY + timedelta(days=40),
                     **{lang_field("title", LANG2): "Titre traduit"})
    d = newsletter.delta(items, _prev(), TODAY)
    facts = newsletter.render_facts(d, LANG2, TODAY)
    assert "Titre traduit" in facts
    assert "Title closing" in facts, "an untranslated title falls back to the primary language"
    assert f"### {strings(LANG2)['sec_new']}" in facts


def test_stock_framing_and_compose_produce_one_issue_per_language_section():
    d = newsletter.delta(_store(), _prev(), TODAY)
    facts = {x: newsletter.render_facts(d, x, TODAY) for x in LANGS}
    framing = newsletter.fallback_framing(d, TODAY)
    subject, body = newsletter.compose(framing, facts, TODAY)
    for x in LANGS:
        assert strings(x)["text"]["title"] in subject
        assert strings(x)["text"]["title"] in body
    assert body.count("\n---\n") == len(LANGS) - 1
    assert "{" not in subject and "{n}" not in body, "every placeholder was filled"


def test_run_posts_a_draft_by_default_and_updates_state_only_on_success():
    posted = []
    state = {"last_sent": (TODAY - timedelta(days=14)).isoformat(), "items": _prev()}
    outcome, new_state = newsletter.run(_store(), state, TODAY, framing_fn=None, poster=lambda s, b: posted.append((s, b)))
    assert outcome == "posted" and len(posted) == 1
    assert new_state["last_sent"] == TODAY.isoformat()
    assert set(new_state["items"]) == {i.id for i in _store()}
    assert new_state["items"]["gone"]["status"] == "retired"

    calls = []
    newsletter.post_issue("s", "b", "KEY", send=False, post=lambda u, h, p: calls.append((u, h, p)))
    newsletter.post_issue("s", "b", "KEY", send=True, post=lambda u, h, p: calls.append((u, h, p)))
    assert calls[0][0] == newsletter.API_URL
    assert calls[0][1]["Authorization"] == "Token KEY"
    assert calls[0][2]["status"] == "draft" and calls[1][2]["status"] == "about_to_send"


def test_fortnight_guard_and_quiet_run_leave_state_alone():
    recent = {"last_sent": (TODAY - timedelta(days=6)).isoformat(), "items": _prev()}
    assert newsletter.run(_store(), recent, TODAY, framing_fn=None, poster=None)[0] == "skipped"
    assert newsletter.run(_store(), recent, TODAY, framing_fn=None, poster=None, force=True)[0] == "drafted"
    items = [_item("steady", closes=TODAY + timedelta(days=60))]
    quiet = {"last_sent": (TODAY - timedelta(days=20)).isoformat(), "items": newsletter.snapshot(items, TODAY)}
    outcome, st = newsletter.run(items, quiet, TODAY, framing_fn=None, poster=None)
    assert outcome == "nothing" and st is quiet


def test_dry_run_previews_without_posting():
    state = {"items": _prev()}
    outcome, st = newsletter.run(_store(), state, TODAY, framing_fn=None, poster=None)
    assert outcome == "drafted"
    assert st["_preview"].startswith("# ") and "https://example.gc.ca/brand-new" in st["_preview"]


def test_model_call_stays_within_the_classifier_budget():
    """One low-effort call on the same model as the classifier, capped on output tokens."""
    src = inspect.getsource(newsletter.draft_framing)
    assert newsletter.MODEL == classify.MODEL
    assert '"effort": "low"' in src
    assert newsletter.MAX_TOKENS <= 1500
    for x in LANGS:
        assert lang_field("subject", x) in newsletter.Framing.model_fields
        assert lang_field("intro", x) in newsletter.Framing.model_fields


def test_prompt_is_built_from_site_yaml_not_hardcoded():
    prompt = newsletter.build_system_prompt({"classifier": {"place": "Elsewhere"}, "jurisdiction": {"name": "Elsewhere"}})
    assert "Elsewhere" in prompt
    src = inspect.getsource(newsletter)
    assert not re.search(r"\bCanad", src), "pipeline code names no place"
