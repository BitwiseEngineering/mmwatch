"""RSS 2.0 feed.

Two jobs. It is the public feed for anyone who wants raw updates, and it is the
input Mailchimp's RSS-to-email campaign reads, so the newsletter needs no code
of our own and no subscriber list in this repo.

That second job sets the shape: Mailchimp sends one email per campaign run and
includes the items published since the last send, so an item must be
self-contained. Each entry therefore carries the full meeting detail, not a
teaser linking back.
"""
import datetime
import html
import xml.sax.saxutils as saxutils

SITE = "https://mmwatch.org"


def _rfc822(dt):
    if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        dt = datetime.datetime(dt.year, dt.month, dt.day)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")


def _cdata(text):
    """Wrap HTML for an RSS description, neutralising any nested terminator."""
    return "<![CDATA[" + str(text).replace("]]>", "]]&gt;") + "]]>"


def _meeting_html(meeting):
    parts = [
        f"<p><strong>{html.escape(meeting.jurisdiction)}</strong><br>",
        f"{html.escape(meeting.body)}</p>",
        f"<p><strong>When:</strong> {meeting.start:%A, %B %-d, %Y at %-I:%M %p}</p>",
    ]
    if meeting.location:
        parts.append(f"<p><strong>Where:</strong> {html.escape(meeting.location)}</p>")
    if meeting.cancelled:
        parts.insert(0, "<p><strong>This meeting has been cancelled.</strong></p>")
    if meeting.topics:
        parts.append("<p><strong>On the agenda:</strong></p><ul>")
        parts.extend(f"<li>{html.escape(t)}</li>" for t in meeting.topics)
        parts.append("</ul>")
    if meeting.source_url:
        parts.append(
            f'<p><a href="{html.escape(meeting.source_url)}">Source listing</a></p>')
    parts.append(
        f'<p><a href="{SITE}/meetings.html">All upcoming meetings</a> · '
        f'<a href="{SITE}/calendar.ics">Subscribe in your calendar</a></p>')
    return "".join(parts)


def _item(meeting):
    title = f"{meeting.start:%a %b %-d} · {meeting.title}"
    if meeting.cancelled:
        title = "CANCELLED: " + title
    return f"""  <item>
    <title>{saxutils.escape(title)}</title>
    <link>{SITE}/meetings.html#{meeting.uid}</link>
    <guid isPermaLink="false">mmwatch-meeting-{meeting.uid}</guid>
    <pubDate>{_rfc822(meeting.source_date or meeting.start)}</pubDate>
    <description>{_cdata(_meeting_html(meeting))}</description>
  </item>"""


def render(meetings, built=None, limit=50):
    """Feed of upcoming meetings, soonest first."""
    built = built or datetime.datetime.now(datetime.timezone.utc)
    ordered = sorted(meetings, key=lambda m: (m.start, m.jurisdiction, m.body))[:limit]
    items = "\n".join(_item(m) for m in ordered)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>MMWatch — Marinette &amp; Menominee public meetings</title>
  <link>{SITE}/</link>
  <atom:link href="{SITE}/feed.xml" rel="self" type="application/rss+xml"/>
  <description>Upcoming city and county meetings in Marinette, Wisconsin and Menominee, Michigan — what is being decided, when, and where.</description>
  <language>en-us</language>
  <lastBuildDate>{_rfc822(built)}</lastBuildDate>
  <ttl>720</ttl>
{items}
</channel>
</rss>
"""
