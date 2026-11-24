from datetime import date
from app.domain.date_range_resolver import resolve_date_range


def test_resolve_this_year():
    ref = date(2026, 11, 23)
    res = resolve_date_range("Where did I spend the least this year?", reference_date=ref)
    assert res.start_date == date(2026, 1, 1)
    assert res.end_date == date(2026, 11, 23)
    assert res.target_year == 2026


def test_resolve_previous_year():
    ref = date(2026, 11, 23)
    res = resolve_date_range("Where did I spend the most in the previous year?", reference_date=ref)
    assert res.start_date == date(2025, 1, 1)
    assert res.end_date == date(2025, 12, 31)
    assert res.target_year == 2025


def test_resolve_last_year():
    ref = date(2026, 11, 23)
    res = resolve_date_range("What was my spending last year?", reference_date=ref)
    assert res.start_date == date(2025, 1, 1)
    assert res.end_date == date(2025, 12, 31)
    assert res.target_year == 2025


def test_resolve_this_month():
    ref = date(2026, 11, 23)
    res = resolve_date_range("How much did I spend this month?", reference_date=ref)
    assert res.start_date == date(2026, 11, 1)
    assert res.end_date == date(2026, 11, 23)


def test_resolve_last_month():
    ref = date(2026, 11, 23)
    res = resolve_date_range("How much did I spend on shopping last month?", reference_date=ref)
    assert res.start_date == date(2026, 10, 1)
    assert res.end_date == date(2026, 10, 31)


def test_resolve_this_week():
    ref = date(2026, 11, 23)  # Monday
    res = resolve_date_range("How much did I spend this week?", reference_date=ref)
    assert res.start_date == date(2026, 11, 23)
    assert res.end_date == date(2026, 11, 23)


def test_resolve_last_7_days():
    ref = date(2026, 11, 23)
    res = resolve_date_range("What were my expenses for the last 7 days?", reference_date=ref)
    assert res.start_date == date(2026, 11, 16)
    assert res.end_date == date(2026, 11, 23)


def test_resolve_last_30_days():
    ref = date(2026, 11, 23)
    res = resolve_date_range("Summary for last 30 days", reference_date=ref)
    assert res.start_date == date(2026, 10, 24)
    assert res.end_date == date(2026, 11, 23)


def test_resolve_today():
    ref = date(2026, 11, 23)
    res = resolve_date_range("Did I spend anything today?", reference_date=ref)
    assert res.start_date == date(2026, 11, 23)
    assert res.end_date == date(2026, 11, 23)


def test_resolve_yesterday():
    ref = date(2026, 11, 23)
    res = resolve_date_range("How much did I spend yesterday?", reference_date=ref)
    assert res.start_date == date(2026, 11, 22)
    assert res.end_date == date(2026, 11, 22)


def test_resolve_explicit_year():
    ref = date(2026, 11, 23)
    res = resolve_date_range("Did I spend anything on medical expenses in 2025?", reference_date=ref)
    assert res.start_date == date(2025, 1, 1)
    assert res.end_date == date(2025, 12, 31)
    assert res.target_year == 2025


def test_resolve_explicit_month():
    ref = date(2026, 11, 23)
    res = resolve_date_range("Show my expenses for December 2025.", reference_date=ref)
    assert res.start_date == date(2025, 12, 1)
    assert res.end_date == date(2025, 12, 31)
    assert res.target_month == "2025-12"


def test_resolve_multi_month_range():
    ref = date(2026, 11, 23)
    res = resolve_date_range("Give me a complete financial summary from January to November 2026.", reference_date=ref)
    assert res.start_date == date(2026, 1, 1)
    assert res.end_date == date(2026, 11, 30)


def test_resolve_comparison_between_years():
    ref = date(2026, 11, 23)
    res = resolve_date_range("Compare my spending between 2025 and 2026.", reference_date=ref)
    assert res.comparison is not None
    assert res.comparison.period1_start == date(2025, 1, 1)
    assert res.comparison.period1_end == date(2025, 12, 31)
    assert res.comparison.period2_start == date(2026, 1, 1)
    assert res.comparison.period2_end == date(2026, 11, 23)


def test_resolve_comparison_between_months():
    ref = date(2026, 11, 23)
    res = resolve_date_range("Compare my expenses between October and November.", reference_date=ref)
    assert res.comparison is not None
    assert res.comparison.period1_start == date(2026, 10, 1)
    assert res.comparison.period1_end == date(2026, 10, 31)
    assert res.comparison.period2_start == date(2026, 11, 1)
    assert res.comparison.period2_end == date(2026, 11, 30)


def test_resolve_all_time_highest_transaction():
    ref = date(2026, 11, 23)
    res = resolve_date_range("What was my highest expense transaction ever?", reference_date=ref)
    assert res.is_all_time is True
