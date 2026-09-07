"""The iCalendar feed and the add-to-calendar links.

Calendar clients are unforgiving about RFC 5545 details -- CRLF endings, 75-octet
line folding, escaped commas -- and a malformed file fails silently in the client
rather than loudly here, so the structural checks are worth their keep. No network.
"""
import re
from datetime import timedelta

import pytest

from pipeline import build
from tests.conftest import (
    LANG2, LANGS, PRIMARY, TODAY, make_item, needs_second_language, output_name, translated, untranslated,
)

ICS_FILES = [output_name("deadlines", ".ics", x) for x in LANGS]
PRIMARY_ICS = ICS_FILES[0]


def _write(items, out):
    out.mkdir(parents=True, exist_ok=True)
    for lang in LANGS:
        build.build_calendar(items, out, TODAY, lang)
    return out


@pytest.fixture
def cal(tmp_path, sample_items):
    return _write(sample_items, tmp_path / "site")


def _raw(out, name=PRIMARY_ICS) -> bytes:
    return (out / name).read_bytes()


def unfold(out, name=PRIMARY_ICS) -> list[str]:
    """Content lines with RFC 5545 folding undone."""
    return _raw(out, name).decode("utf-8").replace("\r\n ", "").rstrip("\r\n").split("\r\n")


# ---- file shape ------------------------------------------------------------

@pytest.mark.parametrize("name", ICS_FILES)
def test_lines_end_with_crlf_only(cal, name):
    raw = _raw(cal, name)
    assert raw.endswith(b"\r\n")
    assert b"\n" not in raw.replace(b"\r\n", b""), "bare LF in an .ics file"


@pytest.mark.parametrize("name", ICS_FILES)
def test_no_line_exceeds_75_octets(cal, name):
    long = [l for l in _raw(cal, name).split(b"\r\n") if len(l) > 75]
    assert not long, f"{name}: {len(long)} line(s) over the 75-octet fold limit"


@pytest.mark.parametrize("name", ICS_FILES)
def test_calendar_and_events_are_balanced(cal, name):
    lines = unfold(cal, name)
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-1] == "END:VCALENDAR"
    for tag in ("VEVENT", "VALARM"):
        assert lines.count(f"BEGIN:{tag}") == lines.count(f"END:{tag}")
    assert "VERSION:2.0" in lines
    assert any(l.startswith("PRODID:") for l in lines)


@pytest.mark.parametrize("name", ICS_FILES)
def test_feed_is_subscribable(cal, name):
    """Clients only re-read a published calendar if it says how often to look."""
    lines = unfold(cal, name)
    assert "REFRESH-INTERVAL;VALUE=DURATION:PT12H" in lines
    assert "X-PUBLISHED-TTL:PT12H" in lines
    assert any(l.startswith("X-WR-CALNAME:") for l in lines)


# ---- which items get an event ---------------------------------------------

def test_only_open_items_with_a_stated_deadline_appear(cal, sample_items):
    uids = {l.split(":", 1)[1].split("@")[0] for l in unfold(cal) if l.startswith("UID:")}
    expected = {i.id for i in sample_items if i.status(TODAY) == "open" and i.closes}
    assert uids == expected
    assert "no-deadline" not in uids, "an item with no closing date has nothing to put in a calendar"
    assert "expired" not in uids and "retired-flag" not in uids


def test_uids_are_scoped_to_the_site_slug(cal):
    uids = [l for l in unfold(cal) if l.startswith("UID:")]
    assert uids and all(l.endswith("@" + build.SLUG) for l in uids)


def test_a_past_deadline_is_never_offered(tmp_path):
    """Nobody wants last month's closing dates in their calendar, in bulk or singly."""
    past = make_item(id="past", closes=TODAY - timedelta(days=1))
    future = make_item(id="future", closes=TODAY + timedelta(days=1))
    assert not build.has_upcoming_deadline(past, TODAY)
    assert build.has_upcoming_deadline(future, TODAY)
    lines = unfold(_write([past, future], tmp_path / "site"))
    assert not any(l.startswith("UID:past@") for l in lines)
    assert any(l.startswith("UID:future@") for l in lines)


def test_a_deadline_falling_today_still_counts(tmp_path):
    """The last day to respond is not a past deadline."""
    item = make_item(id="closes-today", closes=TODAY)
    assert build.has_upcoming_deadline(item, TODAY)
    lines = unfold(_write([item], tmp_path / "site"))
    assert any(l.startswith("UID:closes-today@") for l in lines)


def test_event_is_all_day_and_ends_the_following_day(cal, sample_items):
    """DTEND is exclusive for a DATE value, so a one-day event ends on the next date."""
    lines = unfold(cal)
    item = next(i for i in sample_items if i.id == "closing-soon")
    start = lines.index(f"DTSTART;VALUE=DATE:{item.closes:%Y%m%d}")
    assert lines[start + 1] == f"DTEND;VALUE=DATE:{item.closes + timedelta(days=1):%Y%m%d}"


def test_each_event_has_both_reminders(cal):
    lines = unfold(cal)
    events = lines.count("BEGIN:VEVENT")
    assert lines.count("TRIGGER;VALUE=DURATION:-P7D") == events
    assert lines.count("TRIGGER;VALUE=DURATION:-P1D") == events


def test_the_week_before_is_the_first_reminder_on_every_event(cal):
    """A week is enough notice to actually write something, so it leads."""
    triggers = [l for l in unfold(cal) if l.startswith("TRIGGER;")]
    assert triggers, "no reminders at all"
    assert triggers[::2] == ["TRIGGER;VALUE=DURATION:-P7D"] * (len(triggers) // 2)
    assert triggers[1::2] == ["TRIGGER;VALUE=DURATION:-P1D"] * (len(triggers) // 2)


def test_events_are_ordered_by_closing_date(cal):
    starts = [l for l in unfold(cal) if l.startswith("DTSTART")]
    assert starts == sorted(starts)


# ---- escaping and honesty --------------------------------------------------

def test_commas_and_semicolons_are_escaped_in_text_values(cal):
    """make_item's body contains a comma; an unescaped one splits the value."""
    desc = next(l for l in unfold(cal) if l.startswith("DESCRIPTION:Ministry"))
    assert "Ministry of Example\\, Testing" in desc
    assert not re.search(r"(?<!\\),", desc.split(":", 1)[1]), "unescaped comma in a TEXT value"


def test_categories_keep_their_separator_unescaped(cal):
    """CATEGORIES is a list, so its commas separate values rather than being literal."""
    cats = next(l for l in unfold(cal) if l.startswith("CATEGORIES:"))
    assert cats == "CATEGORIES:privacy,standards"


def test_unverified_dates_are_flagged_rather_than_dropped(tmp_path):
    """The site marks unchecked dates with a warning glyph; the calendar says so too."""
    unchecked = make_item(id="unchecked", verified=False, closes=TODAY + timedelta(days=10))
    checked = make_item(id="checked", verified=True, closes=TODAY + timedelta(days=10))
    out = _write([unchecked, checked], tmp_path / "site")
    lines = unfold(out)
    uids = {l.split(":", 1)[1].split("@")[0] for l in lines if l.startswith("UID:")}
    assert uids == {"unchecked", "checked"}, "an unverified item must still reach the calendar"
    marker = build.strings(PRIMARY)["cal_unverified"]
    warnings = [l for l in lines if build._ics_text(marker) in l]
    assert len(warnings) == 1, "exactly the unverified event should carry the warning"


# ---- multilingual ----------------------------------------------------------

@needs_second_language
def test_translated_feed_uses_translated_prose(cal):
    t2, t1 = build.strings(LANG2), build.strings(PRIMARY)
    fr = "\n".join(unfold(cal, output_name("deadlines", ".ics", LANG2)))
    en = "\n".join(unfold(cal, PRIMARY_ICS))
    assert t2["deadline_prefix"] in fr and t1["deadline_prefix"] not in fr
    assert t1["deadline_prefix"] in en
    assert translated("title") in fr
    assert build._ics_text(t2["alarm_7"].format(x=translated("title"))) in fr


@needs_second_language
def test_untranslated_items_fall_back_to_the_primary_language(tmp_path):
    item = untranslated(id="untranslated", closes=TODAY + timedelta(days=5))
    out = _write([item], tmp_path / "site")
    fr = "\n".join(unfold(out, output_name("deadlines", ".ics", LANG2)))
    assert "Test consultation" in fr, "a missing translated title should fall back, not render blank"


def test_the_feeds_describe_the_same_events(cal):
    def uids(name):
        return [l for l in unfold(cal, name) if l.startswith("UID:")]
    for name in ICS_FILES[1:]:
        assert uids(PRIMARY_ICS) == uids(name)


# ---- the per-item links ----------------------------------------------------

def test_google_link_carries_an_all_day_date_range():
    item = make_item(closes=TODAY + timedelta(days=10))
    url = build.google_url(item)
    assert url.startswith("https://calendar.google.com/calendar/render?")
    dates = re.search(r"dates=(\d{8})%2F(\d{8})", url)
    assert dates, f"no dates parameter in {url}"
    assert dates.group(1) == f"{item.closes:%Y%m%d}"
    assert dates.group(2) == f"{item.closes + timedelta(days=1):%Y%m%d}"


def test_outlook_link_is_marked_all_day():
    item = make_item(closes=TODAY + timedelta(days=10))
    url = build.outlook_url(item)
    assert url.startswith("https://outlook.live.com/calendar/0/deeplink/compose?")
    assert "allday=true" in url
    assert f"startdt={item.closes.isoformat()}" in url
    assert f"enddt={(item.closes + timedelta(days=1)).isoformat()}" in url


def test_links_percent_encode_the_way_encodeuricomponent_does():
    """The client builds these URLs too; both must produce identical markup."""
    item = make_item(title="Rights, duties & (safety) — a test", closes=TODAY + timedelta(days=5))
    url = build.google_url(item)
    assert "%2C" in url and "%26" in url, "comma and ampersand must be encoded"
    assert "(" in url and ")" in url, "encodeURIComponent leaves parentheses alone"
    assert "'" not in url or "%27" not in url, "apostrophes follow encodeURIComponent"
    assert " " not in url


def test_link_body_matches_the_ics_description(tmp_path):
    """One helper feeds the .ics, the Google link and the Outlook link."""
    item = make_item(id="shared-text", closes=TODAY + timedelta(days=5))
    title, details = build.cal_text(item)
    assert title.startswith(build.strings(PRIMARY)["deadline_prefix"])
    assert item.url in details
    assert build.SITE_URL in details
    out = _write([item], tmp_path / "shared")
    lines = unfold(out)
    event = lines[lines.index("BEGIN:VEVENT"):]
    desc = next(l for l in event if l.startswith("DESCRIPTION:"))
    assert desc == "DESCRIPTION:" + build._ics_text(details)
    assert next(l for l in event if l.startswith("SUMMARY:")) == "SUMMARY:" + build._ics_text(title)


# ---- the server-rendered menu ---------------------------------------------

def test_menu_is_rendered_only_for_items_that_have_a_deadline(sample_items):
    """build.py renders the primary-language list, so the buttons must be in the HTML itself."""
    records = build.sorted_records(sample_items, TODAY)
    html = build.render_items_html(records, {i.id: i for i in sample_items}, TODAY)
    for item in sample_items:
        expected = item.status(TODAY) == "open" and item.closes is not None
        assert (f'data-cal="{item.id}"' in html) is expected, f"{item.id}: menu presence is wrong"


def test_menu_offers_all_three_destinations(sample_items):
    records = build.sorted_records(sample_items, TODAY)
    html = build.render_items_html(records, {i.id: i for i in sample_items}, TODAY)
    assert "calendar.google.com" in html
    assert "outlook.live.com" in html
    assert 'data-ics="closing-soon"' in html
    assert 'class="cal-menu" role="menu" hidden' in html, "the menu must start closed"


def test_menu_urls_are_html_escaped(sample_items):
    """Query strings are full of ampersands; unescaped they break the attribute."""
    records = build.sorted_records(sample_items, TODAY)
    html = build.render_items_html(records, {i.id: i for i in sample_items}, TODAY)
    hrefs = re.findall(r'<a role="menuitem" href="([^"]*)"', html)
    assert hrefs
    for h in hrefs:
        assert "&amp;" in h and not re.search(r"&(?!amp;|quot;|lt;|gt;)", h)
