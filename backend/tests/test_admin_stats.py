from datetime import datetime, timedelta, timezone

from services.admin_stats import (
    age_seconds,
    coverage_ratio,
    freshness_status,
    mask_email,
)


def test_mask_email_hides_the_local_part():
    assert mask_email("jane.doe@example.com") == "j***@example.com"
    assert mask_email("broken") == "***"
    assert mask_email("") == "***"


def test_freshness_thresholds():
    assert freshness_status(60, 1800, 7200) == "ok"
    assert freshness_status(3600, 1800, 7200) == "warn"
    assert freshness_status(10000, 1800, 7200) == "error"
    assert freshness_status(None, 1800, 7200) == "error"  # never seen


def test_age_handles_naive_and_aware_timestamps():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert age_seconds(now - timedelta(minutes=5), now) == 300
    assert age_seconds((now - timedelta(minutes=5)).replace(tzinfo=None), now) == 300
    assert age_seconds(None, now) is None


def test_coverage_ratio_is_clamped():
    assert coverage_ratio(48, 96) == 0.5
    assert coverage_ratio(200, 96) == 1.0
    assert coverage_ratio(5, 0) == 0.0
