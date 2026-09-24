"""Every calendar link on the site must SUBSCRIBE, never download.

A bare link to calendar.ics makes the browser save the file -- seen on Android /
Brave on 2026-09-23 ("Choose where to download: calendar.ics, 1.33 KB") when a
member tapped "Add to your calendar". Someone who imports that file gets a frozen
snapshot that never updates, and believes they are subscribed: the one failure a
"before the vote, not after" site cannot afford. So no page links the file
directly. They link the subscribe page, which offers per-app subscribe actions
(webcal://, Google "add by URL", Outlook "add from web") and the URL to paste.
"""
import datetime
import os
import re
import tempfile
import unittest

from mmwatch import build, feed
from mmwatch.build import Post
from mmwatch.digest import Meeting

ICS = "https://mmwatch.org/calendar.ics"
ICS_ENCODED = "https%3A%2F%2Fmmwatch.org%2Fcalendar.ics"
WEBCAL_ENCODED = "webcal%3A%2F%2Fmmwatch.org%2Fcalendar.ics"
NOW = datetime.datetime(2026, 9, 23, 8, 0)

# Any <a> whose href IS the file: absolute, protocol-relative or relative
# (including ../ from /blog/), any quoting or none, spaces around =, either
# case, a query string or fragment. Not matched, deliberately: the <link
# rel="alternate"> discovery tag in <head> (no download; how clients find the
# feed), webcal:// (hands the address to a calendar app), the Google/Outlook
# deep links whose query strings merely mention the file, and data-href. It is
# applied to <a> in rendered pages and to the RSS item HTML, nothing else;
# GuardRegexTest is its negative control.
ICS_ANCHOR = re.compile(
    r'<a\b[^>]*(?<![\w-])href\s*=\s*["\']?'
    r'(?:(?:https?:)?//[^/"\'\s>]*)?(?:\.\.?/)*/?calendar\.ics'
    r'(?:[?#][^"\'\s>]*)?(?=["\'\s>])', re.I)
DISCOVERY = ('<link rel="alternate" type="text/calendar" '
             'title="MMWatch meetings (calendar)" href="/calendar.ics">')


def meeting(**kw):
    kw.setdefault("jurisdiction", "Marinette County")
    kw.setdefault("body", "Mar-Oco Landfill Committee")
    kw.setdefault("start", NOW + datetime.timedelta(days=7))
    kw.setdefault("location", "Marinette County Resource Center, 1925 Ella Ct.")
    kw.setdefault("topics", ["Solid waste disposal services financial analysis"])
    kw.setdefault("source_url", "https://www.ehextra.com/records/public-meetings/x.html")
    return Meeting(**kw)


class GuardRegexTest(unittest.TestCase):
    """Negative control for the guard itself: a typo in ICS_ANCHOR would make
    every page pass forever. Each list is a plausible template edit."""

    MUST_MATCH = [
        '<a href="/calendar.ics">',
        "<a href='/calendar.ics'>",
        '<a href=/calendar.ics>',
        '<a href = "/calendar.ics">',
        '<A HREF="/CALENDAR.ICS">',
        '<a class="btn" href="calendar.ics">',
        '<a href="./calendar.ics">',
        '<a href="../calendar.ics">',                      # from /blog/
        '<a href="//mmwatch.org/calendar.ics">',           # protocol-relative
        '<a href="https://mmwatch.org/calendar.ics">',
        '<a href="https://mmwatch.org:443/calendar.ics">',
        '<a href="http://mmwatch.org/calendar.ics" download>',
        '<a href="/calendar.ics?v=2">',
        '<a href="/calendar.ics#">',
        '<a class="btn"\n   href="/calendar.ics">',         # multi-line, href second
    ]
    MUST_NOT = [
        '<a href="webcal://mmwatch.org/calendar.ics">',
        '<a href="https://calendar.google.com/calendar/render?cid=https%3A%2F%2Fmmwatch.org%2Fcalendar.ics">',
        '<a href="https://calendar.google.com/calendar/render?cid=webcal%3A%2F%2Fmmwatch.org%2Fcalendar.ics">',
        '<a href="https://outlook.live.com/calendar/0/addfromweb?url=https%3A%2F%2Fmmwatch.org%2Fcalendar.ics&amp;name=MMWatch">',
        '<a href="/subscribe.html#calendar">',
        '<link rel="alternate" type="text/calendar" href="/calendar.ics">',
        '<input readonly value="https://mmwatch.org/calendar.ics">',
        '<a href="/calendar.icsx">',
        '<a href="/calendar.ics.txt">',
        '<a href="/x" data-href="/calendar.ics">',
        '<abbr href="/calendar.ics">',
    ]

    def test_catches_every_direct_link_spelling(self):
        for tag in self.MUST_MATCH:
            with self.subTest(tag=tag):
                self.assertIsNotNone(ICS_ANCHOR.search(tag))

    def test_ignores_subscribe_actions_and_discovery(self):
        for tag in self.MUST_NOT:
            with self.subTest(tag=tag):
                self.assertIsNone(ICS_ANCHOR.search(tag))


class RenderedSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        meetings = {
            "soon": meeting(),
            "recent": meeting(body="County Board", start=NOW - datetime.timedelta(days=7)),
        }
        posts = [Post(slug="test-post", title="Test post", date=NOW.date(),
                      summary="A post.", html="<p>Body.</p>")]
        build.render_site(meetings, posts, out=cls.tmp.name, now=NOW)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def page(self, name):
        with open(os.path.join(self.tmp.name, name), encoding="utf-8") as fh:
            return fh.read()

    def pages(self):
        for root, _, files in os.walk(self.tmp.name):
            for f in files:
                if f.endswith(".html"):
                    rel = os.path.relpath(os.path.join(root, f), self.tmp.name)
                    yield rel, self.page(rel)

    def test_fixture_renders_a_meeting_card_and_a_post(self):
        """Guard against the guard: if the fixture rendered an empty site, the
        per-meeting markup and the post page would never be inspected."""
        self.assertEqual(self.page("index.html").count('class="meeting'), 1)
        meetings = self.page("meetings.html")
        self.assertEqual(meetings.count('class="meeting'), 2, "upcoming AND recent")
        self.assertIn("Recently held", meetings)
        post = self.page(os.path.join("blog", "test-post.html"))
        self.assertIn('<article class="post">', post)
        self.assertIn("<h1>Test post</h1>", post)

    def test_no_page_links_the_ics_file_directly(self):
        for name, html in self.pages():
            with self.subTest(page=name):
                hit = ICS_ANCHOR.search(html)
                self.assertIsNone(hit, hit and hit.group(0))

    def test_every_page_advertises_the_calendar_for_discovery(self):
        """The one safe reference: a <link rel="alternate"> in <head>, next to
        the RSS one, so calendar clients and extensions can still find the feed."""
        for name, html in self.pages():
            with self.subTest(page=name):
                self.assertIn(DISCOVERY, html)

    def test_front_page_calendar_button_goes_to_the_subscribe_page(self):
        self.assertIn('<a class="btn ghost" href="/subscribe.html#calendar">',
                      self.page("index.html"))

    def test_subscribe_page_has_the_calendar_anchor(self):
        self.assertIn('id="calendar"', self.page("subscribe.html"))

    def test_subscribe_page_offers_webcal(self):
        self.assertIn('href="webcal://mmwatch.org/calendar.ics"',
                      self.page("subscribe.html"))

    def test_subscribe_page_offers_google_add_by_url(self):
        """Google's cid= takes the address in webcal:// form. Given https:// it
        attempts the add and fails ("Unable to add calendar - check the url");
        both outcomes were verified by hand on 2026-09-23."""
        html = self.page("subscribe.html")
        self.assertIn("calendar.google.com/calendar/render?cid=" + WEBCAL_ENCODED, html)
        self.assertNotIn("cid=" + ICS_ENCODED, html)

    def test_subscribe_page_names_googles_failure_and_the_way_around_it(self):
        html = self.page("subscribe.html")
        self.assertIn("Unable to add calendar", html)
        self.assertIn("From URL", html)

    def test_subscribe_page_offers_outlook_add_from_web(self):
        html = self.page("subscribe.html")
        self.assertIn("outlook.live.com/calendar/0/addfromweb?url=" + ICS_ENCODED, html)

    def test_subscribe_page_shows_the_url_in_a_readonly_field(self):
        """An input's context menu offers Select All on every phone; inline
        <code> needs a long-press drag across 33 characters."""
        html = self.page("subscribe.html")
        tag = re.search(r'<input\b[^>]*value="%s"[^>]*>' % re.escape(ICS), html)
        self.assertIsNotNone(tag, "no input carries the address")
        self.assertRegex(tag.group(0), r"\breadonly\b")

    def test_android_guidance_is_visible_without_expanding_anything(self):
        """The phone app cannot subscribe by URL; that is where the download
        came from. The person it happened to must see that without opening a
        collapsed section -- and the page must not claim the phone button
        works, because nobody has tested it on a phone."""
        html = self.page("subscribe.html")
        self.assertIn("Android", html)
        self.assertIn('class="cta"', html)
        self.assertIn("<details", html)
        # Above the buttons: an Android reader taps the first thing they see.
        self.assertLess(html.index("Android"), html.index('class="cta"'))
        self.assertLess(html.index("Android"), html.index("<details"))
        self.assertNotIn("works on the phone", html)


class FeedLinksTest(unittest.TestCase):
    def test_rss_items_link_the_subscribe_page_not_the_file(self):
        m = Meeting(jurisdiction="Marinette County", body="Mar-Oco Landfill Committee",
                    start=datetime.datetime(2026, 9, 23, 9, 0),
                    location="Marinette County Resource Center", topics=["Solid waste"])
        out = feed.render([m])
        self.assertIn("https://mmwatch.org/subscribe.html#calendar", out)
        hit = ICS_ANCHOR.search(out)
        self.assertIsNone(hit, hit and hit.group(0))


if __name__ == "__main__":
    unittest.main()
