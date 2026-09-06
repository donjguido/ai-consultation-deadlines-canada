"""Scaffold a fork of this monitor for another geography.

Usage (from the root of your fork):

    python -m pipeline.fork --name "AI Consultation Deadlines Ontario" \
        --place Ontario --level provincial --schema-type State \
        --url https://you.github.io/ai-consultation-deadlines-ontario \
        --repo https://github.com/you/ai-consultation-deadlines-ontario \
        --author "Your Name" --author-url https://github.com/you \
        --languages en,fr

What it does, in order:

  1. Rewrites data/site.yaml: name, slug, url, repo, author, jurisdiction, languages,
     and a first draft of the per-language `text:` block (primary-language prose
     generated from the place name; other languages copied from it and listed for
     translation). The classifier block, keywords and pre-filter keywords are kept
     so you can edit rather than rewrite them.
  2. Empties data/items.json and data/forks.yaml.
  3. Replaces data/sources.yaml with a commented template showing every fetcher kind.
  4. Prints the checklist of what is left to do by hand.

Pass --dry-run to see the plan without writing. Pass --root to act on another
checkout (the tests use this). Nothing here touches Python or the template.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

from .config import ROOT


def slugify(s: str) -> str:
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


def scaffold(args: argparse.Namespace, root: Path) -> list[str]:
    data = root / "data"
    site_path = data / "site.yaml"
    site = yaml.safe_load(site_path.read_text(encoding="utf-8"))
    original = {
        "name": site["name"], "jurisdiction": site["jurisdiction"]["name"],
        "url": site["url"], "repo": site.get("repo", ""),
        "languages": [site["languages"]["primary"], *(site["languages"].get("secondary") or [])],
    }
    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    primary, secondary = langs[0], langs[1:]

    site["name"] = args.name
    site["slug"] = args.slug or slugify(args.name)
    site["url"] = args.url.rstrip("/")
    site["repo"] = args.repo
    site["version"] = "0.1"
    site["author"] = {"name": args.author, "url": args.author_url or args.repo}
    site["copyright_year"] = args.year
    site["jurisdiction"] = {"name": args.place, "level": args.level, "schema_type": args.schema_type}
    site["languages"] = {"primary": primary, "secondary": secondary}
    site["locales"] = {x: (args.locales or {}).get(x, x) for x in langs}
    draft = draft_text(args.name, args.place, args.level)
    site["text"] = {x: dict(draft) for x in langs}
    site["keywords"] = ["AI governance", "AI safety", args.place, "public consultation",
                        "regulation", "civic participation"]
    site.setdefault("classifier", {})
    site["classifier"]["place"] = args.place
    site["classifier"]["scope"] = f"{args.place} {args.level} intake channels (public consultations, calls for evidence, comment periods, funding calls, petitions)".replace("  ", " ")
    site["classifier"].pop("official_names", None)
    site["classifier"]["style"] = {x: site["classifier"].get("style", {}).get(x) for x in secondary
                                   if site["classifier"].get("style", {}).get(x)}
    if not site["classifier"]["style"]:
        site["classifier"].pop("style")

    plan = [f"site.yaml   name={site['name']!r} slug={site['slug']!r} url={site['url']} languages={langs}",
            "items.json  emptied to []",
            "forks.yaml  reset, listing the original site",
            "sources.yaml replaced with the commented template"]
    if args.dry_run:
        return plan

    header = ("# Site identity. Everything geography-specific that is not a source (data/sources.yaml)\n"
              "# or an item (data/items.json) lives here. Generated by `python -m pipeline.fork`;\n"
              "# edit freely. UI strings live in pipeline/strings/<lang>.yaml.\n\n")
    site_path.write_text(header + yaml.safe_dump(site, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
    (data / "items.json").write_text("[]\n", encoding="utf-8")
    entries = yaml.safe_dump([original], allow_unicode=True, sort_keys=False, width=100)
    (data / "forks.yaml").write_text(FORKS_TEMPLATE.format(entries=entries), encoding="utf-8")
    (data / "sources.yaml").write_text(SOURCES_TEMPLATE, encoding="utf-8")
    return plan


def checklist(args: argparse.Namespace, root: Path) -> str:
    langs = [x.strip() for x in args.languages.split(",") if x.strip()]
    missing = [x for x in langs if not (root / "pipeline" / "strings" / f"{x}.yaml").exists()]
    lines = [
        "",
        "Next steps:",
        "  1. data/site.yaml: read the generated `text:` block and rewrite it in your own words;",
        "     translate it for each secondary language: " + (", ".join(langs[1:]) or "(none)") + ".",
        "     Fill `classifier.official_names` and `classifier.style.<lang>` if you have a second language.",
        "  2. data/sources.yaml: add your registry, legislature, gazette and petition sources.",
        "  3. data/site.yaml `prefilter_keywords`: add terms in every language your sources publish in.",
    ]
    if missing:
        lines.append(f"  4. Add UI strings for: {', '.join(missing)} (copy pipeline/strings/en.yaml to <lang>.yaml).")
    else:
        lines.append("  4. (UI strings for every configured language already exist in pipeline/strings/.)")
    lines += [
        "  5. python -m pytest                      (offline; must be green before you deploy)",
        "  6. python -m pipeline.fetch data/candidates.json && ANTHROPIC_API_KEY=... python -m pipeline.classify data/candidates.json data/items.json",
        "  7. python -m pipeline.build data/items.json site && python -m http.server 8000 --directory site",
        "  8. Enable GitHub Pages (Settings > Pages > Source: GitHub Actions) and set the ANTHROPIC_API_KEY secret.",
        "  9. Open a pull request on the original repo adding your site to data/forks.yaml.",
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
    if not args.dry_run:
        print(checklist(args, root))


if __name__ == "__main__":
    main()
