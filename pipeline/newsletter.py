"""Fortnightly newsletter: python -m pipeline.newsletter data/items.json [--send] [--dry-run] [--force]

The site is static, so the newsletter is the one push channel. Subscribers sign up through
Buttondown's hosted form (rendered by build.py when site.yaml `newsletter.buttondown` names
an account); this module writes the issue and hands it to Buttondown's API, which owns the
list, the unsubscribe links and the anti-spam footer. No address ever touches this repo.

What an issue contains is decided here, from the store, not by the model:

  * items first seen since the last issue,
  * items closing within the closing-soon window,
  * items whose closing date moved since the last issue,
  * items that closed or were withdrawn since the last issue,
  * a count of everything else still open.

Claude writes only the framing: a subject line and a two- or three-sentence lead per
language, from the rendered facts. Every date, title and link in the body comes straight
from data/items.json, so nothing the model could get wrong reaches a reader. Without an
API key the framing falls back to the stock sentences in pipeline/strings/<lang>.yaml.

State lives in data/newsletter.json: the date of the last issue and a snapshot of each
item's status and closing date, which is what the next issue is diffed against. It is
written only after Buttondown has accepted the issue, and the workflow commits it.

By default the issue lands in Buttondown as a draft for a person to read and press send
on; --send (or NEWSLETTER_AUTOSEND=true) sends it straight away. The fortnight guard skips
a run that falls within MIN_DAYS of the last issue, so a weekly schedule sends fortnightly.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

import requests
from pydantic import BaseModel, Field, create_model

from .build import fmt_date, load_items
from .classify import MODEL
from .config import LANGS, PRIMARY, ROOT, SECONDARY, SITE, SITE_URL, field as lang_field, output_name, pick, strings
from .models import CLOSING_SOON_DAYS, Item

STATE_FILE = ROOT / "data" / "newsletter.json"
API_URL = "https://api.buttondown.com/v1/emails"
MIN_DAYS = 13          # a weekly schedule becomes fortnightly; a manual run can --force past it
MAX_TOKENS = 1200      # subject + lead per language; cost-guarded in tests like the classifier

Poster = Callable[[str, dict, dict], Any]


# ---- delta -----------------------------------------------------------------------

def snapshot(items: list[Item], today: date) -> dict[str, dict]:
    """What the next issue compares against: status and closing date per item."""
    return {i.id: {"status": i.status(today), "closes": i.closes.isoformat() if i.closes else None} for i in items}


def delta(items: list[Item], prev: dict[str, dict] | None, today: date) -> dict[str, Any]:
    """The sections of an issue. With no previous snapshot (the first issue) 'new' means
    the store's own new window, so the first letter is not a dump of the whole store."""
    prev = prev or {}
    first = not prev
    new, closing, moved, retired, open_ = [], [], [], [], []
    for i in items:
        st = i.status(today)
        was = prev.get(i.id)
        if st == "retired":
            if was and was["status"] != "retired":
                retired.append(i)
            continue
        is_new = i.is_new(today) if first else was is None
        if is_new:
            new.append(i)
        elif i.is_closing_soon(today):
            closing.append(i)
        elif was and was["closes"] != (i.closes.isoformat() if i.closes else None):
            moved.append(i)
        else:
            open_.append(i)
    return {"new": new, "closing": closing, "moved": moved, "retired": retired, "open": open_}


def has_news(d: dict[str, Any]) -> bool:
    return any(d[k] for k in ("new", "closing", "moved", "retired"))


# ---- facts (rendered from the store, never by the model) -------------------------

def _entry(i: Item, lang: str, today: date, t: dict) -> str:
    text = lambda f: pick(i, f, lang)  # noqa: E731
    if i.closes:
        verb = t["closed"] if i.status(today) == "retired" else t["closes"]
        when = f"{verb.lower()} {fmt_date(i.closes, lang)}"
    else:
        when = t["no_deadline"].lower()
    return (
        f"- **{text('title')}** ({text('body')}, {when})\n  {text('summary')}\n"
        f"  {t['how']} {text('how_to_participate')}\n  {i.url}"
    )


def render_facts(d: dict[str, Any], lang: str, today: date) -> str:
    """The body of one language's section: headed lists in Markdown, Buttondown's native format."""
    t = strings(lang)
    sep = t.get("sep", ": ")
    out = []
    for key, rows in (("sec_closing", d["closing"]), ("sec_new", d["new"]),
                      ("sec_moved", d["moved"]), ("sec_retired", d["retired"])):
        if rows:
            out.append(f"### {t[key]}\n\n" + "\n".join(_entry(i, lang, today, t) for i in rows) + "\n")
    n_open = len(d["open"]) + len(d["closing"]) + len(d["new"]) + len(d["moved"])
    out.append(t["newsletter_open_count"].format(n=n_open, url=SITE_URL))
    out.append(
        f"{t['full_list']}{sep}{SITE_URL}  ·  {t['rss']}{sep}{SITE_URL}/{output_name('feed', '.xml', lang)}"
        f"  ·  {t['calendar']}{sep}{SITE_URL}/{output_name('deadlines', '.ics', lang)}"
    )
    return "\n\n".join(out) + "\n"


# ---- framing (the only part the model writes) ------------------------------------

def _framing_model() -> type[BaseModel]:
    fields: dict[str, Any] = {}
    for lang in LANGS:
        fields[lang_field("subject", lang)] = (str, Field(description=f"Subject line in {_lang_name(lang)}, under 80 characters"))
        fields[lang_field("intro", lang)] = (str, Field(description=f"Two or three sentences in {_lang_name(lang)} introducing this issue"))
    return create_model("Framing", **fields)


def _lang_name(lang: str) -> str:
    return strings(lang).get("language_name_en") or lang


Framing = _framing_model()


def build_system_prompt(site: dict = SITE) -> str:
    cfg = site.get("classifier", {})
    place = cfg.get("place") or site["jurisdiction"]["name"]
    parts = [
        f"""You write the fortnightly email for a public monitor that tracks the channels through which
people in {place} can shape how AI is governed. You are given the issue's facts already laid out:
which channels are new, closing soon, have a moved deadline, or have closed.

Write only the subject line and a short lead for each language. The lead points readers at the
one or two things that matter most this fortnight (a deadline about to pass beats a new listing)
and says plainly that the full details follow. Do not restate every item, invent dates, or add
anything not in the facts. Plain, direct, no marketing tone, no exclamation marks. Write the
{_lang_name(PRIMARY)} first."""
    ]
    for lang in SECONDARY:
        style = (cfg.get("style") or {}).get(lang)
        parts.append(f"For the {_lang_name(lang)} fields: "
                     + (style.strip() if style else f"write idiomatic {_lang_name(lang)}, not a calque of the {_lang_name(PRIMARY)}."))
    return "\n\n".join(parts)


def draft_framing(facts: dict[str, str], today: date) -> BaseModel:
    """One low-effort call: the facts in every language in, subject and lead per language out."""
    import anthropic  # imported here so the offline path (tests, --no-llm) never needs it configured
    client = anthropic.Anthropic()
    body = "\n\n".join(f"=== {_lang_name(x)} facts ===\n{facts[x]}" for x in LANGS)
    resp = client.messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        output_config={"effort": "low"},
        system=build_system_prompt(),
        messages=[{"role": "user", "content": f"Issue date: {today.isoformat()}\n\n{body}"}],
        output_format=Framing,
    )
    assert resp.parsed_output is not None, "model returned no structured output"
    return resp.parsed_output


def fallback_framing(d: dict[str, Any], today: date) -> BaseModel:
    """Stock subject and lead from the strings files, for runs without an API key."""
    data = {}
    for lang in LANGS:
        t = strings(lang)
        data[lang_field("subject", lang)] = t["newsletter_subject"].format(
            title=t["text"]["title"], date=fmt_date(today, lang), new=len(d["new"]), closing=len(d["closing"]))
        data[lang_field("intro", lang)] = t["newsletter_intro"].format(
            new=len(d["new"]), closing=len(d["closing"]), moved=len(d["moved"]), retired=len(d["retired"]), days=CLOSING_SOON_DAYS)
    return Framing(**data)


# ---- compose and post --------------------------------------------------------------

def compose(framing: BaseModel, facts: dict[str, str], today: date) -> tuple[str, str]:
    """One bilingual issue: every language's section in turn, primary first."""
    f = framing.model_dump()
    subject = " / ".join(f[lang_field("subject", x)] for x in LANGS)
    sections = []
    for x in LANGS:
        t = strings(x)
        heading = f"## {t['text']['title']}, {t['week_of']} {fmt_date(today, x)}"
        sections.append(f"{heading}\n\n{f[lang_field('intro', x)]}\n\n{facts[x]}")
    return subject, "\n\n---\n\n".join(sections)


def _post(url: str, headers: dict, payload: dict) -> Any:
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"Buttondown answered {resp.status_code}: {resp.text[:500]}")
    return resp.json()


def post_issue(subject: str, body: str, api_key: str, send: bool, post: Poster = _post) -> Any:
    """Create the email in Buttondown. `about_to_send` goes out at once; `draft` waits for a
    person to press send in the Buttondown dashboard."""
    payload = {"subject": subject, "body": body, "status": "about_to_send" if send else "draft"}
    return post(API_URL, {"Authorization": f"Token {api_key}", "Content-Type": "application/json"}, payload)


def load_state(path: Path = STATE_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def due(state: dict[str, Any], today: date) -> bool:
    last = state.get("last_sent")
    return not last or (today - date.fromisoformat(last)).days >= MIN_DAYS


def run(items: list[Item], state: dict[str, Any], today: date, *, framing_fn: Callable[[dict[str, str], date], BaseModel] | None,
        poster: Callable[[str, str], Any] | None, force: bool = False) -> tuple[str, dict[str, Any]]:
    """Everything but the I/O choices. Returns ('skipped'|'nothing'|'drafted'|'sent-or-posted', new_state).
    `framing_fn` None means the stock framing; `poster` None means compose only (dry run)."""
    if not force and not due(state, today):
        return "skipped", state
    d = delta(items, state.get("items"), today)
    if not has_news(d):
        return "nothing", state
    facts = {x: render_facts(d, x, today) for x in LANGS}
    framing = framing_fn(facts, today) if framing_fn else fallback_framing(d, today)
    subject, body = compose(framing, facts, today)
    new_state = {"last_sent": today.isoformat(), "last_subject": subject, "items": snapshot(items, today)}
    if poster is None:
        return "drafted", {**new_state, "_preview": f"# {subject}\n\n{body}"}
    poster(subject, body)
    return "posted", new_state


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("items", nargs="?", default=str(ROOT / "data" / "items.json"))
    ap.add_argument("--send", action="store_true", help="send at once instead of leaving a Buttondown draft")
    ap.add_argument("--dry-run", action="store_true", help="print the issue; touch neither Buttondown nor the state file")
    ap.add_argument("--force", action="store_true", help="ignore the fortnight guard")
    ap.add_argument("--no-llm", action="store_true", help="use the stock framing even if ANTHROPIC_API_KEY is set")
    args = ap.parse_args(argv)

    today = date.today()
    items = load_items(args.items)
    state = load_state()
    use_llm = bool(os.environ.get("ANTHROPIC_API_KEY")) and not args.no_llm
    send = args.send or os.environ.get("NEWSLETTER_AUTOSEND", "").lower() in ("1", "true", "yes")
    api_key = os.environ.get("BUTTONDOWN_API_KEY", "")

    if not args.dry_run and not api_key:
        print("BUTTONDOWN_API_KEY is not set; nothing sent. Use --dry-run to preview the issue.", file=sys.stderr)
        return 2

    poster = None if args.dry_run else (lambda s, b: post_issue(s, b, api_key, send))
    outcome, new_state = run(items, state, today, framing_fn=draft_framing if use_llm else None,
                             poster=poster, force=args.force)
    if outcome == "skipped":
        print(f"Last issue went out {state['last_sent']}; next one is due {MIN_DAYS} days after. Nothing to do.")
    elif outcome == "nothing":
        print("No new, moved, closing or closed items since the last issue. Nothing to send.")
    elif outcome == "drafted":
        print(new_state["_preview"])
    else:
        STATE_FILE.write_text(json.dumps(new_state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{'Sent' if send else 'Drafted in Buttondown'}: {new_state['last_subject']}")
        print(f"State written to {STATE_FILE.relative_to(ROOT)}; commit it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
