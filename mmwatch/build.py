"""Build the static site: fetch -> merge -> render.

Run `python -m mmwatch.build` to refresh from the live digests, or
`python -m mmwatch.build --offline` to rebuild pages from the stored data only
(no network), which is what you want while working on templates.

Everything lands in `public/`, which is what gets published. The data file in
`data/meetings.json` is committed, so the site survives a source going dark and
a rebuild is always reproducible.
"""
import argparse
import datetime
import os
import re
import shutil

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import feed as feed_mod
from . import ics as ics_mod
from . import store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "meetings.json")
OUT = os.path.join(ROOT, "public")
TEMPLATES = os.path.join(ROOT, "templates")
STATIC = os.path.join(ROOT, "static")
POSTS = os.path.join(ROOT, "content", "posts")

# Set MMWATCH_MAILCHIMP_ACTION to the form action URL from Mailchimp's embedded
# form (Audience -> Signup forms -> Embedded form). Left unset, the subscribe
# page explains that email is not wired up yet rather than showing a dead form.
MAILCHIMP_ACTION = os.environ.get("MMWATCH_MAILCHIMP_ACTION", "")
# Mailchimp's bot-trap field name: b_<userid>_<listid>. Copy it from the same
# embed snippet; it must match exactly or real signups get dropped as spam.
MAILCHIMP_HONEYPOT = os.environ.get("MMWATCH_MAILCHIMP_HONEYPOT", "")

HORIZON_DAYS = 60
FRONT_PAGE_COUNT = 6


def env():
    return Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


class Post:
    __slots__ = ("slug", "title", "date", "summary", "html")

    def __init__(self, slug, title, date, summary, html):
        self.slug, self.title, self.date = slug, title, date
        self.summary, self.html = summary, html


def load_posts():
    """Read `content/posts/*.md`. Front matter is a few `Key: value` lines."""
    if not os.path.isdir(POSTS):
        return []
    try:
        import markdown
    except ImportError:
        print("warn: markdown not installed; skipping blog posts")
        return []

    posts = []
    for name in sorted(os.listdir(POSTS)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(POSTS, name)
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
        meta, _, body = raw.partition("\n\n")
        fields = {}
        if re.match(r"^[A-Za-z][A-Za-z ]*:", meta.strip()):
            for line in meta.strip().splitlines():
                key, sep, value = line.partition(":")
                if sep:
                    fields[key.strip().lower()] = value.strip()
        else:
            body = raw
        slug = fields.get("slug") or os.path.splitext(name)[0]
        try:
            date = datetime.date.fromisoformat(fields.get("date", ""))
        except ValueError:
            date = datetime.date.fromtimestamp(os.path.getmtime(path))
        posts.append(Post(
            slug=slug,
            title=fields.get("title", slug.replace("-", " ").title()),
            date=date,
            summary=fields.get("summary", ""),
            html=markdown.markdown(body, extensions=["extra"]),
        ))
    posts.sort(key=lambda p: p.date, reverse=True)
    return posts


def refresh(path=DATA, limit=1):
    """Pull recent digests and fold them into the store. Returns (store, added)."""
    from . import digest as digest_mod
    from . import sources

    existing = store.load(path)
    found = []
    try:
        for published, url, text in sources.recent_digests(limit=limit):
            got = digest_mod.parse(text, published=published, source_url=url)
            print(f"  {published}  {len(got):2d} meeting(s)  {url}")
            found.extend(got)
    except Exception as exc:
        # A source going down must not wipe the site; rebuild from stored data.
        print(f"warn: digest refresh failed ({exc}); building from stored data")
        return existing, []

    merged, added = store.merge(existing, found)
    store.save(path, merged)
    return merged, added


def write(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def render_site(meetings, posts, out=OUT, now=None):
    now = now or datetime.datetime.now()
    jenv = env()
    upcoming = store.upcoming(meetings, now=now, days=HORIZON_DAYS)
    recent = store.past(meetings, now=now)
    built_human = now.strftime("%B %-d, %Y at %-I:%M %p")

    common = {
        "built_human": built_human,
        "mailchimp_action": MAILCHIMP_ACTION,
        "mailchimp_honeypot": MAILCHIMP_HONEYPOT,
    }

    write(os.path.join(out, "index.html"), jenv.get_template("index.html").render(
        soon=upcoming[:FRONT_PAGE_COUNT], total_upcoming=len(upcoming),
        posts=posts, **common))
    write(os.path.join(out, "meetings.html"), jenv.get_template("meetings.html").render(
        upcoming=upcoming, past=recent, **common))
    write(os.path.join(out, "subscribe.html"), jenv.get_template("subscribe.html").render(**common))
    write(os.path.join(out, "about.html"), jenv.get_template("about.html").render(**common))
    write(os.path.join(out, "documents.html"), jenv.get_template("documents.html").render(
        documents=[], **common))

    write(os.path.join(out, "blog", "index.html"),
          jenv.get_template("blog_index.html").render(posts=posts, **common))
    for post in posts:
        write(os.path.join(out, "blog", f"{post.slug}.html"),
              jenv.get_template("post.html").render(post=post, **common))

    # Machine-readable outputs. The calendar carries upcoming meetings only --
    # a subscriber does not want last month's agenda reappearing every rebuild.
    write(os.path.join(out, "calendar.ics"), ics_mod.render(upcoming))
    write(os.path.join(out, "feed.xml"), feed_mod.render(upcoming))

    # Static assets and the raw dataset.
    for name in os.listdir(STATIC):
        shutil.copy2(os.path.join(STATIC, name), os.path.join(out, name))
    if os.path.exists(DATA):
        shutil.copy2(DATA, os.path.join(out, "meetings.json"))

    # GitHub Pages: keep Jekyll's hands off, and serve the custom domain.
    write(os.path.join(out, ".nojekyll"), "")
    domain = os.environ.get("MMWATCH_DOMAIN", "mmwatch.org")
    if domain:
        write(os.path.join(out, "CNAME"), domain + "\n")

    write(os.path.join(out, "robots.txt"),
          "User-agent: *\nAllow: /\nSitemap: https://%s/feed.xml\n" % domain)
    return len(upcoming), len(recent)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the MMWatch static site.")
    ap.add_argument("--offline", action="store_true",
                    help="skip the network; rebuild pages from data/meetings.json")
    ap.add_argument("--digests", type=int, default=1,
                    help="how many recent PUBLIC MEETINGS digests to read "
                         "(more than 1 returns previews; see sources.py)")
    args = ap.parse_args(argv)

    if args.offline:
        meetings = store.load(DATA)
        added = []
        print(f"offline: {len(meetings)} meeting(s) from {DATA}")
    else:
        print("fetching recent PUBLIC MEETINGS digests...")
        meetings, added = refresh(limit=args.digests)
        print(f"{len(meetings)} meeting(s) known, {len(added)} new")

    posts = load_posts()
    up, past_n = render_site(meetings, posts)
    print(f"built {OUT}: {up} upcoming, {past_n} recent, {len(posts)} post(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
