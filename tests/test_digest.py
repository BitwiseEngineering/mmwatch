"""Parsing the EagleHerald PUBLIC MEETINGS digest into structured meetings.

The digest is the earliest and broadest notice we get: it lists every upcoming
Marinette city/county and Menominee city/county meeting with date, time, room and
subject matter, usually days before the agenda PDF is posted. It is also the only
routine coverage of the City of Menominee, whose own site is Cloudflare-gated.

Its shape is prose, not markup:

    CITY OF MARINETTE * Historic Preservation Committee. Monday, Sept. 21,
    10 a.m., council chambers, City Hall, 1905 Hall Ave. Meridian plate
    monument. Cemetery wall on Mary Street. * Water & Wastewater Utilities
    Commissions. Monday, Sept. 21, 3 p.m., ... MARINETTE COUNTY * Mar-Oco
    Landfill Committee. Wednesday, 9 a.m., ...

Note the two date styles. Most entries carry an explicit "Monday, Sept. 21";
some carry only a weekday ("Wednesday, 9 a.m."), which resolves against the
publication date. Getting that wrong puts a meeting on the calendar a week out,
which is worse than not listing it.
"""
import datetime
import unittest

from mmwatch import digest

PUBLISHED = datetime.date(2026, 9, 20)   # a Sunday

REAL = (
    "CITY OF MARINETTE • Historic Preservation Committee. Monday, Sept. 21, "
    "10 a.m., council chambers, City Hall, 1905 Hall Ave. Meridian plate monument. "
    "Cemetery wall on Mary Street at Forest Home. • Water & Wastewater Utilities "
    "Commissions. Monday, Sept. 21, 3 p.m., council chambers, City Hall, 1905 Hall Ave. "
    "Voltus Distributed Energy Resource agreement. Solids treatment update. "
    "CITY OF MENOMINEE • City Council. Monday, Sept. 21, 6 p.m., council chambers, "
    "City Hall, 2511 10th St. Amendment to marijuana ordinance. 2027-2032 Recreation Plan. "
    "MARINETTE COUNTY • Mar-Oco Landfill Committee. Wednesday, 9 a.m., Marinette County "
    "Resource Center, 1925 Ella Ct., Marinette. Solid waste disposal services financial "
    "analysis. Used or new wheel loader. "
    "Let the news come to you Get any of our free email newsletters"
)


class ParseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meetings = digest.parse(REAL, published=PUBLISHED)

    def test_finds_every_meeting_and_no_phantoms(self):
        self.assertEqual(len(self.meetings), 4)

    def test_jurisdiction_is_carried_down_to_each_meeting(self):
        self.assertEqual(
            [m.jurisdiction for m in self.meetings],
            ["City of Marinette", "City of Marinette",
             "City of Menominee", "Marinette County"],
        )

    def test_body_name_is_separated_from_the_date(self):
        self.assertEqual(self.meetings[0].body, "Historic Preservation Committee")
        self.assertEqual(self.meetings[3].body, "Mar-Oco Landfill Committee")

    def test_explicit_dates_and_times(self):
        self.assertEqual(self.meetings[0].start,
                         datetime.datetime(2026, 9, 21, 10, 0))
        self.assertEqual(self.meetings[1].start,
                         datetime.datetime(2026, 9, 21, 15, 0))
        self.assertEqual(self.meetings[2].start,
                         datetime.datetime(2026, 9, 21, 18, 0))

    def test_a_weekday_only_entry_resolves_forward_from_publication(self):
        """'Wednesday, 9 a.m.' published Sunday 2026-09-20 is 2026-09-23."""
        self.assertEqual(self.meetings[3].start,
                         datetime.datetime(2026, 9, 23, 9, 0))

    def test_location_is_captured(self):
        self.assertIn("1905 Hall Ave", self.meetings[0].location)
        self.assertIn("Ella Ct", self.meetings[3].location)

    def test_topics_are_split_into_items(self):
        self.assertEqual(self.meetings[3].topics,
                         ["Solid waste disposal services financial analysis",
                          "Used or new wheel loader"])

    def test_newsletter_boilerplate_is_not_treated_as_a_topic(self):
        joined = " ".join(t for m in self.meetings for t in m.topics)
        self.assertNotIn("newsletters", joined)
        self.assertNotIn("Let the news", joined)

    def test_uid_is_stable_and_unique(self):
        uids = [m.uid for m in self.meetings]
        self.assertEqual(len(set(uids)), 4)
        again = digest.parse(REAL, published=PUBLISHED)
        self.assertEqual(uids, [m.uid for m in again])


class HalfHourAndEdgeCaseTest(unittest.TestCase):
    def parse_one(self, text, published=PUBLISHED):
        got = digest.parse("CITY OF MENOMINEE • " + text, published=published)
        return got[0] if got else None

    def test_half_past_times(self):
        m = self.parse_one("Parks Committee. Monday, Sept. 21, 5:30 p.m., council chambers.")
        self.assertEqual(m.start, datetime.datetime(2026, 9, 21, 17, 30))

    def test_noon_and_midnight_words_do_not_crash(self):
        m = self.parse_one("Board of Review. Tuesday, Sept. 22, noon, City Hall.")
        self.assertEqual(m.start, datetime.datetime(2026, 9, 22, 12, 0))

    def test_a_meeting_that_rolls_into_next_month(self):
        m = self.parse_one("Council. Thursday, Oct. 1, 6 p.m., chambers.",
                           published=datetime.date(2026, 9, 28))
        self.assertEqual(m.start, datetime.datetime(2026, 10, 1, 18, 0))

    def test_a_weekday_that_matches_publication_day_is_not_pushed_a_week_out(self):
        """Published Sunday, meeting 'Sunday' = today, not next week."""
        m = self.parse_one("Special Session. Sunday, 2 p.m., chambers.")
        self.assertEqual(m.start.date(), datetime.date(2026, 9, 20))

    def test_an_entry_with_no_parseable_time_is_dropped_not_guessed(self):
        """A calendar entry at the wrong time is worse than no entry."""
        self.assertIsNone(self.parse_one("Some Committee. To be announced."))

    def test_cancellation_notices_are_flagged_not_listed_as_meetings(self):
        m = self.parse_one("Cemetery Board. Tuesday, Sept. 22, 4 p.m., City Hall. "
                           "CANCELED.")
        self.assertTrue(m.cancelled)


if __name__ == "__main__":
    unittest.main()


class DateClauseScopingTest(unittest.TestCase):
    """A date or time inside the topic list must not override the meeting's own.

    Caught against the real 2026-09-06 digest: the county Development Committee
    meets Tuesday 9 a.m., but its topics mention travel to a conference on a
    later date, and searching the whole entry moved the meeting a month out. A
    calendar entry on the wrong day is the failure this project cannot afford.
    """

    def one(self, text, published=datetime.date(2026, 9, 6)):
        got = digest.parse("MARINETTE COUNTY • " + text, published=published)
        return got[0] if got else None

    def test_a_date_in_the_topics_does_not_move_the_meeting(self):
        m = self.one(
            "Development Committee. Tuesday, 9 a.m., county board room, Courthouse, "
            "1926 Hall Ave., Marinette. Outside agency reports. 2027 department "
            "budgets. Approve mileage for members to attend a conference Oct. 9."
        )
        self.assertEqual(m.start, datetime.datetime(2026, 9, 8, 9, 0))

    def test_a_time_in_the_topics_does_not_move_the_meeting(self):
        m = self.one(
            "Infrastructure Committee. Wednesday, 9 a.m., county board room. "
            "Discuss shifting the recycling drop-off window to 4 p.m."
        )
        self.assertEqual(m.start, datetime.datetime(2026, 9, 9, 9, 0))

    def test_a_street_abbreviation_does_not_truncate_the_date_clause(self):
        """'Monday, Sept. 21' and '1905 Hall Ave.' both contain '. '."""
        m = digest.parse(
            "CITY OF MARINETTE • Historic Preservation Committee. Monday, Sept. 21, "
            "10 a.m., council chambers, City Hall, 1905 Hall Ave. Meridian plate "
            "monument.",
            published=datetime.date(2026, 9, 20),
        )[0]
        self.assertEqual(m.start, datetime.datetime(2026, 9, 21, 10, 0))
        self.assertIn("1905 Hall Ave", m.location)
        self.assertEqual(m.topics, ["Meridian plate monument"])
