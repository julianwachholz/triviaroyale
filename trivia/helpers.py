import datetime
import locale
import os

LOCALE = os.environ.get("LC_ALL", "en_US.UTF-8")


def format_number(num, decimal_places=0):
    if not isinstance(num, (int, float)):
        return "n/a"
    locale.setlocale(locale.LC_ALL, LOCALE)
    if decimal_places > 0 and isinstance(num, float):
        return locale.format("%.{}f".format(decimal_places), num, grouping=True)
    return locale.format("%d", num, grouping=True)


def pluralize(s, p):
    return lambda n: s % n if n == 1 else p % n


TIMESINCE_CHUNKS = (
    (60 * 60 * 24 * 365, pluralize("%d year", "%d years")),
    (60 * 60 * 24 * 30, pluralize("%d month", "%d months")),
    (60 * 60 * 24 * 7, pluralize("%d week", "%d weeks")),
    (60 * 60 * 24, pluralize("%d day", "%d days")),
    (60 * 60, pluralize("%d hour", "%d hours")),
    (60, pluralize("%d minute", "%d minutes")),
)


def get_week_tuple(dt):
    """
    Get the start and end date of a date's week.

    :type dt: datetime.date

    """
    return (
        dt - datetime.timedelta(days=dt.weekday()),
        dt + datetime.timedelta(days=6 - dt.weekday()),
    )


def timesince(d, now=None, reversed=False):
    """
    Blatantly copied from:

    https://github.com/django/django/blob/e8e4f978dd4b7a3d0c689c6e3301e3c6f9e50003/django/utils/timesince.py

    """
    # Convert datetime.date to datetime.datetime for comparison.
    if not isinstance(d, datetime.datetime):
        d = datetime.datetime(d.year, d.month, d.day)
    if now and not isinstance(now, datetime.datetime):
        now = datetime.datetime(now.year, now.month, now.day)

    if not now:
        now = datetime.datetime.utcnow()

    delta = (d - now) if reversed else (now - d)
    # ignore microseconds
    since = delta.days * 24 * 60 * 60 + delta.seconds
    if since <= 0:
        # d is in the future compared to now, stop processing.
        return "0 minutes"
    for i, (seconds, name) in enumerate(TIMESINCE_CHUNKS):
        count = since // seconds
        if count != 0:
            break
    result = name(count)
    if i + 1 < len(TIMESINCE_CHUNKS):
        # Now get the second item
        seconds2, name2 = TIMESINCE_CHUNKS[i + 1]
        count2 = (since - (seconds * count)) // seconds2
        if count2 != 0:
            result += ", " + name2(count2)
    return result
