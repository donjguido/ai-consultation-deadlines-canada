"""The site build. Renders a fixed store and the real store into a temp
directory and checks every artefact the workflow deploys. No network."""
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from pipeline import build
from tests.conftest import (
    LANG2, LANGS, PRIMARY, ROOT, SECONDARY, TODAY, needs_second_language, output_name, translated,
)

EXPECTED_FILES = [
    "index.html", "items.json", "feed.json", "llms.txt", "llms-full.txt", "forks.json",
    "robots.txt", "sitemap.xml", ".nojekyll",
    *[output_name("feed", ".xml", x) for x in LANGS],
    *[output_name("deadlines", ".ics", x) for x in LANGS],
    *[output_name("digest", ".md", x) for x in LANGS],
]
PLACEHOLDERS = ["__DESC__", "__SITE_URL__", "__COUNT__", "__BUILT__", "__SLUG__", "__LOCALE__",
                "__PLACE__", "__LICENCE_URL__",
                "<!--__STATS__-->", "<!--__ITEMS__-->", "<!--__JSONLD__-->", "<!--__HEAD_LINKS__-->",
                "<!--__LANG_BUTTONS__-->", "<!--__FORKS__-->", "<!--__ANALYTICS__-->", "/*__DATA__*/", "/*__L__*/", "/*__CONFIG__*/"]


def _build(items, out: Path):
    return build.build_all(items, out, TODAY)


@pytest.fixture
def built(tmp_path, sample_items):
    out = tmp_path / "site"
    records = _build(sample_items, out)
    return out, records


def test_every_artefact_is_written(built):
    out, _ = built
    missing = [f for f in EXPECTED_FILES if not (out / f).exists()]
    assert not missing, f"build did not write: {missing}"


def test_no_template_placeholder_survives(built):
    out, _ = built
    html = (out / "index.html").read_text(encoding="utf-8")
    left = [p for p in PLACEHOLDERS if p in html]
    assert not left, f"unfilled placeholders in index.html: {left}"


def test_i18n_slots_are_filled_server_side(built):
    """Every data-i18n element and attribute carries the primary-language string in the
    HTML itself, so the page reads correctly with JavaScript off."""
    out, _ = built
    html = (out / "index.html").read_text(encoding="utf-8")
    t = build.strings(PRIMARY)
    assert f'<h1 data-i18n="title">{t["text"]["title"]}</h1>' in html
    assert f'<title data-i18n="page_title">{t["text"]["page_title"]}</title>' in html
    assert f'data-i18n-content="title" content="{build.esc(t["text"]["title"])}"' in html
    assert f'data-i18n-placeholder="search_placeholder" placeholder="{build.esc(t["search_placeholder"])}"' in html
    assert 'content="Site name"' not in html and ">Tagline<" not in html


def test_language_toggle_matches_the_configured_languages(built):
    out, _ = built
    html = (out / "index.html").read_text(encoding="utf-8")
    for lang in LANGS:
        assert (f'data-lang="{lang}"' in html) is (len(LANGS) > 1)
        assert f'hreflang="{build.locale(lang).lower()}"' in html
    assert f'<html lang="{build.locale(PRIMARY)}">' in html


def test_every_item_is_rendered_into_the_html(built, sample_items):
    out, _ = built
    html = (out / "index.html").read_text(encoding="utf-8")
    for item in sample_items:
        assert f'id="item-{item.id}"' in html, f"{item.id} missing from index.html"


def test_html_escapes_untrusted_text(built):
    out, _ = built
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    # Embedded JSON must not be able to close the <script> element either.
    start = html.index("const DATA = ")
    line = html[start:html.index(chr(10), start)]
    assert "<" not in line, "build.js_json must escape < inside the embedded JSON"
    assert chr(92) + "u003cscript" in line


def test_embedded_data_matches_items_json(built):
    out, records = built
    api = json.loads((out / "items.json").read_text(encoding="utf-8"))
    assert api == records
    assert {r["id"] for r in api} == {r["id"] for r in records}
    for r in api:
        assert r["status"] in {"open", "retired"}
        assert set(r["badges"]) <= {"new", "open", "closing_soon", "retired"}
        assert "verified" in r


def test_records_sorted_open_first_then_soonest(built):
    _, records = built
    statuses = [r["status"] for r in records]
    assert statuses == sorted(statuses, key=lambda s: 0 if s == "open" else 1)
    open_closes = [r["closes"] for r in records if r["status"] == "open" and r["closes"]]
    assert open_closes == sorted(open_closes)
    undated = [i for i, r in enumerate(records) if r["status"] == "open" and not r["closes"]]
    dated = [i for i, r in enumerate(records) if r["status"] == "open" and r["closes"]]
    assert all(u > d for u in undated for d in dated), "undated open items must come after dated ones"


def test_rss_feeds_are_valid_xml_with_one_entry_per_item(built, sample_items):
    out, _ = built
    for lang in LANGS:
        name = output_name("feed", ".xml", lang)
        root = ET.parse(out / name).getroot()
        channel = root.find("channel")
        assert channel is not None, f"{name} has no channel"
        assert channel.findtext("language") == build.locale(lang).lower()
        entries = channel.findall("item")
        assert len(entries) == len(sample_items), f"{name}: {len(entries)} entries for {len(sample_items)} items"
        for e in entries:
            assert e.findtext("title") and e.findtext("link", "").startswith("https://")


@needs_second_language
def test_translated_feed_uses_translations_and_falls_back(built):
    out, _ = built
    fr = (out / output_name("feed", ".xml", LANG2)).read_text(encoding="utf-8")
    assert translated("title") in fr
    assert "Test consultation" in fr, "untranslated item should fall back to the primary language"


def test_json_feed_is_valid(built, sample_items):
    out, _ = built
    feed = json.loads((out / "feed.json").read_text(encoding="utf-8"))
    assert feed["version"].startswith("https://jsonfeed.org/version/1")
    assert feed["language"] == build.locale(PRIMARY)
    assert len(feed["items"]) == len(sample_items)
    for it in feed["items"]:
        assert it["id"] and it["url"].startswith("https://") and it["title"]


def test_digests_mention_open_items(built):
    out, _ = built
    en = (out / output_name("digest", ".md", PRIMARY)).read_text(encoding="utf-8")
    assert "closing-soon" in en or "Test consultation" in en
    assert build.strings(PRIMARY)["text"]["title"] in en


@needs_second_language
def test_translated_digest_differs_from_the_primary(built):
    out, _ = built
    en = (out / output_name("digest", ".md", PRIMARY)).read_text(encoding="utf-8")
    fr = (out / output_name("digest", ".md", LANG2)).read_text(encoding="utf-8")
    assert translated("title") in fr
    assert en != fr


def test_sitemap_and_robots(built):
    out, _ = built
    root = ET.parse(out / "sitemap.xml").getroot()
    locs = [el.text or "" for el in root.iter() if el.tag.endswith("loc")]
    assert locs and all(l.startswith(build.SITE_URL) for l in locs)
    for lang in SECONDARY:
        assert f"{build.SITE_URL}/?lang={lang}" in locs
    robots = (out / "robots.txt").read_text(encoding="utf-8")
    assert f"Sitemap: {build.SITE_URL}/sitemap.xml" in robots
    assert "User-agent: *\nAllow: /" in robots
    assert "Disallow" not in robots, "crawling is meant to be explicitly permitted"


def test_llms_files_list_every_item(built, sample_items):
    out, _ = built
    full = (out / "llms-full.txt").read_text(encoding="utf-8")
    for item in sample_items:
        assert item.url in full, f"{item.id} missing from llms-full.txt"
    llms = (out / "llms.txt").read_text(encoding="utf-8")
    assert llms.strip()
    assert f"{build.SITE_URL}/forks.json" in llms


def test_forks_json_describes_this_site_and_its_siblings(built):
    out, _ = built
    data = json.loads((out / "forks.json").read_text(encoding="utf-8"))
    assert data["self"]["url"] == build.SITE_URL
    assert data["self"]["languages"] == LANGS
    assert isinstance(data["forks"], list)
    for f in data["forks"]:
        assert f["name"] and f["url"].startswith("https://")


def test_jsonld_names_the_jurisdiction_and_languages(built):
    out, _ = built
    html = (out / "index.html").read_text(encoding="utf-8")
    start = html.index('<script type="application/ld+json">') + len('<script type="application/ld+json">')
    graph = json.loads(html[start:html.index("</script>", start)])["@graph"]
    dataset = next(g for g in graph if g["@type"] == "Dataset")
    assert dataset["spatialCoverage"]["name"] == build.SITE["jurisdiction"]["name"]
    assert dataset["inLanguage"] == [build.locale(x) for x in LANGS]
    assert dataset["license"] == build.SITE["licence"]["data_url"]


def test_analytics_tag_only_when_an_endpoint_is_configured(tmp_path, sample_items, monkeypatch):
    """An empty analytics block loads no third-party script at all; a configured
    endpoint renders the counter tag and tells the client script to send events."""
    monkeypatch.setitem(build.SITE, "analytics", {"goatcounter": ""})
    _build(sample_items, tmp_path / "off")
    html = (tmp_path / "off" / "index.html").read_text(encoding="utf-8")
    assert "gc.zgo.at" not in html and "data-goatcounter" not in html
    assert '"analytics": false' in html

    monkeypatch.setitem(build.SITE, "analytics", {"goatcounter": "https://example.goatcounter.com/count"})
    _build(sample_items, tmp_path / "on")
    html = (tmp_path / "on" / "index.html").read_text(encoding="utf-8")
    assert '<script data-goatcounter="https://example.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>' in html
    assert '"analytics": true' in html


def test_real_store_builds_cleanly(tmp_path):
    """The actual data/items.json renders without error and every id lands in the HTML."""
    items = build.load_items(str(ROOT / "data" / "items.json"))
    out = tmp_path / "site"
    records = _build(items, out)
    html = (out / "index.html").read_text(encoding="utf-8")
    assert len(records) == len(items)
    for item in items:
        assert f'id="item-{item.id}"' in html
    assert not [p for p in PLACEHOLDERS if p in html]
    for lang in LANGS:
        ET.parse(out / output_name("feed", ".xml", lang))
    json.loads((out / "feed.json").read_text(encoding="utf-8"))


def test_cli_entrypoint_runs(tmp_path, sample_store):
    """`python -m pipeline.build` is what the workflow calls; make sure it still runs."""
    out = tmp_path / "cli-site"
    res = subprocess.run(
        [sys.executable, "-m", "pipeline.build", str(sample_store), str(out)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, res.stderr
    assert (out / "index.html").exists()
    assert "built" in res.stdout


def test_dates_follow_the_language_date_style():
    """The first paint uses the same format the client formatter would produce, so a
    language with `date_style: long` is not served ISO dates until JavaScript runs."""
    from pipeline.build import fmt_date
    from pipeline.config import LANGS, strings
    for lang in LANGS:
        out = fmt_date("2026-12-05", lang)
        if strings(lang).get("date_style") == "long":
            assert out != "2026-12-05" and "2026" in out and strings(lang)["months_short"][11] in out
        else:
            assert out == "2026-12-05"
    assert fmt_date(None, LANGS[0]) == ""
