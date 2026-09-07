"""The fork scaffold. Runs `pipeline.fork` on a copy of this checkout's data
directory, then builds the site from that copy in a subprocess (config is read at
import time, so a fresh interpreter is the only clean way to load another site.yaml).
Proves that a fork with a different place, a different second language, or no second
language at all, builds without touching Python."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from pipeline import fork
from tests.conftest import ROOT

ARGS = ["--name", "AI Consultation Deadlines Testland", "--place", "Testland", "--level", "provincial",
        "--schema-type", "State", "--url", "https://example.org/testland/", "--repo",
        "https://github.com/example/testland", "--author", "A Tester", "--year", "2027"]


PARENT = yaml.safe_load((ROOT / "data" / "site.yaml").read_text(encoding="utf-8"))
PARENT_NAME, PARENT_PLACE = PARENT["name"], PARENT["jurisdiction"]["name"]


@pytest.fixture
def copy(tmp_path):
    root = tmp_path / "fork"
    (root / "data").mkdir(parents=True)
    for name in ("site.yaml", "items.json", "sources.yaml", "forks.yaml"):
        shutil.copy(ROOT / "data" / name, root / "data" / name)
    (root / "pipeline").mkdir()
    shutil.copytree(ROOT / "pipeline" / "strings", root / "pipeline" / "strings")
    (root / "site").mkdir()
    (root / "site" / "index.html").write_text("stale", encoding="utf-8")
    return root


def _build_with(root: Path, out: Path):
    env = {**os.environ, "MONITOR_SITE_CONFIG": str(root / "data" / "site.yaml")}
    res = subprocess.run([sys.executable, "-m", "pipeline.build", str(root / "data" / "items.json"), str(out)],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    return out


def test_dry_run_writes_nothing(copy):
    before = {p: p.read_bytes() for p in (copy / "data").iterdir()}
    fork.main(ARGS + ["--root", str(copy), "--dry-run", "--languages", "en,fr"])
    assert {p: p.read_bytes() for p in (copy / "data").iterdir()} == before


def test_scaffold_rewrites_identity_and_empties_the_store(copy):
    fork.main(ARGS + ["--root", str(copy), "--languages", "en,fr", "--locale", "en=en-GB"])
    site = yaml.safe_load((copy / "data" / "site.yaml").read_text(encoding="utf-8"))
    assert site["name"] == "AI Consultation Deadlines Testland"
    assert site["slug"] == "ai-consultation-deadlines-testland"
    assert site["url"] == "https://example.org/testland"
    assert site["jurisdiction"] == {"name": "Testland", "level": "provincial", "schema_type": "State"}
    assert site["languages"] == {"primary": "en", "secondary": ["fr"]}
    assert site["locales"] == {"en": "en-GB", "fr": "fr"}
    assert site["author"] == {"name": "A Tester", "url": "https://github.com/example/testland"}
    assert "Testland" in site["text"]["en"]["tagline"] and PARENT_PLACE not in site["text"]["en"]["tagline"]
    assert not site["text"]["fr"], "a secondary block starts empty and falls back, not as an English copy"
    assert site["classifier"]["place"] == "Testland"
    assert site["prefilter_keywords"], "the keyword list is kept for editing, not wiped"
    assert json.loads((copy / "data" / "items.json").read_text()) == []
    forks = yaml.safe_load((copy / "data" / "forks.yaml").read_text(encoding="utf-8"))["forks"]
    assert forks[0]["url"].startswith("https://") and forks[0]["name"] == PARENT_NAME
    sources = yaml.safe_load((copy / "data" / "sources.yaml").read_text(encoding="utf-8"))
    assert not sources.get("sources"), "sources.yaml becomes a commented template"
    assert not list((copy / "site").iterdir()), "the original's rendered site/ is emptied"


def test_scaffolded_site_yaml_keeps_its_documentation(copy):
    fork.main(ARGS + ["--root", str(copy), "--languages", "en,fr"])
    text = (copy / "data" / "site.yaml").read_text(encoding="utf-8")
    for key in ("schema_type", "secondary", "locales", "government_licence", "official_names",
                "prefilter_keywords", "docs/FORKING.md"):
        assert key in text, f"the scaffolded site.yaml no longer explains {key}"
    assert text.count("#") > 40, "the scaffold used to strip every comment"
    assert PARENT_PLACE not in text and "donjguido" not in text


@pytest.mark.parametrize("languages", ["en,fr", "fr,en", "en"])
def test_a_fresh_scaffold_passes_the_config_and_fetch_tests(copy, languages):
    """A fork is born green whatever its language shape: the config and fetcher suites
    run against the scaffolded files before a single hand edit (the deploy workflow
    refuses a red suite). fr,en is the inverted pair a French-primary fork uses."""
    fork.main(ARGS + ["--root", str(copy), "--languages", languages])
    env = {**os.environ, "MONITOR_SITE_CONFIG": str(copy / "data" / "site.yaml")}
    res = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                          "tests/test_config.py", "tests/test_fetch.py"],
                         cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stdout + res.stderr


def test_slug_transliterates_accents():
    assert fork.slugify("Échéances des consultations sur l'IA Québec") == "echeances-des-consultations-sur-l-ia-quebec"
    assert fork.slugify("Straße Zürich") == "strasse-zurich"


def test_a_bilingual_fork_builds_from_an_empty_store(copy, tmp_path):
    fork.main(ARGS + ["--root", str(copy), "--languages", "en,fr"])
    out = _build_with(copy, tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "AI Consultation Deadlines Testland" in html
    footer = html[html.index("<footer"):]
    body_only = html[:html.index("<footer")]
    assert PARENT_PLACE not in body_only and "donjguido" not in body_only
    assert PARENT_NAME in footer, "the original is linked as a sister site"
    assert (out / "feed-fr.xml").exists() and (out / "deadlines-fr.ics").exists()
    assert 'data-lang="fr"' in html
    forks = json.loads((out / "forks.json").read_text(encoding="utf-8"))
    assert forks["self"]["name"] == "AI Consultation Deadlines Testland"
    assert forks["forks"][0]["name"] == PARENT_NAME, "the original is listed as a sibling"


def test_a_monolingual_fork_builds_with_no_toggle_and_no_second_feed(copy, tmp_path):
    fork.main(ARGS + ["--root", str(copy), "--languages", "en"])
    out = _build_with(copy, tmp_path / "site")
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "data-lang=" not in html, "a single-language site has no language toggle"
    assert not (out / "feed-fr.xml").exists() and not (out / "digest-fr.md").exists()
    assert (out / "feed.xml").exists() and (out / "digest.md").exists()
    assert "_fr" not in (out / "llms.txt").read_text(encoding="utf-8")


def test_a_fork_with_a_new_language_needs_only_a_strings_file(copy, tmp_path):
    """German UI strings do not ship; a fork adds pipeline/strings/de.yaml (a copy of
    en.yaml is enough to start) and the build picks the language up from site.yaml."""
    fork.main(ARGS + ["--root", str(copy), "--languages", "en,de"])
    strings_de = ROOT / "pipeline" / "strings" / "de.yaml"
    assert not strings_de.exists(), "this test assumes no German strings file is checked in"
    shutil.copy(ROOT / "pipeline" / "strings" / "en.yaml", strings_de)
    try:
        out = _build_with(copy, tmp_path / "site")
        assert (out / "feed-de.xml").exists() and (out / "deadlines-de.ics").exists()
        assert 'hreflang="de"' in (out / "index.html").read_text(encoding="utf-8")
    finally:
        strings_de.unlink()
