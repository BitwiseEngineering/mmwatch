# MMWatch

The website for **[mmwatch.org](https://mmwatch.org)** — public meetings, agendas
and documents for the City of Marinette and Marinette County, Wisconsin, and the
City of Menominee and Menominee County, Michigan.

A static site, rebuilt daily by GitHub Actions. No server, no database, no
hosting bill, and no subscriber data stored in this repo.

## What it produces

| Output | What it is |
|---|---|
| `index.html`, `meetings.html` | Human-readable listings |
| `calendar.ics` | Subscribe once in Google/Apple/Outlook; updates itself |
| `feed.xml` | RSS — also the input for the Mailchimp newsletter |
| `meetings.json` | The whole dataset, open for reuse |
| `blog/` | Posts from `content/posts/*.md` |

## How it works

```
EagleHerald "PUBLIC MEETINGS" digest
   └─ sources.py   fetch feed + one article
        └─ digest.py   prose → structured Meeting objects
             └─ store.py   merge into data/meetings.json (dedupe by uid)
                  └─ build.py   render public/ (HTML + .ics + .xml + .json)
                       └─ GitHub Pages
```

In CI the live copy of `data/meetings.json` is not on `main` -- `main` requires
pull requests, so the workflow cannot push there (issue #4). `tools/data_branch.sh`
keeps it on an unprotected `data` branch: `restore` overlays it before the build,
`persist` pushes it back only when the meetings changed (a moved `generated_at`
alone is not a change). The copy on `main` is the seed; editing it changes
nothing once the branch exists, and deleting the branch resets the store to it.

`data/meetings.json` is committed on purpose. It is the site's memory: history
accumulates across runs, a source going dark degrades to "rebuild from what we
have" rather than an empty site, and any build is reproducible.

## Relationship to civic-watch

[`civic-watch`](https://github.com/BitwiseEngineering/civic-watch) is the engine:
it crawls the agenda portals, extracts document text (OCR included) and files
alerts on keyword hits. MMWatch is the public face. Keeping them separate means
the watcher stays a small, dependency-light, topic-neutral tool while the website
is free to grow presentation code.

## Running it

```bash
pip install -r requirements.txt

python -m mmwatch.build              # fetch the newest digest, rebuild public/
python -m mmwatch.build --offline    # rebuild from stored data, no network
python -m unittest discover -s tests
```

Then open `public/index.html`, or `python -m http.server -d public 8000`.

### Why it reads only one digest per run

The EagleHerald meters article access by session: the first article read returns
the full text, later ones in the same session return a ~180-character preview
(measured 2026-09-23 — 1,910 chars vs 178). A daily build only needs the newest
digest, and the store accumulates history, so one article a day is both
sufficient and a normal amount of use. `--digests N` exists for a deliberate
backfill; expect previews.

## Parsing rules that matter

The digest is prose, not markup, and two rules keep it honest:

- **Never guess a time.** An entry whose time cannot be read is dropped, not
  placed on the calendar at a plausible hour. A wrong time sends someone to an
  empty room, which costs more trust than a missing listing.
- **Scope the date clause.** A date or time mentioned in a *topic* ("attend a
  conference Oct. 9") must not move the meeting. Caught against the real
  2026-09-06 digest, where it moved a county committee a month out.

Weekday-only entries ("Wednesday, 9 a.m.") resolve forward from the digest's
**publication** date, never from today.

## Configuration

| Env var | Purpose |
|---|---|
| `MMWATCH_MAILCHIMP_ACTION` | Form action URL from Mailchimp's embed snippet. Unset → the subscribe page says email isn't wired up yet instead of showing a dead form. |
| `MMWATCH_MAILCHIMP_HONEYPOT` | Mailchimp's bot-trap field name, `b_<userid>_<listid>`. Must match the embed exactly or real signups are dropped as spam. |
| `MMWATCH_DOMAIN` | Custom domain written to `CNAME` (default `mmwatch.org`). |

Both Mailchimp values are repository secrets in CI. Neither is a credential —
they are public form fields — but they live in secrets so the audience id is not
committed.

## Adding a blog post

Drop a Markdown file in `content/posts/`:

```markdown
Title: What the 2027 county budget actually proposes
Date: 2026-10-05
Slug: 2027-county-budget
Summary: One sentence for the listing and the social preview.

Body text in Markdown.
```

## Editorial commitments

These are load-bearing, not decoration:

- **Every listing links to its source.** Readers check the original, not us.
- **Nothing is paraphrased by a language model.** Detection and extraction are
  deterministic.
- **Absence is not evidence.** If a body publishes no notice we cannot list it,
  and the site says so rather than implying complete coverage.
- **Corrections are prompt and visible.** An error in a transparency project is
  worse than an error elsewhere.
