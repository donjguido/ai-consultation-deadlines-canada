"""data/site.yaml and pipeline/strings/*.yaml are what a fork edits. A missing key
there surfaces as a KeyError deep in the build, so validate the shape up front."""
import re

import yaml

from pipeline import config
from pipeline.config import LANGS, PRIMARY, SECONDARY, SITE, STRINGS_DIR, TEXT_KEYS, plural, strings

REQUIRED_TOP = ["name", "slug", "url", "repo", "author", "jurisdiction", "languages", "licence", "text"]
# Keys every strings file must carry: the build, the calendar, the digest and the
# template all index these directly.
REQUIRED_UI = [
    "language_name", "language_name_en", "date_style", "badge", "badge_hint", "type", "topic",
    "closes", "closed", "opened", "no_deadline", "days_left", "why", "how", "empty", "unverified",
    "count", "skip", "at_a_glance", "search_and_filter", "search_label", "search_placeholder",
    "filter_type", "all_types", "filter_body", "all_bodies", "topics_label", "monitored_items",
    "built", "rss", "calendar", "json", "digest", "sister_sites", "footer_status", "footer_credit",
    "add_cal", "ics_one", "deadline_prefix", "cal_unverified", "cal_tracked", "alarm_7", "alarm_1",
    "all_cal", "close", "all_title", "all_intro", "sub_head", "apple_sub", "copy_link", "copied",
    "sub_note", "once_head", "once_note", "download", "cal_fine", "no_dated",
    "week_of", "nothing", "sec_closing", "sec_new", "sec_open", "sec_retired", "full_list",
]


def test_site_yaml_has_the_required_keys():
    missing = [k for k in REQUIRED_TOP if k not in SITE]
    assert not missing, f"data/site.yaml is missing {missing}"
    assert re.match(r"^[a-z0-9][a-z0-9-]*$", SITE["slug"]), "slug must be a lowercase slug"
    assert SITE["url"].startswith("https://") and not SITE["url"].endswith("/")
    assert SITE["repo"].startswith("https://")
    assert SITE["author"].get("name")
    assert SITE["jurisdiction"].get("name")
    assert SITE["licence"].get("data") and SITE["licence"].get("data_url", "").startswith("https://")


def test_languages_are_consistent():
    assert PRIMARY not in SECONDARY
    assert len(LANGS) == len(set(LANGS))
    for lang in LANGS:
        assert re.match(r"^[a-z]{2,3}$", lang), f"language codes are ISO 639 lowercase: {lang!r}"
        assert (STRINGS_DIR / f"{lang}.yaml").exists(), f"no pipeline/strings/{lang}.yaml"
        assert config.locale(lang)


def test_site_text_is_complete_for_the_primary_language():
    text = SITE["text"].get(PRIMARY) or {}
    missing = [k for k in TEXT_KEYS if not text.get(k)]
    assert not missing, f"text.{PRIMARY} is missing {missing}"


def test_site_text_for_secondary_languages_is_not_a_copy_of_the_primary():
    """The build falls back per key, so a missing translation is allowed; an exact copy
    of the primary prose under a secondary language is a scaffold left unfinished."""
    primary = SITE["text"].get(PRIMARY) or {}
    for lang in SECONDARY:
        text = SITE["text"].get(lang) or {}
        same = [k for k in TEXT_KEYS if text.get(k) and text[k] == primary.get(k)]
        assert len(same) < len(TEXT_KEYS) // 2, f"text.{lang} looks untranslated: {same}"


def test_every_strings_file_has_every_ui_key():
    for lang in LANGS:
        raw = yaml.safe_load((STRINGS_DIR / f"{lang}.yaml").read_text(encoding="utf-8"))
        missing = [k for k in REQUIRED_UI if k not in raw]
        assert not missing, f"pipeline/strings/{lang}.yaml is missing {missing}"
        for group in ("badge", "badge_hint"):
            assert set(raw[group]) == {"new", "open", "closing_soon", "retired"}, f"{lang}: {group}"
        assert set(raw["type"]) >= {"consultation", "call_for_briefs", "gazette_notice", "funding_call",
                                    "standards_review", "petition", "other"}, f"{lang}: type labels"
        assert raw["date_style"] in ("iso", "long")


def test_plural_forms_format_cleanly():
    for lang in LANGS:
        t = strings(lang)
        for key in ("days_left", "count", "all_intro", "download"):
            for n in (0, 1, 2):
                out = plural(t, key, n, total=9)
                assert "{" not in out, f"{lang}.{key} left a placeholder unfilled for n={n}: {out}"
        for key in ("alarm_7", "alarm_1"):
            assert "{x}" in t[key], f"{lang}.{key} must carry the {{x}} placeholder for the title"
        assert "{site}" in t["cal_tracked"]
        for ph in ("{year}", "{author}", "{repo}"):
            assert ph in t["footer_credit"], f"{lang}.footer_credit must carry {ph}"


def test_prefilter_keywords_compile():
    import re as _re
    from pipeline.fetch import compile_keywords
    for kw in SITE["prefilter_keywords"]:
        _re.compile(kw)
    joined = compile_keywords(SITE["prefilter_keywords"])
    assert joined and joined.search("a consultation on artificial intelligence")


def test_pick_falls_back_to_the_primary_language():
    rec = {"title": "Primary"}
    for lang in LANGS:
        assert config.pick(rec, "title", lang) == "Primary"
    if SECONDARY:
        rec[f"title_{SECONDARY[0]}"] = "Translated"
        assert config.pick(rec, "title", SECONDARY[0]) == "Translated"
        assert config.pick(rec, "title", PRIMARY) == "Primary"


def test_output_names_follow_the_language():
    assert config.output_name("feed", ".xml", PRIMARY) == "feed.xml"
    for lang in SECONDARY:
        assert config.output_name("feed", ".xml", lang) == f"feed-{lang}.xml"
