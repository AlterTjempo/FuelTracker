"""Pure helpers for the Literboard (ranking eligibility and the cheapest-share definition)."""

import analytics_config as cfg


def split_by_coverage(stations: list[dict]) -> tuple[list[dict], list[dict]]:
    """(ranked, unranked): stations with too little data are not ranked next to well-covered ones.

    A station needs at least LITERBOARD_MIN_HOURS hours of data (or all hours that exist,
    if the window is shorter) AND at least LITERBOARD_MIN_DATA_SHARE of the hours of the
    best-covered station.
    """
    if not stations:
        return [], []
    best = max(s["hours_with_data"] for s in stations)
    # The absolute minimum can never exceed what the best-covered station has: in a
    # window with only 5 hours of data, a station with all 5 hours is fully covered.
    minimum = max(
        min(cfg.LITERBOARD_MIN_HOURS, best), cfg.LITERBOARD_MIN_DATA_SHARE * best
    )
    ranked = [s for s in stations if s["hours_with_data"] >= minimum]
    unranked = [s for s in stations if s["hours_with_data"] < minimum]
    return ranked, unranked


def cheapest_percentage(
    cheapest_hours: int, total_hours: int, station_hours: int, weighted: bool
) -> float:
    """Share of hours in which a station was the cheapest.

    Default: relative to all hours with any data in the window.
    Opening-hours weighted: relative to the hours the station itself had data
    (price rows are only stored while a station is open), so a station that
    closes at night is not penalised for the hours it could not be cheapest.
    """
    denominator = station_hours if weighted else total_hours
    return round(cheapest_hours / denominator * 100, 1) if denominator > 0 else 0.0
