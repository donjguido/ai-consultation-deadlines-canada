"""The weekly engagement snapshot, offline: the lookups are injected and the CSV
grows by one row per run without touching the network."""
from datetime import date

import requests

from pipeline import engagement
from pipeline.config import LANGS, PRIMARY

TODAY = date(2026, 9, 7)


def _resp(status):
    r = requests.Response()
    r.status_code = status
    return r


def test_feedly_counts_per_language_feed_and_treats_unknown_as_zero():
    seen = []

    def get(url, headers):
        seen.append(url)
        if url.endswith("feed.xml"):
            return [{"subscribers": 12}]
        return []

    counts = engagement.feedly_subscribers(get)
    assert counts[PRIMARY] == 12
    assert all(counts[x] == 0 for x in LANGS if x != PRIMARY)
    assert all(u.startswith(engagement.FEEDLY + "feed%2Fhttps%3A%2F%2F") for u in seen)


def test_feedly_404_is_zero_but_unreachable_is_blank():
    def gone(url, headers):
        raise requests.HTTPError(response=_resp(404))
    assert all(v == 0 for v in engagement.feedly_subscribers(gone).values())

    def offline(url, headers):
        raise requests.ConnectionError("offline")
    assert all(v is None for v in engagement.feedly_subscribers(offline).values())


def test_github_traffic_reads_both_endpoints():
    calls = []

    def run(args):
        calls.append(args[0])
        return '{"count": 40, "uniques": 9}' if args[0].endswith("views") else '{"count": 3, "uniques": 2}'

    out = engagement.github_traffic(run)
    assert out == {"gh_views_14d": 40, "gh_views_uniques_14d": 9, "gh_clones_14d": 3, "gh_clones_uniques_14d": 2}
    assert all(c.startswith("repos/") and "/traffic/" in c for c in calls)


def test_goatcounter_is_skipped_without_endpoint_or_token(monkeypatch):
    monkeypatch.setitem(engagement.SITE, "analytics", {"goatcounter": ""})
    monkeypatch.setenv("GOATCOUNTER_TOKEN", "x")
    def get(url, headers):
        raise AssertionError("must not be called")
    assert engagement.goatcounter_totals(TODAY, get) == {"gc_pageviews_7d": None, "gc_events_7d": None}


def test_goatcounter_totals_use_the_endpoint_host_and_a_seven_day_window(monkeypatch):
    monkeypatch.setitem(engagement.SITE, "analytics", {"goatcounter": "https://x.goatcounter.com/count"})
    monkeypatch.setenv("GOATCOUNTER_TOKEN", "tok")
    seen = {}

    def get(url, headers):
        seen.update(url=url, headers=headers)
        return {"total": 150, "total_events": 31}

    assert engagement.goatcounter_totals(TODAY, get) == {"gc_pageviews_7d": 150, "gc_events_7d": 31}
    assert seen["url"] == "https://x.goatcounter.com/api/v0/stats/total?start=2026-08-31&end=2026-09-07"
    assert seen["headers"] == {"Authorization": "Bearer tok"}


def test_csv_gets_a_header_once_and_blanks_for_unreachable(tmp_path):
    out = tmp_path / "engagement.csv"
    row = engagement.snapshot(TODAY, feedly={PRIMARY: 5}, github={"gh_views_14d": None}, goatcounter={"gc_pageviews_7d": 7})
    engagement.append_row(row, out)
    engagement.append_row(row, out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"date,feedly_{PRIMARY},gh_views_14d,gc_pageviews_7d"
    assert lines[1:] == ["2026-09-07,5,,7"] * 2
