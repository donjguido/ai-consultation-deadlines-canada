"""Scaffold a fork of this monitor for another geography.

Usage (from the root of your fork):

    python -m pipeline.fork --name "AI Consultation Deadlines Ontario" \
        --place Ontario --level provincial --schema-type State \
        --url https://you.github.io/ai-consultation-deadlines-ontario \
        --repo https://github.com/you/ai-consultation-deadlines-ontario \
        --author "Your Name" --author-url https://github.com/you \
        --languages en,fr

What it does, in order:

  1. Rewrites data/site.yaml as a commented file: name, slug, url, repo, author,
     jurisdiction, languages, and a first draft of the primary-language `text:` block
     generated from the place name. Secondary-language blocks start empty, with the
     primary values shown as comments to translate (a missing key falls back to the
     primary language, so the suite is green before you translate). The pre-filter
     keywords are kept so you can edit rather than rewrite them.
  2. Empties data/items.json, resets data/forks.yaml to list the original as a sister
     site, and empties the generated site/ directory.
  3. Replaces data/sources.yaml with a commented template showing every fetcher kind.
  4. Prints the checklist of what is left to do by hand.

Pass --dry-run to see the plan without writing. Pass --root to act on another
checkout (the tests use this). Nothing here touches Python or the template.
"""
from __future__ import annotations

import argparse
import re
import shutil
import unicodedata
from pathlib import Path

import yaml

from .config import ROOT


def slugify(s: str) -> str:
    """ASCII slug: accents are transliterated, not dropped, so an accented site name
    gives "echeances-quebec" rather than "ch-ances-qu-bec". Override with --slug."""
    s = s.replace("ß", "ss").replace("æ", "ae").replace("œ", "oe").replace("Æ", "AE").replace("Œ", "OE")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def draft_text(name: str, place: str, level: str) -> dict:
    """A serviceable first draft of the site prose for one language, from the place name."""
    lvl = f"{level} " if level else ""
    return {
        "title": name,
        "page_title": f"{name} — open {lvl}consultations on AI".replace("  ", " "),
        "tagline": (f"Every {lvl}consultation, call for evidence and comment period where people in "
                    f"{place} can shape how AI is governed. Updated twice a week."),
        "description": f"{lvl.capitalize()}consultations and other ways people in {place} can shape AI safety.",
        "channels": f"{lvl}consultations, calls for evidence, comment periods, funding calls and petitions",
        "audience": f"people in {place}",
        "cadence": "twice a week",
        "calendar_description": (f"Closing dates for {lvl}consultations, calls for evidence and comment "
                                 f"periods where people in {place} can shape how AI is governed."),
        "dataset_name": f"{place} {lvl}AI-governance participation channels".replace("  ", " "),
        "government_licence": None,
    }


SOURCES_TEMPLATE = """# Intake channels monitored. `kind` selects the fetcher in pipeline/fetch.py.
# Tier 1 = machine-readable, cheap, high yield. Tier 2 = HTML scraping, brittle.
# Tier 3 = manual watch list reviewed by the human curator.
#
# Every fetcher applies the keyword pre-filter from data/site.yaml (prefilter_keywords)
# before the classifier sees anything. `enabled: false` keeps a source on record
# without running it. See docs/FORKING.md for the columns each kind expects.

sources:
  # ---- Tier 1: machine-readable -------------------------------------------
  # A consultation registry's open-data CSV. `columns` maps candidate fields to
  # column names; `text` lists the columns joined for the keyword filter.
  # - key: registry_csv
  #   kind: csv
  #   tier: 1
  #   body: "Name of the registry's owner"
  #   csv: https://example.gov/open-data/consultations.csv
  #   portal: https://example.gov/consultations
  #   id_prefix: reg-
  #   open_statuses: [open, planned]
  #   columns:
  #     id: registration_number
  #     title: title_en
  #     title_fr: title_fr
  #     url: profile_page_en
  #     opened: start_date
  #     closes: end_date
  #     status: status
  #     body: owner_org_title
  #     text: [title_en, description_en, subjects]

  # A JSON endpoint. `items_path` is a dotted path to the list; `columns` values
  # are dotted paths inside each element.
  # - key: registry_api
  #   kind: json_api
  #   tier: 1
  #   body: "Name of the API's owner"
  #   url: https://example.gov/api/consultations?status=open
  #   items_path: data.items
  #   columns:
  #     id: id
  #     title: attributes.title
  #     url: links.self
  #     opened: attributes.opens_on
  #     closes: attributes.closes_on
  #     text: [attributes.title, attributes.summary]

  # An RSS or Atom feed (an official gazette). `fetch_pages: true` fetches each
  # linked page so the classifier can read the comment deadline from it.
  # - key: gazette
  #   kind: rss
  #   tier: 1
  #   body: "Official Gazette"
  #   url: https://example.gov/gazette/rss.xml
  #   fetch_pages: true

  # ---- Tier 2: HTML ---------------------------------------------------------
  # An XML sitemap filtered by URL pattern; each matching page is fetched.
  # - key: ministry_sitemap
  #   kind: sitemap
  #   tier: 2
  #   body: "Ministry of Example"
  #   url: https://example.gov/sitemap.xml
  #   include: /consultations/
  #   limit: 100

  # An index page scraped for links matching a CSS selector.
  # - key: committee_pages
  #   kind: html_index
  #   tier: 2
  #   body: "Legislature committees"
  #   url: https://example.gov/committees/
  #   selector: "main a[href*='/inquiry/']"

  # ---- Tier 3: manual watch list (no fetcher) -----------------------------
  # - Bodies that block automated fetches, or publish only PDFs: list them here
  #   so the curator checks them by hand on the weekly sweep.
"""

FORKS_TEMPLATE = """# Sister sites built from the same template. Every build publishes this list as
# forks.json and links it from llms.txt and the footer. The original is listed
# first; add your own siblings as you find them.
forks:
{entries}"""


SITE_TEMPLATE = """# Site identity. Everything geography-specific that is not a source (data/sources.yaml)
# or an item (data/items.json) lives here. Generated by `python -m pipeline.fork`; edit
# freely and touch no Python. UI strings that are the same for every site in a language
# (badge names, button labels) live in pipeline/strings/<lang>.yaml; the `text:` block
# below holds the prose that names this site and its jurisdiction. Every key here is
# explained in docs/FORKING.md.

name: {name}
slug: {slug}        # feed generator, calendar UIDs, user agent
url: {url}
repo: {repo}
version: "0.1"              # your site's version; shown in the calendar PRODID and the user agent
author:
  name: {author}
  url: {author_url}
copyright_year: {year}       # first year of the footer's copyright line

jurisdiction:
  name: {place}
  level: {level}            # adjective used in generated prose: federal, provincial, municipal, EU
  schema_type: {schema_type}      # schema.org type for spatialCoverage: Country, State, City, AdministrativeArea

languages:
  primary: {primary}               # the language the HTML is rendered in before any JavaScript runs
  secondary: {secondary}          # [] for a monolingual site; each code needs pipeline/strings/<code>.yaml
locales:                    # BCP 47 tags for <html lang>, hreflang, feeds and date formatting
{locales}

licence:
  code: MIT                 # the code
  data: CC BY 4.0           # the published dataset: items.json, the feeds, the calendars
  data_url: https://creativecommons.org/licenses/by/4.0/

# Site-specific prose, one block per language. The primary block is a first draft made
# from the place name, in English whatever the primary language: rewrite it in your own
# words and language. Each secondary block starts empty
# with the primary values shown as comments: translate them. A key missing from a
# secondary block falls back to the primary language, and `python -m pytest` fails if a
# secondary block is mostly an untranslated copy of the primary.
#   title                 the site name, shown in the header and the feeds
#   page_title            the page <title> and the feed titles
#   tagline               one sentence under the site name
#   description           meta description and schema.org description
#   channels              the kinds of channel monitored, as a list in prose
#   audience              who can take part, e.g. "people in <place>"
#   cadence               how often the site is updated, e.g. "twice a week"
#   calendar_description  the description of the .ics calendar
#   dataset_name          schema.org Dataset name
#   government_licence    the licence government content is reproduced under, or null
text:
{text}
# Cookieless visit and click counting, off unless `goatcounter` names an endpoint. Create a
# site at goatcounter.com (free for non-commercial use, no cookies, no consent banner) and
# paste its count URL. Empty means the page loads no analytics at all.
analytics:
  goatcounter: ""
keywords:                   # schema.org Dataset keywords
{keywords}
# The classifier prompt in pipeline/classify.py is jurisdiction-neutral; this block is
# the part that names the place. `scope` describes the channels being screened, `place`
# is used in "in <place>", `official_names` (optional) tells the model which naming
# conventions to follow for bodies and programmes in the secondary languages, and
# `style` is one paragraph per secondary language on how to write it well.
classifier:
{classifier}
# Regex fragments joined with | into the keyword pre-filter in pipeline/fetch.py. Broad on
# purpose: false positives are cheap (the classifier rejects them), false negatives are
# invisible. A fragment matches anywhere inside a word unless it carries its own \\b, so
# a stem such as `biometri` catches every inflection. Include every language your
# sources publish in.
prefilter_keywords:
{prefilter}"""


def _yaml(value, indent: int = 0) -> str:
    """One value as a YAML fragment, indented, without the document markers."""
    out = yaml.safe_dump(value, allow_unicode=True, sort_keys=False, width=100, default_flow_style=False)
    out = out.removesuffix("...\n").rstrip("\n")
    return "\n".join((" " * indent + line) if line else line for line in out.split("\n"))


def _scalar(value) -> str:
    return _yaml(value).strip()


def render_site_yaml(args: argparse.Namespace, old: dict) -> str:
    """The scaffolded site.yaml as text, so the documentation comments survive the rewrite."""
    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    primary, secondary = langs[0], langs[1:]
    draft = draft_text(args.name, args.place, args.level)

    text = _yaml({primary: draft}, 2)
    for lang in secondary:
        text += f"\n  {lang}: {{}}                  # translate every key of the {primary} block; missing keys fall back to {primary}"
        for key, value in draft.items():
            text += "\n    # " + _yaml({key: value}).strip().replace("\n", "\n    # ")
    text += "\n"

    old_cls = old.get("classifier") or {}
    classifier = {
        "scope": (f"{args.place} {args.level} intake channels (public consultations, calls for evidence, "
                  "comment periods, funding calls, petitions)").replace("  ", " "),
        "place": args.place,
    }
    styles = {x: (old_cls.get("style") or {}).get(x) for x in secondary if (old_cls.get("style") or {}).get(x)}
    if styles:
        classifier["style"] = styles
    cls = _yaml(classifier, 2) + "\n"
    if secondary:
        cls += ("  # official_names: >-\n"
                "  #   use the official {name} name of a department, committee or programme when one exists\n"
                "  #   (e.g. \"...\")\n").format(name=_lang_names(secondary))
        for lang in secondary:
            if lang not in styles:
                cls += (f"  # style:\n  #   {lang}: >-\n"
                        f"  #     Write {lang} of the same quality as the {primary}: idiomatic prose, not a\n"
                        f"  #     word-for-word calque. Note the date format and typography readers expect.\n")

    return SITE_TEMPLATE.format(
        name=_scalar(args.name), slug=_scalar(args.slug or slugify(args.name)),
        url=_scalar(args.url.rstrip("/")), repo=_scalar(args.repo),
        author=_scalar(args.author), author_url=_scalar(args.author_url or args.repo), year=args.year,
        place=_scalar(args.place), level=_scalar(args.level or ""), schema_type=_scalar(args.schema_type),
        primary=primary, secondary="[" + ", ".join(secondary) + "]",
        locales=_yaml({x: (args.locales or {}).get(x, x) for x in langs}, 2),
        text=text,
        keywords=_yaml(["AI governance", "AI safety", args.place, "public consultation",
                        "regulation", "civic participation"]) + "\n",
        classifier=cls,
        prefilter=_yaml(old.get("prefilter_keywords") or ["artificial intelligence", r"\bAI\b"]) + "\n",
    )


def _lang_names(codes: list[str]) -> str:
    return " / ".join(codes)


def scaffold(args: argparse.Namespace, root: Path) -> list[str]:
    data = root / "data"
    site_path = data / "site.yaml"
    old = yaml.safe_load(site_path.read_text(encoding="utf-8"))
    original = {
        "name": old["name"], "jurisdiction": old["jurisdiction"]["name"],
        "url": old["url"], "repo": old.get("repo", ""),
        "languages": [old["languages"]["primary"], *(old["languages"].get("secondary") or [])],
    }
    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    site_text = render_site_yaml(args, old)
    site = yaml.safe_load(site_text)

    plan = [f"site.yaml   name={site['name']!r} slug={site['slug']!r} url={site['url']} languages={langs}",
            "items.json  emptied to []",
            "forks.yaml  reset, listing the original site",
            "sources.yaml replaced with the commented template",
            "site/       emptied (the original's rendered pages; rebuilt by pipeline.build)"]
    if args.dry_run:
        return plan

    site_path.write_text(site_text, encoding="utf-8")
    (data / "items.json").write_text("[]\n", encoding="utf-8")
    entries = yaml.safe_dump([original], allow_unicode=True, sort_keys=False, width=100)
    (data / "forks.yaml").write_text(FORKS_TEMPLATE.format(entries=entries), encoding="utf-8")
    (data / "sources.yaml").write_text(SOURCES_TEMPLATE, encoding="utf-8")
    generated = root / "site"
    if generated.is_dir():
        shutil.rmtree(generated)
        generated.mkdir()
    return plan


def checklist(args: argparse.Namespace, root: Path) -> str:
    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    secondary = langs[1:]
    missing = [x for x in langs if not (root / "pipeline" / "strings" / f"{x}.yaml").exists()]
    lines = [
        "",
        "Next steps (python -m pytest is green as scaffolded; keep it that way at each step):",
        "  0. README.md and CHANGELOG.md still describe the original site: rewrite the README's",
        "     first section and start a fresh CHANGELOG.",
        "  1. data/site.yaml `text`: rewrite the generated draft (English, whatever your primary",
        "     language) in your own words and set",
        "     `government_licence` (null hides the licence line)."
        + (f" Translate the block for: {', '.join(secondary)}." if secondary else ""),
        "     data/site.yaml `classifier`: fill in `official_names` and `style.<lang>` from the commented examples."
        if secondary else
        "     data/site.yaml `classifier`: check `scope` reads well.",
        "  2. data/sources.yaml: add your registry, legislature, gazette and petition sources",
        "     (fetch prints \"no enabled sources\" until you do).",
        "  3. data/site.yaml `prefilter_keywords`: add terms in every language your sources publish in.",
    ]
    if missing:
        lines.append(f"  4. Add UI strings for: {', '.join(missing)} (copy pipeline/strings/en.yaml to <lang>.yaml"
                     " and translate every value; pytest checks the file is complete).")
    else:
        lines.append("  4. (UI strings for every configured language already exist in pipeline/strings/.)")
    lines += [
        "  5. python -m pytest                      (offline; the deploy workflow refuses a red suite)",
        "  6. python -m pipeline.fetch data/candidates.json && ANTHROPIC_API_KEY=... python -m pipeline.classify data/candidates.json data/items.json",
        "     (python -m pipeline.classify --print-prompt shows the prompt your classifier block builds, no key needed)",
        "  7. python -m pipeline.build data/items.json site && python -m http.server 8000 --directory site",
        "  8. Enable GitHub Pages (Settings > Pages > Source: GitHub Actions) and set the ANTHROPIC_API_KEY secret.",
        "  9. Open a pull request on the original repo adding your site to data/forks.yaml.",
        "  Score yourself against docs/FORK-RUBRIC.md and file what you hit as an issue on the original.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m pipeline.fork", description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--name", required=True, help='e.g. "AI Consultation Deadlines Ontario"')
    p.add_argument("--place", required=True, help="jurisdiction name, e.g. Ontario")
    p.add_argument("--level", default="", help="adjective for prose: federal, provincial, municipal, EU")
    p.add_argument("--schema-type", default="AdministrativeArea",
                   help="schema.org type for spatialCoverage: Country, State, City, AdministrativeArea")
    p.add_argument("--url", required=True, help="where the site will be published")
    p.add_argument("--repo", required=True, help="the fork's repository URL")
    p.add_argument("--author", required=True)
    p.add_argument("--author-url", default="")
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--slug", default="", help="defaults to a slug of --name")
    p.add_argument("--languages", default="en", help="comma-separated, primary first, e.g. en,fr or de")
    p.add_argument("--locale", action="append", default=[], metavar="LANG=TAG",
                   help="BCP 47 tag per language, e.g. --locale en=en-GB --locale cy=cy-GB")
    p.add_argument("--root", default=str(ROOT), help="checkout to act on (default: this one)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    if args.year is None:
        from datetime import date
        args.year = date.today().year
    args.locales = dict(x.split("=", 1) for x in args.locale)
    root = Path(args.root)

    for line in scaffold(args, root):
        print(("would write: " if args.dry_run else "wrote: ") + line)
    print(checklist(args, root))


if __name__ == "__main__":
    main()
