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
import tempfile
import unittest

from mmwatch import build, feed
from mmwatch.digest import Meeting

ICS = "https://mmwatch.org/calendar.ics"
ICS_ENCODED = "https%3A%2F%2Fmmwatch.org%2Fcalendar.ics"


class RenderedSite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        build.render_site({}, [], out=cls.tmp.name,
                          now=datetime.datetime(2026, 9, 23, 8, 0))

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

    def test_no_page_links_the_ics_file_directly(self):
        for name, html in self.pages():
            with self.subTest(page=name):
                self.assertNotIn('href="/calendar.ics"', html)
                self.assertNotIn(f'href="{ICS}"', html)

    def test_front_page_calendar_button_goes_to_the_subscribe_page(self):
        self.assertIn('href="/subscribe.html#calendar">Add to your calendar',
                      self.page("index.html"))

    def test_subscribe_page_has_the_calendar_anchor(self):
        self.assertIn('id="calendar"', self.page("subscribe.html"))

    def test_subscribe_page_offers_webcal(self):
        self.assertIn('href="webcal://mmwatch.org/calendar.ics"',
                      self.page("subscribe.html"))

    def test_subscribe_page_offers_google_add_by_url(self):
        html = self.page("subscribe.html")
        self.assertIn("calendar.google.com/calendar/render?cid=" + ICS_ENCODED, html)

    def test_subscribe_page_offers_outlook_add_from_web(self):
        html = self.page("subscribe.html")
        self.assertIn("outlook.live.com/calendar/0/addfromweb?url=" + ICS_ENCODED, html)

    def test_subscribe_page_shows_the_url_to_paste(self):
        self.assertIn(f"<code>{ICS}</code>", self.page("subscribe.html"))

    def test_subscribe_page_explains_android(self):
        """The phone app cannot subscribe by URL; that is where the download came from."""
        self.assertIn("Android", self.page("subscribe.html"))


class FeedLinksTest(unittest.TestCase):
    def test_rss_items_link_the_subscribe_page_not_the_file(self):
        m = Meeting(jurisdiction="Marinette County", body="Mar-Oco Landfill Committee",
                    start=datetime.datetime(2026, 9, 23, 9, 0),
                    location="Marinette County Resource Center", topics=["Solid waste"])
        out = feed.render([m])
        self.assertIn("https://mmwatch.org/subscribe.html#calendar", out)
        self.assertNotIn('calendar.ics">Subscribe', out)


if __name__ == "__main__":
    unittest.main()
