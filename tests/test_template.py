"""pipeline/template.html is hand-edited. Losing a placeholder or an element the
JavaScript looks up by id breaks the site silently, so pin them here."""
import re

from pipeline.build import TEMPLATE

REQUIRED_PLACEHOLDERS = [
    "__DESC__", "__SITE_URL__", "__COUNT__", "__BUILT__", "__SLUG__", "__LOCALE__", "__PLACE__",
    "__LICENCE_URL__",
    "<!--__STATS__-->", "<!--__ITEMS__-->", "<!--__JSONLD__-->", "<!--__HEAD_LINKS__-->",
    "<!--__LANG_BUTTONS__-->", "<!--__FORKS__-->", "<!--__ANALYTICS__-->",
    "/*__DATA__*/[]", "/*__L__*/{}", "/*__CONFIG__*/{}",
]
# Elements the inline script and the build step address by id.
REQUIRED_IDS = ["lang-toggle", "main", "stats", "filters", "q", "type", "body", "topics", "items", "count",
                "list", "cal-all", "calbox"]
# Strings the script reads from the injected L object; each must exist in every strings file.
I18N_KEYS = ["page_title", "title", "tagline", "links_line", "skip", "at_a_glance", "search_and_filter",
             "search_label", "filter_type", "all_types", "filter_body", "all_bodies", "monitored_items",
             "all_cal", "footer_status", "footer_credit"]


def _html() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


ONCE_ONLY = {"<!--__STATS__-->", "<!--__ITEMS__-->", "<!--__JSONLD__-->", "<!--__HEAD_LINKS__-->",
             "<!--__LANG_BUTTONS__-->", "<!--__FORKS__-->", "<!--__ANALYTICS__-->", "<!--__NEWSLETTER__-->", "/*__DATA__*/[]", "/*__L__*/{}",
             "/*__CONFIG__*/{}", "__COUNT__"}


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


def test_no_hardcoded_site_identity():
    """Everything that names the site, the place or the author comes from site.yaml."""
    html = _html()
    for word in ("Canada", "donjguido", "Guidote", "fr-CA", "en-CA", "data-fr=", "data-en="):
        assert word not in html, f"{word!r} is hardcoded in template.html"


def test_i18n_keys_used_by_the_template_exist_in_every_strings_file():
    from pipeline.config import LANGS, strings
    html = _html()
    used = set(re.findall(r'data-i18n(?:-[a-z-]+)?="([^"]+)"', html))
    assert used >= set(I18N_KEYS)
    for lang in LANGS:
        t = strings(lang)
        missing = [k for k in used if k not in t and k not in t["text"] and k != "links_line"]
        assert not missing, f"{lang}: strings missing for {missing}"


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


def test_engagement_events_are_gated_on_the_configured_endpoint():
    """The click tracker must be a no-op unless site.yaml names an analytics endpoint,
    so a fork with the default empty block sends nothing anywhere."""
    html = _html()
    assert "CFG.analytics&&window.goatcounter" in html
    assert '"/event/"+p' in html


def test_subscribe_form_tag_follows_the_language_toggle():
    """build.py renders the form only when site.yaml names a Buttondown account; the client
    keeps its hidden tag equal to the reader's language and counts a submit as an event."""
    html = _html()
    assert '$("#nl-tag")' in html and "nlTag.value=lang" in html
    assert 'el.closest("#nl-form")' in html
