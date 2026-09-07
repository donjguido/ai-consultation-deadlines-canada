"""Weekly engagement snapshot: python -m pipeline.engagement

The site is static files, so nothing counts feed or API fetches server-side. This
gathers the free signals that do exist and appends one row to data/engagement.csv,
because the sources themselves keep no history (GitHub traffic covers 14 days only):

  * Feedly subscriber count for each language's RSS feed (public API, no key).
  * GitHub repository traffic: views, unique visitors, clones over the last 14 days
    (via the `gh` CLI, which must be logged in with push access to the repo).
  * GoatCounter page views and events over the last 7 days, when site.yaml names
    an endpoint and GOATCOUNTER_TOKEN is set (an API token with "read statistics").

A source that fails leaves its columns blank and prints a warning; the row is still
written. Run it on the Monday curation pass.
"""
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlsplit

import requests

from .config import LANGS, REPO, ROOT, SITE, SITE_URL, SLUG, output_name

OUT_FILE = ROOT / "data" / "engagement.csv"
FEEDLY = "https://cloud.feedly.com/v3/feeds/"
_UA = {"User-Agent": f"{SLUG}-engagement/1.0"}

Fetcher = Callable[[str, dict], Any]


def _get(url: str, headers: dict | None = None) -> Any:
    resp = requests.get(url, timeout=20, headers={**_UA, **(headers or {})})
    resp.raise_for_status()
    return resp.json()


def feed_urls() -> dict[str, str]:
    return {lang: f"{SITE_URL}/{output_name('feed', '.xml', lang)}" for lang in LANGS}


def feedly_subscribers(get: Fetcher = _get) -> dict[str, int | None]:
    """Feedly reports how many of its users follow a feed URL. An unknown feed comes
    back as an empty list (older deployments answered 404); both mean none yet."""
    out: dict[str, int | None] = {}
    for lang, url in feed_urls().items():
        try:
            data = get(FEEDLY + quote("feed/" + url, safe=""), {})
            if isinstance(data, list):
                data = data[0] if data else {}
            out[lang] = int(data.get("subscribers", 0))
        except requests.HTTPError as e:
            out[lang] = 0 if e.response is not None and e.response.status_code == 404 else None
            if out[lang] is None:
                print(f"warning: feedly {lang}: {e}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 - a snapshot never fails as a whole
            out[lang] = None
            print(f"warning: feedly {lang}: {e}", file=sys.stderr)
    return out


def github_traffic(run: Callable[[list[str]], str] | None = None) -> dict[str, int | None]:
    """Views, unique visitors, clones and unique cloners over the last 14 days."""
    path = urlsplit(REPO).path.strip("/")
    run = run or (lambda args: subprocess.run(["gh", "api", *args], check=True, capture_output=True, text=True).stdout)
    out: dict[str, int | None] = {}
    for kind in ("views", "clones"):
        try:
            data = json.loads(run([f"repos/{path}/traffic/{kind}"]))
            out[f"gh_{kind}_14d"] = int(data.get("count", 0))
            out[f"gh_{kind}_uniques_14d"] = int(data.get("uniques", 0))
        except Exception as e:  # noqa: BLE001
            out[f"gh_{kind}_14d"] = out[f"gh_{kind}_uniques_14d"] = None
            print(f"warning: github {kind}: {e}", file=sys.stderr)
    return out


def goatcounter_totals(today: date, get: Fetcher = _get) -> dict[str, int | None]:
    """Page views and events over the last 7 days from the GoatCounter API."""
    endpoint = (SITE["analytics"].get("goatcounter") or "").strip()
    token = os.environ.get("GOATCOUNTER_TOKEN", "")
    blank: dict[str, int | None] = {"gc_pageviews_7d": None, "gc_events_7d": None}
    if not endpoint or not token:
        return blank
    parts = urlsplit(endpoint)
    base = f"{parts.scheme}://{parts.netloc}/api/v0/stats/total"
    start, end = (today - timedelta(days=7)).isoformat(), today.isoformat()
    try:
        data = get(f"{base}?start={start}&end={end}", {"Authorization": f"Bearer {token}"})
        return {"gc_pageviews_7d": int(data.get("total", 0)), "gc_events_7d": int(data.get("total_events", 0))}
    except Exception as e:  # noqa: BLE001
        print(f"warning: goatcounter: {e}", file=sys.stderr)
        return blank


def snapshot(today: date, **overrides) -> dict[str, object]:
    row: dict[str, object] = {"date": today.isoformat()}
    feedly = overrides["feedly"] if "feedly" in overrides else feedly_subscribers()
    row.update({f"feedly_{lang}": n for lang, n in feedly.items()})
    row.update(overrides["github"] if "github" in overrides else github_traffic())
    row.update(overrides["goatcounter"] if "goatcounter" in overrides else goatcounter_totals(today))
    return row


def append_row(row: dict[str, object], path: Path = OUT_FILE) -> None:
    """Append one row, writing the header when the file is new. Blank cells mean
    the source was unreachable that week, not zero."""
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow({k: ("" if v is None else v) for k, v in row.items()})


def main() -> int:
    row = snapshot(date.today())
    append_row(row)
    for k, v in row.items():
        print(f"{k:24} {'' if v is None else v}")
    print(f"\nappended to {OUT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
