"""Term arithmetic. An academic year "2026-2027" has Fall 2026, IAP 2027, Spring 2027, Summer 2027."""

SEASONS = ("Fall", "IAP", "Spring", "Summer")          # order within an academic year
_CAL = {"IAP": 0, "Spring": 1, "Summer": 2, "Fall": 3}   # order within a calendar year


def ay_start(ay):
    return int(ay.split("-")[0])


def ay_label(start):
    return "%d-%d" % (start, start + 1)


def next_ay(ay):
    return ay_label(ay_start(ay) + 1)


def term(season, ay):
    """('Spring', '2026-2027') -> 'Spring 2027'."""
    start = ay_start(ay)
    return "%s %d" % (season, start if season == "Fall" else start + 1)


def ay_terms(ay):
    return [term(s, ay) for s in SEASONS]


def ay_of(t):
    season, year = t.split()
    return ay_label(int(year) if season == "Fall" else int(year) - 1)


def key(t):
    """Chronological sort key: IAP 2027 < Spring 2027 < Summer 2027 < Fall 2027."""
    season, year = t.split()
    return (int(year), _CAL[season])


def season(t):
    return t.split()[0]
