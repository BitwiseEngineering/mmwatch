"""Emit an iCalendar feed people subscribe to in Google / Apple / Outlook.

Written by hand rather than with a library: RFC 5545 is strict but small, the
output is easier to diff in review, and it keeps the build dependency-free.

Two details that decide whether this actually works in a real calendar app:

* **Line folding.** Lines must not exceed 75 octets; longer ones continue on the
  next line beginning with a single space. Topic lists blow past this constantly,
  and an unfolded file is silently rejected by Outlook.
* **Local time with a VTIMEZONE.** Meetings are wall-clock events in
  America/Chicago. Emitting naive UTC would shift every listing by five or six
  hours depending on the season -- the exact failure that sends someone to an
  empty room.
"""
import datetime

PRODID = "-//MMWatch//Marinette-Menominee civic calendar//EN"
TZID = "America/Chicago"
DURATION_HOURS = 2          # the paper never prints an end time

# Minimal but valid US Central definition, so apps that do not already know the
# zone still place events correctly.
VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/Chicago
X-LIC-LOCATION:America/Chicago
BEGIN:DAYLIGHT
TZOFFSETFROM:-0600
TZOFFSETTO:-0500
TZNAME:CDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0500
TZOFFSETTO:-0600
TZNAME:CST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE"""


def _escape(text):
    """RFC 5545 TEXT escaping. Order matters: backslash first."""
    return (str(text or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\\n")
            .replace("\n", "\\n"))


def _fold(line):
    """Fold to 75 octets, continuing with a leading space.

    Counts bytes, not characters: the digests carry en dashes and curly quotes,
    and folding on character count produces lines that are legal-looking but
    over the octet limit.
    """
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    out, chunk = [], bytearray()
    limit = 75
    for ch in line:
        enc = ch.encode("utf-8")
        if len(chunk) + len(enc) > limit:
            out.append(chunk.decode("utf-8"))
            chunk = bytearray()
            limit = 74          # subsequent lines carry a leading space
        chunk.extend(enc)
    if chunk:
        out.append(chunk.decode("utf-8"))
    return "\r\n ".join(out)


def _event(meeting, stamp):
    summary = meeting.title
    if meeting.cancelled:
        summary = "CANCELLED - " + summary

    description = []
    if meeting.topics:
        description.append("On the agenda:")
        description.extend(f"• {t}" for t in meeting.topics)
    if meeting.source_url:
        if description:
            description.append("")
        description.append(f"Source: {meeting.source_url}")
    description.append("")
    description.append("Listing via MMWatch - https://mmwatch.org")

    end = meeting.start + datetime.timedelta(hours=DURATION_HOURS)
    lines = [
        "BEGIN:VEVENT",
        f"UID:{meeting.uid}@mmwatch.org",
        f"DTSTAMP:{stamp:%Y%m%dT%H%M%SZ}",
        f"DTSTART;TZID={TZID}:{meeting.start:%Y%m%dT%H%M%S}",
        f"DTEND;TZID={TZID}:{end:%Y%m%dT%H%M%S}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(chr(10).join(description))}",
    ]
    if meeting.location:
        lines.append(f"LOCATION:{_escape(meeting.location)}")
    if meeting.source_url:
        lines.append(f"URL:{_escape(meeting.source_url)}")
    # CANCELLED events stay in the feed on purpose: subscribers who already have
    # the event need it struck through, not silently vanished.
    lines.append("STATUS:" + ("CANCELLED" if meeting.cancelled else "CONFIRMED"))
    lines.append("END:VEVENT")
    return lines


def render(meetings, stamp=None):
    """A complete .ics document for `meetings`."""
    stamp = stamp or datetime.datetime.now(datetime.timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:MMWatch - Marinette & Menominee public meetings",
        f"X-WR-TIMEZONE:{TZID}",
        "X-PUBLISHED-TTL:PT12H",
        # RFC 7986 twin of the X- property above: tells a subscribed client
        # how often to re-fetch rather than treating the feed as static.
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        *VTIMEZONE.split("\n"),
    ]
    for meeting in sorted(meetings, key=lambda m: (m.start, m.jurisdiction, m.body)):
        lines.extend(_event(meeting, stamp))
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
