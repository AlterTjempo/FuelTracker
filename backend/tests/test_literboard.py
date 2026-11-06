import analytics_config as cfg
from services import literboard as lb


def st(hours, name="s"):
    return {"name": name, "hours_with_data": hours}


def test_thin_stations_are_not_ranked_next_to_well_covered_ones():
    stations = [st(100, "full1"), st(95, "full2"), st(30, "thin")]
    ranked, unranked = lb.split_by_coverage(stations)
    assert [s["name"] for s in ranked] == ["full1", "full2"]
    assert [s["name"] for s in unranked] == ["thin"]  # 30 < 50% of the best (100)


def test_absolute_minimum_hours_applies_when_the_window_is_long_enough():
    ranked, unranked = lb.split_by_coverage([st(60), st(cfg.LITERBOARD_MIN_HOURS - 1)])
    assert len(ranked) == 1 and len(unranked) == 1


def test_short_windows_do_not_rank_everyone_out():
    # only 5 hours of data exist in the window; stations with all 5 are fully covered
    ranked, unranked = lb.split_by_coverage([st(5), st(5), st(2)])
    assert len(ranked) == 2 and len(unranked) == 1


def test_no_stations():
    assert lb.split_by_coverage([]) == ([], [])


def test_opening_hours_weighting_changes_the_denominator_only():
    # a station open 12 of 24 hours that was cheapest in 6 of them
    assert (
        lb.cheapest_percentage(6, total_hours=24, station_hours=12, weighted=False)
        == 25.0
    )
    assert (
        lb.cheapest_percentage(6, total_hours=24, station_hours=12, weighted=True)
        == 50.0
    )
    # a station open all the time is unaffected
    assert lb.cheapest_percentage(6, 24, 24, False) == lb.cheapest_percentage(
        6, 24, 24, True
    )
    assert lb.cheapest_percentage(0, 0, 0, True) == 0.0


def test_literboard_thresholds_come_from_the_config_module():
    assert cfg.LITERBOARD_STABILITY_DAYS > 0 and 0 < cfg.LITERBOARD_MIN_DATA_SHARE <= 1
