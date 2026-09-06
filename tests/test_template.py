"""pipeline/template.html is hand-edited. Losing a placeholder or an element the
JavaScript looks up by id breaks the site silently, so pin them here."""
import re

from pipeline.build import TEMPLATE

REQUIRED_PLACEHOLDERS = [
    "__DESC__", "__SITE_URL__", "__COUNT__", "__BUILT__",
    "<!--__STATS__-->", "<!--__ITEMS__-->", "<!--__JSONLD__-->", "/*__DATA__*/[]",
]
# Elements the inline script and the build step address by id.
REQUIRED_IDS = ["en", "fr", "main", "stats", "filters", "q", "type", "body", "topics", "items", "count",
                "list", "cal-all", "calbox"]


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


ONCE_ONLY = {"<!--__STATS__-->", "<!--__ITEMS__-->", "<!--__JSONLD__-->", "/*__DATA__*/[]", "__COUNT__"}


def test_placeholders_present():
    """Text placeholders (__DESC__, __SITE_URL__, __BUILT__) repeat across meta tags;
    the generated-content slots must appear exactly once or the list renders twice."""
    html = _html()
    for p in REQUIRED_PLACEHOLDERS:
        n = html.count(p)
        assert n >= 1, f"{p} is missing from template.html"
        if p in ONCE_ONLY:
            assert n == 1, f"{p} appears {n} times in template.html, expected 1"


def test_required_ids_present_once():
    html = _html()
    for i in REQUIRED_IDS:
        n = len(re.findall(rf'\bid="{i}"', html))
        assert n == 1, f'id="{i}" appears {n} times'


def test_bilingual_toggle_and_language_attributes():
    html = _html()
    assert 'lang="en"' in html and 'lang="fr"' in html
    assert html.count("data-fr=") >= 5, "bilingual strings should carry data-fr attributes"


def test_script_and_style_tags_balance():
    html = _html()
    assert html.count("<script") == html.count("</script>")
    assert html.count("<style") == html.count("</style>")
    assert "<main" in html and "</main>" in html


def test_calendar_hooks_present():
    """The add-to-calendar UI is wired by id and by these helper names; build.py
    renders the per-item menu itself, so both sides have to keep agreeing."""
    html = _html()
    assert "<dialog" in html and "</dialog>" in html
    for name in ("calMenu", "wireItemMenus", "renderCalBox", "icsFile", "downloadIcs"):
        assert name in html, f"{name} missing from template.html"
    assert ".cal-menu[hidden]" in html, (
        "the .cal-menu display:flex rule outranks the UA [hidden] rule, so this "
        "override is what keeps closed menus closed"
    )


def test_client_rechecks_deadlines_against_the_readers_own_date():
    """Statuses are baked in at build time and the site is rebuilt twice a week,
    so between builds only the browser knows a deadline has passed."""
    html = _html()
    assert "todayISO" in html and "r.closes>=todayISO()" in html
    assert "DATA.filter(upcoming)" in html, "the bulk download must use the same filter"
