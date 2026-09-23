"""Accumulate meetings across digests into one durable JSON file.

The paper reprints the same meeting in consecutive digests, usually with the
wording of its topic list revised. `Meeting.uid` deliberately keys on
(jurisdiction, body, start) so a reprint updates rather than duplicates -- and
the newest digest wins, because a later printing is the paper's own correction.

The file is the site's data layer. Keeping it as plain JSON on disk (rather than
a database) is what lets the whole site build in CI with no services, and it is
also the natural export if this ever moves behind Django.
"""
import datetime
import json
import os

from .digest import Meeting


def _parse_dt(value):
    return datetime.datetime.fromisoformat(value)


def load(path):
    """Return {uid: Meeting}. A missing or unreadable file yields an empty set."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (ValueError, OSError) as exc:
        print(f"warn: could not read {path} ({exc}); starting empty")
        return {}

    out = {}
    for rec in raw.get("meetings", []):
        try:
            meeting = Meeting(
                jurisdiction=rec["jurisdiction"],
                body=rec["body"],
                start=_parse_dt(rec["start"]),
                location=rec.get("location", ""),
                topics=rec.get("topics", []),
                cancelled=rec.get("cancelled", False),
                source_url=rec.get("source_url", ""),
                source_date=(datetime.date.fromisoformat(rec["source_date"])
                             if rec.get("source_date") else None),
            )
        except (KeyError, ValueError) as exc:
            print(f"warn: skipping malformed meeting record ({exc})")
            continue
        out[meeting.uid] = meeting
    return out


def merge(existing, found):
    """Fold newly parsed meetings into the store.

    A later digest wins on conflict: the paper corrects itself between
    printings, and a cancellation is usually announced in a later issue.
    Returns (merged, added_uids).
    """
    merged = dict(existing)
    added = []
    for meeting in found:
        prior = merged.get(meeting.uid)
        if prior is None:
            merged[meeting.uid] = meeting
            added.append(meeting.uid)
            continue
        if (prior.source_date or datetime.date.min) <= (meeting.source_date
                                                        or datetime.date.min):
            merged[meeting.uid] = meeting
    return merged, added


def save(path, meetings):
    """Write the store, newest meeting last, with a stable key order."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    ordered = sorted(meetings.values(), key=lambda m: (m.start, m.jurisdiction, m.body))
    payload = {
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
                                .isoformat(timespec="seconds"),
        "meetings": [m.to_dict() for m in ordered],
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)          # atomic: a killed run cannot truncate the store
    return ordered


def upcoming(meetings, now=None, days=60):
    """Meetings from `now` forward, soonest first."""
    now = now or datetime.datetime.now()
    horizon = now + datetime.timedelta(days=days)
    return sorted(
        (m for m in meetings.values() if now.date() <= m.start.date() <= horizon.date()),
        key=lambda m: (m.start, m.jurisdiction, m.body),
    )


def past(meetings, now=None, limit=40):
    """Most recent past meetings, newest first -- the 'what just happened' view."""
    now = now or datetime.datetime.now()
    return sorted(
        (m for m in meetings.values() if m.start.date() < now.date()),
        key=lambda m: m.start,
        reverse=True,
    )[:limit]
