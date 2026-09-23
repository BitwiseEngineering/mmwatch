"""Parse the EagleHerald "PUBLIC MEETINGS" digest into structured meetings.

The digest is prose, not markup, and it is the earliest broad notice of what is
being decided locally -- usually days before an agenda PDF is posted, and the only
routine coverage of the City of Menominee (whose own site is Cloudflare-gated).

Shape:

    CITY OF MARINETTE * Body Name. Monday, Sept. 21, 10 a.m., where. Topic. Topic.
                      * Another Body. Wednesday, 9 a.m., where. Topic.
    MARINETTE COUNTY  * ...

Design rule: **never guess a time.** An entry whose time cannot be read is dropped
rather than placed on the calendar at a plausible-looking hour. A wrong time sends
somebody to an empty room, which costs more trust than a missing listing.
"""
import datetime
import hashlib
import re

BULLET = "•"

# Jurisdiction banners, in the capitalisation the paper uses.
JURISDICTIONS = {
    "CITY OF MARINETTE": "City of Marinette",
    "CITY OF MENOMINEE": "City of Menominee",
    "MARINETTE COUNTY": "Marinette County",
    "MENOMINEE COUNTY": "Menominee County",
    "TOWN OF PESHTIGO": "Town of Peshtigo",
    "CITY OF PESHTIGO": "City of Peshtigo",
}

# Trailing site furniture that follows the article text.
_BOILERPLATE = re.compile(
    r"(Let the news come to you|Get any of our free email newsletters|"
    r"Trending Now|Copyright \d{4}|Powered by BLOX|Facebook Twitter WhatsApp)",
    re.I,
)

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday",
             "friday", "saturday", "sunday"]

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_WEEKDAY_RE = re.compile(r"\b(" + "|".join(_WEEKDAYS) + r")\b", re.I)
_MONTHDAY_RE = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sept|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b",
    re.I,
)
# No trailing \b: the token usually ends in "." and is followed by ",", where a
# word boundary cannot match. Tolerates "a.m.", "am", "a. m.", "P.M.".
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?", re.I)
_NOON_RE = re.compile(r"\b(noon|midnight)\b", re.I)
_CANCELLED_RE = re.compile(r"\b(cancell?ed|canceled|postponed)\b", re.I)

# Words whose trailing period is an abbreviation, not a sentence end. Street
# types and month names dominate; both appear mid-clause in every digest.
_ABBREV = {
    "ave", "av", "st", "rd", "dr", "ct", "blvd", "ln", "pl", "hwy", "ste", "apt",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov",
    "dec", "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat",
    "sun", "no", "rm", "mt", "ft", "co", "inc", "jr", "sr",
}

# Narrower set for the location/topics split. Street types are deliberately NOT
# here: the paper writes "1925 Ella Ct., Marinette." (period then comma, which
# never matches a sentence break) but also "1905 Hall Ave. Meridian plate
# monument.", where "Ave." genuinely ends the location. Treating street types as
# abbreviations swallowed the whole topic list.
_ABBREV_LOC = {
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct",
    "nov", "dec", "no", "rm",
}


class Meeting:
    """One scheduled public meeting.

    `start` is naive local time (America/Chicago for both cities -- Menominee
    County, MI sits in the Central zone with Wisconsin, not Eastern).
    """

    __slots__ = ("jurisdiction", "body", "start", "location", "topics",
                 "cancelled", "source_url", "source_date")

    def __init__(self, jurisdiction, body, start, location="", topics=None,
                 cancelled=False, source_url="", source_date=None):
        self.jurisdiction = jurisdiction
        self.body = body
        self.start = start
        self.location = location
        self.topics = topics or []
        self.cancelled = cancelled
        self.source_url = source_url
        self.source_date = source_date

    @property
    def uid(self):
        """Stable identity: same meeting from a later digest must not duplicate.

        Deliberately excludes topics and location -- the paper revises wording
        between printings, and a changed topic list is the same meeting.
        """
        raw = f"{self.jurisdiction}|{self.body}|{self.start:%Y-%m-%dT%H:%M}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def title(self):
        return f"{self.jurisdiction}: {self.body}"

    def to_dict(self):
        return {
            "uid": self.uid,
            "jurisdiction": self.jurisdiction,
            "body": self.body,
            "start": self.start.isoformat(),
            "location": self.location,
            "topics": list(self.topics),
            "cancelled": self.cancelled,
            "source_url": self.source_url,
            "source_date": self.source_date.isoformat() if self.source_date else None,
        }

    def __repr__(self):
        return f"<Meeting {self.start:%Y-%m-%d %H:%M} {self.title}>"


def _resolve_time(chunk):
    """(hour, minute) or None. None means 'do not put this on a calendar'."""
    noon = _NOON_RE.search(chunk)
    if noon:
        return (12, 0) if noon.group(1).lower() == "noon" else (0, 0)
    m = _TIME_RE.search(chunk)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = m.group(3).lower()
    if meridiem == "p" and hour != 12:
        hour += 12
    elif meridiem == "a" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour, minute


def _resolve_date(chunk, published):
    """Explicit 'Sept. 21' wins; else the next named weekday on/after publication.

    Weekday-only entries are the trap: the paper means *this coming* Wednesday,
    so resolving must start at the publication date, never at 'today'.
    """
    md = _MONTHDAY_RE.search(chunk)
    if md:
        key = md.group(1).lower()
        month = _MONTHS.get(key) or _MONTHS.get(key[:3])
        day = int(md.group(2))
        if not month:
            return None
        year = published.year
        # A digest published in late December listing "Jan. 5" means next year.
        if month < published.month - 6:
            year += 1
        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None

    wd = _WEEKDAY_RE.search(chunk)
    if wd:
        target = _WEEKDAYS.index(wd.group(1).lower())
        delta = (target - published.weekday()) % 7
        return published + datetime.timedelta(days=delta)
    return None


def _split_topics(tail):
    """Sentence-ish split of the trailing subject matter."""
    tail = _BOILERPLATE.split(tail)[0]
    parts = re.split(r"(?<=[a-z0-9\)\"'])\.\s+(?=[A-Z0-9])|\.\s*$", tail)
    out = []
    for p in parts:
        if not p:
            continue
        p = p.strip().strip(".").strip()
        # Drop fragments that are just a cancellation marker or too short to mean
        # anything ("A", "TBD").
        if len(p) < 4 or _CANCELLED_RE.fullmatch(p):
            continue
        out.append(p)
    return out


def _first_time_match(text):
    """The earliest clock-time token, whether "9 a.m." or "noon"."""
    found = [m for m in (_TIME_RE.search(text), _NOON_RE.search(text)) if m]
    return min(found, key=lambda m: m.start()) if found else None


def _split_after_location(rest):
    """Split "<location>. <topics>" without breaking on address abbreviations.

    "1925 Ella Ct., Marinette. Solid waste..." must split at "Marinette.", not
    at "Ct.". Sentence end = a period after a word of 3+ letters that is not a
    known abbreviation, followed by a capitalised word.
    """
    for m in re.finditer(r"\.\s+(?=[A-Z0-9])", rest):
        before = rest[:m.start()]
        last = re.search(r"([A-Za-z]+)$", before)
        if last and last.group(1).lower() in _ABBREV_LOC:
            continue
        return rest[:m.start()], "", rest[m.end():]
    return rest, "", ""


def _parse_entry(text, jurisdiction, published, source_url, source_date):
    text = text.strip()
    if not text:
        return None
    text = _BOILERPLATE.split(text)[0].strip()
    if not text:
        return None

    # Body name runs to the first sentence break; the date clause follows.
    head, sep, tail = text.partition(". ")
    if not sep:
        head, tail = text, ""
    body = head.strip().strip(".").strip()
    if not body:
        return None

    # The meeting's own time is the FIRST time token in the entry; the date is
    # whatever precedes it. Scoping matters: topics routinely mention other dates
    # and times ("attend a conference Oct. 9", "shift the window to 4 p.m."), and
    # searching the whole entry let those move the meeting. Splitting on ". "
    # instead does not work either -- "Sept. 21" and "1905 Hall Ave." both
    # contain it.
    tm = _first_time_match(tail)
    if tm is None:
        return None      # never guess -- see module docstring
    time_part = _resolve_time(tail[tm.start():tm.end()])
    date_part = _resolve_date(tail[:tm.start()], published)
    if time_part is None or date_part is None:
        return None

    start = datetime.datetime(date_part.year, date_part.month, date_part.day,
                              time_part[0], time_part[1])

    # Location runs from after the time to the end of that sentence.
    rest = tail[tm.end():].lstrip(" ,")
    loc, _, topics_tail = _split_after_location(rest)
    location = loc.strip().strip(".").strip()
    topics = _split_topics(topics_tail)

    return Meeting(
        jurisdiction=jurisdiction,
        body=body,
        start=start,
        location=location,
        topics=topics,
        cancelled=bool(_CANCELLED_RE.search(text)),
        source_url=source_url,
        source_date=source_date,
    )


def parse(text, published, source_url=""):
    """Return the meetings listed in one digest.

    `published` is the digest's publication date, which anchors weekday-only
    entries. Pass the feed item's date, not today's.
    """
    if isinstance(published, datetime.datetime):
        published = published.date()
    text = " ".join((text or "").split())
    if not text:
        return []

    # Split into jurisdiction sections, keeping the banner that starts each.
    banner = re.compile("(" + "|".join(re.escape(k) for k in JURISDICTIONS) + ")")
    pieces = banner.split(text)
    meetings = []
    current = None
    for piece in pieces:
        if piece in JURISDICTIONS:
            current = JURISDICTIONS[piece]
            continue
        if current is None:
            continue          # preamble before the first banner
        for entry in piece.split(BULLET):
            meeting = _parse_entry(entry, current, published, source_url, published)
            if meeting is not None:
                meetings.append(meeting)
    return meetings
