"""The calendar feed has to satisfy real calendar apps, not just look plausible."""
import datetime
import unittest

from mmwatch import ics
from mmwatch.digest import Meeting


def meeting(**kw):
    kw.setdefault("jurisdiction", "Marinette County")
    kw.setdefault("body", "Mar-Oco Landfill Committee")
    kw.setdefault("start", datetime.datetime(2026, 9, 23, 9, 0))
    kw.setdefault("location", "Marinette County Resource Center, 1925 Ella Ct.")
    kw.setdefault("topics", ["Solid waste disposal services financial analysis"])
    return Meeting(**kw)


class IcsTest(unittest.TestCase):
    def render(self, *meetings):
        return ics.render(meetings or [meeting()],
                          stamp=datetime.datetime(2026, 9, 23, 12, 0, 0,
                                                  tzinfo=datetime.timezone.utc))

    def test_document_is_wellformed(self):
        out = self.render()
        self.assertTrue(out.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(out.endswith("END:VCALENDAR\r\n"))
        self.assertEqual(out.count("BEGIN:VEVENT"), out.count("END:VEVENT"))

    def test_crlf_line_endings_throughout(self):
        """RFC 5545 requires CRLF; bare LF is the classic silent-reject bug."""
        out = self.render()
        self.assertNotIn("\n", out.replace("\r\n", ""))

    def test_times_are_local_with_a_tzid_not_naive_utc(self):
        out = self.render()
        self.assertIn("DTSTART;TZID=America/Chicago:20260923T090000", out)
        self.assertIn("BEGIN:VTIMEZONE", out)

    def test_declares_a_refresh_interval(self):
        """RFC 7986 REFRESH-INTERVAL beside the legacy X-PUBLISHED-TTL, so a
        subscribed client knows to poll rather than treat the feed as static."""
        self.assertIn("REFRESH-INTERVAL;VALUE=DURATION:PT12H", self.render())

    def test_no_line_exceeds_75_octets(self):
        long_topics = ["A considerably overlong agenda item about the "
                       "reconstruction of the wastewater treatment facility "
                       "including clarifier replacement and digester work"] * 3
        out = self.render(meeting(topics=long_topics))
        for line in out.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, line[:90])

    def test_folded_continuations_start_with_a_single_space(self):
        out = self.render(meeting(body="X" * 200))
        folded = [l for l in out.split("\r\n") if l.startswith(" ")]
        self.assertTrue(folded)
        for line in folded:
            self.assertFalse(line.startswith("  "))

    def test_special_characters_are_escaped(self):
        out = self.render(meeting(location="Room R121, Marinette; upstairs"))
        self.assertIn("Room R121\\, Marinette\; upstairs", out)

    def test_non_ascii_survives_folding(self):
        """Digest topics carry bullets and dashes; folding must not split a byte."""
        out = self.render(meeting(topics=["Budget — " + "é" * 120]))
        self.assertIn("é", out)
        out.encode("utf-8")

    def test_cancelled_meetings_stay_in_the_feed_marked_cancelled(self):
        out = self.render(meeting(cancelled=True))
        self.assertIn("STATUS:CANCELLED", out)
        self.assertIn("CANCELLED - Marinette County", out)

    def test_uid_is_stable_across_rebuilds(self):
        self.assertEqual(
            [l for l in self.render().split("\r\n") if l.startswith("UID:")],
            [l for l in self.render().split("\r\n") if l.startswith("UID:")],
        )


if __name__ == "__main__":
    unittest.main()
