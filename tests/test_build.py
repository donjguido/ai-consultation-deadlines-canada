"""The site build. Renders a fixed store and the real store into a temp
directory and checks every artefact the workflow deploys. No network."""
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from pipeline import build
from tests.conftest import ROOT, TODAY

EXPECTED_FILES = [
    "index.html", "items.json", "feed.xml", "feed-fr.xml", "feed.json",
    "digest.md", "digest-fr.md", "llms.txt", "llms-full.txt",
    "robots.txt", "sitemap.xml", ".nojekyll",
]
PLACEHOLDERS = ["__DESC__", "__SITE_URL__", "__COUNT__", "__BUILT__",
                "<!--__STATS__-->", "<!--__ITEMS__-->", "<!--__JSONLD__-->", "/*__DATA__*/"]


def _build(items, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    records = build.build_site(items, out, TODAY)
    for lang in ("en", "fr"):
        build.build_feed(items, out, TODAY, lang)
        build.build_digest(items, out, TODAY, lang)
    build.build_json_feed(records, out, TODAY)
    build.build_llms(records, out, TODAY)
    build.build_llms_full(records, out, TODAY)
    build.build_robots(out)
    build.build_sitemap(out, TODAY)
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return records


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
    for name in ("feed.xml", "feed-fr.xml"):
        root = ET.parse(out / name).getroot()
        channel = root.find("channel")
        assert channel is not None, f"{name} has no channel"
        entries = channel.findall("item")
        assert len(entries) == len(sample_items), f"{name}: {len(entries)} entries for {len(sample_items)} items"
        for e in entries:
            assert e.findtext("title") and e.findtext("link", "").startswith("https://")
    fr = (out / "feed-fr.xml").read_text(encoding="utf-8")
    assert "Consultation de test" in fr
    assert "Test consultation" in fr, "untranslated item should fall back to English in the French feed"


def test_json_feed_is_valid(built, sample_items):
    out, _ = built
    feed = json.loads((out / "feed.json").read_text(encoding="utf-8"))
    assert feed["version"].startswith("https://jsonfeed.org/version/1")
    assert len(feed["items"]) == len(sample_items)
    for it in feed["items"]:
        assert it["id"] and it["url"].startswith("https://") and it["title"]


def test_digests_mention_open_items_and_are_bilingual(built):
    out, _ = built
    en = (out / "digest.md").read_text(encoding="utf-8")
    fr = (out / "digest-fr.md").read_text(encoding="utf-8")
    assert "closing-soon" in en or "Test consultation" in en
    assert "Consultation de test" in fr
    assert en != fr


def test_sitemap_and_robots(built):
    out, _ = built
    root = ET.parse(out / "sitemap.xml").getroot()
    locs = [el.text or "" for el in root.iter() if el.tag.endswith("loc")]
    assert locs and all(l.startswith(build.SITE_URL) for l in locs)
    robots = (out / "robots.txt").read_text(encoding="utf-8")
    assert f"Sitemap: {build.SITE_URL}/sitemap.xml" in robots
    assert "User-agent: *\nAllow: /" in robots
    assert "Disallow" not in robots, "crawling is meant to be explicitly permitted"


def test_llms_files_list_every_item(built, sample_items):
    out, _ = built
    full = (out / "llms-full.txt").read_text(encoding="utf-8")
    for item in sample_items:
        assert item.url in full, f"{item.id} missing from llms-full.txt"
    assert (out / "llms.txt").read_text(encoding="utf-8").strip()


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
    ET.parse(out / "feed.xml")
    ET.parse(out / "feed-fr.xml")
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
