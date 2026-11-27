"""When did it happen? Turn "yesterday", "last night", "since Monday", "2 days ago" into
a timestamp (memory.md D17).

Deterministic on purpose (code finds the pattern): the intake LLM only quotes the
user's own words in attributes.onset; this module resolves words to a time. Phrases are
read in the app timezone (IST) and returned as UTC. A date-only phrase means midday.
The result is never in the future, and anything more than a year back is ignored
(that's history, like "since 2019", not the date of this episode).
"""

import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone

from app.core import clock

MAX_BACKDATE = timedelta(days=365)
_MIDDAY = time(12, 0)
_PART_OF_DAY = {
    "morning": time(8, 0),
    "afternoon": time(14, 0),
    "evening": time(19, 0),
    "night": time(22, 0),
}
_COUNTS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "a couple of": 2, "couple of": 2,
    "a few": 3, "few": 3,
}
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4,
    "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11,
    "november": 11, "dec": 12, "december": 12,
}

_N = r"(\d{1,3}|a couple of|couple of|a few|few|an|a|one|two|three|four|five|six|seven|eight|nine|ten)"
_MONTH = r"(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"


def _count(word: str) -> int:
    return int(word) if word.isdigit() else _COUNTS[word]


def _at(day: date, t: time, local_now: datetime) -> datetime:
    return datetime.combine(day, t, tzinfo=local_now.tzinfo)


def _past_date(month: int, day: int, today: date) -> date | None:
    """Most recent occurrence of day/month on or before today."""
    for year in (today.year, today.year - 1):
        try:
            d = date(year, month, day)
        except ValueError:
            return None
        if d <= today:
            return d
    return None


# Each rule: (pattern, resolver(match, local_now) -> local datetime | None).
_Rule = tuple[re.Pattern[str], Callable[[re.Match[str], datetime], datetime | None]]


def _rules() -> list[_Rule]:
    def days_back(n: int, t: time = _MIDDAY):
        return lambda m, now: _at(now.date() - timedelta(days=n), t, now)

    def weekday(m: re.Match[str], now: datetime) -> datetime:
        back = (now.weekday() - _WEEKDAYS.index(m.group(2))) % 7
        if back == 0 and m.group(1) == "last":
            back = 7
        return _at(now.date() - timedelta(days=back), _MIDDAY, now)

    def day_month(day: str, month: str, now: datetime) -> datetime | None:
        d = _past_date(_MONTHS[month], int(day), now.date())
        return _at(d, _MIDDAY, now) if d else None

    rules: list[tuple[str, Callable]] = [
        (r"\bday before yesterday\b", days_back(2)),
        (r"\byesterday (morning|afternoon|evening|night)\b",
         lambda m, now: _at(now.date() - timedelta(days=1), _PART_OF_DAY[m.group(1)], now)),
        (r"\blast night\b", days_back(1, _PART_OF_DAY["night"])),
        (r"\byesterday\b", days_back(1)),
        (r"\bthis (morning|afternoon|evening)\b",
         lambda m, now: _at(now.date(), _PART_OF_DAY[m.group(1)], now)),
        (r"\btonight\b", lambda m, now: _at(now.date(), time(21, 0), now)),
        (rf"\b{_N} (?:hours?|hrs?) (?:ago|back)\b",
         lambda m, now: now - timedelta(hours=_count(m.group(1)))),
        (rf"\b(?:for|since) (?:the )?(?:past |last )?{_N} (?:hours?|hrs?)\b",
         lambda m, now: now - timedelta(hours=_count(m.group(1)))),
        (rf"\b{_N} days? (?:ago|back)\b", lambda m, now: days_back(_count(m.group(1)))(m, now)),
        # "for 3 days" / Indian English "since 3 days": it started 3 days ago.
        (rf"\b(?:for|since) (?:the )?(?:past |last )?{_N} days?\b",
         lambda m, now: days_back(_count(m.group(1)))(m, now)),
        (rf"\b{_N} weeks? (?:ago|back)\b",
         lambda m, now: days_back(7 * _count(m.group(1)))(m, now)),
        (rf"\b(?:for|since) (?:the )?(?:past |last )?{_N} weeks?\b",
         lambda m, now: days_back(7 * _count(m.group(1)))(m, now)),
        (r"\b(?:last|past) week\b", days_back(7)),
        (r"\b(?:(since|on|last|from)\s+)?(" + "|".join(_WEEKDAYS) + r")\b", weekday),
        (rf"\b{_DAY}\s+(?:of\s+)?{_MONTH}\b", lambda m, now: day_month(m.group(1), m.group(2), now)),
        (rf"\b{_MONTH}\s+{_DAY}\b", lambda m, now: day_month(m.group(2), m.group(1), now)),
    ]
    return [(re.compile(p), fn) for p, fn in rules]


_RULES = _rules()


def _scan(text: str, local_now: datetime) -> datetime | None:
    """The earliest phrase in the text wins; at the same position, the longer phrase."""
    hits: list[tuple[int, int, re.Match[str], Callable]] = []
    for pattern, fn in _RULES:
        for m in pattern.finditer(text):
            hits.append((m.start(), -(m.end() - m.start()), m, fn))
    for _start, _neg_len, m, fn in sorted(hits, key=lambda h: (h[0], h[1])):
        result = fn(m, local_now)
        if result is not None:
            return result
    return None


def resolve_onset(
    text: str | None, *, phrase: str | None = None, now: datetime | None = None
) -> datetime | None:
    """UTC time the user said it happened, or None if they didn't say (the caller then
    uses now). `phrase` is the LLM's quote of the onset words and is tried first."""
    ref = clock.to_local(now or clock.now()).astimezone(timezone.utc)  # naive -> UTC
    local_now = clock.to_local(ref)
    for source in (phrase, text):
        if not source:
            continue
        found = _scan(source.lower(), local_now)
        if found is None:
            continue
        found_utc = found.astimezone(timezone.utc)
        if found_utc > ref:
            return ref  # "this evening" said at 10am: it hasn't happened later than now
        if ref - found_utc > MAX_BACKDATE:
            return None
        return found_utc
    return None
