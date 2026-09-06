"""The generic fetchers' record mapping, offline. Network fetchers are not called;
this covers the `columns` contract that lets a fork point a csv/json_api source at
a new registry without writing Python."""
from pipeline import fetch
from pipeline.config import SECONDARY

CSV_CFG = {
    "key": "registry", "kind": "csv", "body": "Registry owner", "portal": "https://example.gov/portal",
    "id_prefix": "reg-", "open_statuses": ["O", "P"],
    "columns": {
        "id": "registration_number", "title": "title_en", "url": "profile_page_en",
        "opened": "start_date", "closes": "end_date", "status": "status", "body": "owner_org_title",
        "text": ["title_en", "description_en"],
        **{f"title_{x}": f"title_{x}" for x in SECONDARY},
    },
}


def _row(**over):
    row = {
        "registration_number": "123", "title_en": "Consultation on artificial intelligence rules",
        "profile_page_en": "https://example.gov/c/123", "start_date": "2026-09-01T00:00:00",
        "end_date": "2026-10-01", "status": "O", "owner_org_title": "Ministry",
        "description_en": "About AI.",
    }
    for x in SECONDARY:
        row[f"title_{x}"] = f"Titre {x}"
    row.update(over)
    return row


def test_csv_row_maps_to_a_candidate():
    rec = fetch._record(CSV_CFG, _row())
    assert rec is not None
    assert rec["id"] == "reg-123" and rec["source"] == "registry"
    assert rec["url"] == "https://example.gov/c/123" and rec["body"] == "Ministry"
    assert rec["opened"] == "2026-09-01" and rec["closes"] == "2026-10-01"
    for x in SECONDARY:
        assert rec[f"title_{x}"] == f"Titre {x}"


def test_closed_rows_and_irrelevant_rows_are_dropped():
    assert fetch._record(CSV_CFG, _row(status="C")) is None
    assert fetch._record(CSV_CFG, _row(title_en="Fisheries licence renewal", description_en="Boats.")) is None


def test_missing_id_falls_back_to_a_title_slug_and_missing_url_to_the_portal():
    cfg = {**CSV_CFG, "columns": {**CSV_CFG["columns"], "id": None}}
    rec = fetch._record(cfg, _row(profile_page_en=""))
    assert rec is not None
    assert rec["id"].startswith("reg-consultation-on-artificial")
    assert rec["url"] == "https://example.gov/portal"


def test_json_api_dotted_paths():
    cfg = {
        "key": "api", "kind": "json_api", "body": "API owner", "url": "https://example.gov/api",
        "columns": {"id": "id", "title": "attributes.title", "url": "links.self",
                    "closes": "attributes.closes_on", "text": ["attributes.title", "attributes.summary"]},
    }
    row = {"id": 7, "attributes": {"title": "Automated decision systems review", "closes_on": "2026-11-30",
                                   "summary": "algorithmic accountability"}, "links": {"self": "https://example.gov/7"}}
    rec = fetch._record(cfg, row)
    assert rec is not None and rec["id"] == "api-7" and rec["closes"] == "2026-11-30"
    assert fetch._get(row, "attributes.missing.deeper") is None


def test_every_declared_kind_has_a_fetcher():
    assert set(fetch.FETCHERS) == {"csv", "json_api", "rss", "sitemap", "html_index"}


def test_keyword_filter_comes_from_site_config():
    assert fetch.relevant("intelligence artificielle") or not SECONDARY
    assert fetch.relevant("deepfake") and not fetch.relevant("pothole repair schedule")
