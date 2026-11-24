from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date as Date
from datetime import timedelta

from app.domain.dates import today_ist

MONTH_NAMES: dict[str, int] = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


@dataclass
class ComparisonPeriod:
    period1_start: Date
    period1_end: Date
    period1_label: str
    period2_start: Date
    period2_end: Date
    period2_label: str


@dataclass
class DateRangeResult:
    start_date: Date
    end_date: Date
    label: str
    is_explicit: bool = False
    is_all_time: bool = False
    comparison: ComparisonPeriod | None = None
    target_year: int | None = None
    target_month: str | None = None  # YYYY-MM if specific single month


def get_previous_month_bounds(reference: Date) -> tuple[Date, Date]:
    """Return the (first_day, last_day) of the calendar month prior to reference date."""
    if reference.month == 1:
        prev_year = reference.year - 1
        prev_month = 12
    else:
        prev_year = reference.year
        prev_month = reference.month - 1
    last_day = calendar.monthrange(prev_year, prev_month)[1]
    return Date(prev_year, prev_month, 1), Date(prev_year, prev_month, last_day)


def resolve_date_range(
    question: str | None,
    *,
    request_start: Date | None = None,
    request_end: Date | None = None,
    reference_date: Date | None = None,
) -> DateRangeResult:
    """
    Deterministically converts natural language date expressions into start and end dates.
    Uses dynamic current date (defaults to today_ist()).
    Does not hardcode any specific year.
    """
    today = reference_date or today_ist()
    clean_q = (question or "").strip().lower()

    # 1. Check comparisons between years (e.g. "between 2025 and 2026")
    year_comp_match = re.search(r"\bbetween\s+(20\d{2})\s+and\s+(20\d{2})\b", clean_q)
    if year_comp_match:
        y1, y2 = int(year_comp_match.group(1)), int(year_comp_match.group(2))
        p1_end = today if y1 == today.year else Date(y1, 12, 31)
        p2_end = today if y2 == today.year else Date(y2, 12, 31)
        comp = ComparisonPeriod(
            period1_start=Date(y1, 1, 1),
            period1_end=p1_end,
            period1_label=str(y1),
            period2_start=Date(y2, 1, 1),
            period2_end=p2_end,
            period2_label=str(y2),
        )
        return DateRangeResult(
            start_date=min(Date(y1, 1, 1), Date(y2, 1, 1)),
            end_date=max(p1_end, p2_end),
            label=f"{y1} vs {y2}",
            is_explicit=True,
            comparison=comp,
        )

    # 2. Check comparisons between months (e.g. "between October and November")
    month_comp_match = re.search(
        r"\bbetween\s+([a-z]+)\s+and\s+([a-z]+)\b", clean_q
    )
    if month_comp_match:
        m1_name, m2_name = month_comp_match.group(1), month_comp_match.group(2)
        if m1_name in MONTH_NAMES and m2_name in MONTH_NAMES:
            m1, m2 = MONTH_NAMES[m1_name], MONTH_NAMES[m2_name]
            y1 = today.year
            y2 = today.year
            m1_last = calendar.monthrange(y1, m1)[1]
            m2_last = calendar.monthrange(y2, m2)[1]
            p1_start = Date(y1, m1, 1)
            p1_end = Date(y1, m1, m1_last)
            p2_start = Date(y2, m2, 1)
            p2_end = Date(y2, m2, m2_last)
            comp = ComparisonPeriod(
                period1_start=p1_start,
                period1_end=p1_end,
                period1_label=m1_name.title(),
                period2_start=p2_start,
                period2_end=p2_end,
                period2_label=m2_name.title(),
            )
            return DateRangeResult(
                start_date=min(p1_start, p2_start),
                end_date=max(p1_end, p2_end),
                label=f"{m1_name.title()} vs {m2_name.title()} {today.year}",
                is_explicit=True,
                comparison=comp,
            )

    # 3. Explicit multi-month range: e.g. "from January to November 2026"
    range_match = re.search(
        r"\b(?:from|between)\s+([a-z]+)\s+to\s+([a-z]+)(?:\s+(20\d{2}))?\b",
        clean_q,
    )
    if range_match:
        m1_str, m2_str = range_match.group(1), range_match.group(2)
        if m1_str in MONTH_NAMES and m2_str in MONTH_NAMES:
            m1 = MONTH_NAMES[m1_str]
            m2 = MONTH_NAMES[m2_str]
            yr = int(range_match.group(3)) if range_match.group(3) else today.year
            start_d = Date(yr, m1, 1)
            last_day = calendar.monthrange(yr, m2)[1]
            end_d = Date(yr, m2, last_day)
            return DateRangeResult(
                start_date=start_d,
                end_date=end_d,
                label=f"{m1_str.title()} to {m2_str.title()} {yr}",
                is_explicit=True,
                target_year=yr,
            )

    # 4. "Today"
    if re.search(r"\btoday\b", clean_q):
        return DateRangeResult(
            start_date=today,
            end_date=today,
            label=f"today ({today.isoformat()})",
            is_explicit=True,
        )

    # 5. "Yesterday"
    if re.search(r"\byesterday\b", clean_q):
        yest = today - timedelta(days=1)
        return DateRangeResult(
            start_date=yest,
            end_date=yest,
            label=f"yesterday ({yest.isoformat()})",
            is_explicit=True,
        )

    # 6. "This week" / "current week"
    if re.search(r"\b(?:this|current)\s+week\b", clean_q):
        start_week = today - timedelta(days=today.weekday())
        return DateRangeResult(
            start_date=start_week,
            end_date=today,
            label=f"this week ({start_week.isoformat()} to {today.isoformat()})",
            is_explicit=True,
        )

    # 7. "Last 7 days" / "past 7 days"
    if re.search(r"\b(?:last|past)\s+7\s+days?\b", clean_q):
        start_7 = today - timedelta(days=7)
        return DateRangeResult(
            start_date=start_7,
            end_date=today,
            label=f"last 7 days ({start_7.isoformat()} to {today.isoformat()})",
            is_explicit=True,
        )

    # 8. "Last 30 days" / "past 30 days"
    if re.search(r"\b(?:last|past)\s+30\s+days?\b", clean_q):
        start_30 = today - timedelta(days=30)
        return DateRangeResult(
            start_date=start_30,
            end_date=today,
            label=f"last 30 days ({start_30.isoformat()} to {today.isoformat()})",
            is_explicit=True,
        )

    # 9. "Last month" / "previous month" / "past month"
    if re.search(r"\b(?:previous|last|past|prior)\s+month\b", clean_q):
        p_start, p_end = get_previous_month_bounds(today)
        return DateRangeResult(
            start_date=p_start,
            end_date=p_end,
            label=f"{calendar.month_name[p_start.month]} {p_start.year}",
            is_explicit=True,
            target_year=p_start.year,
            target_month=f"{p_start.year:04d}-{p_start.month:02d}",
        )

    # 10. "This month" / "current month"
    if re.search(r"\b(?:this|current|present)\s+month\b", clean_q):
        m_start = Date(today.year, today.month, 1)
        return DateRangeResult(
            start_date=m_start,
            end_date=today,
            label=f"this month ({calendar.month_name[today.month]} {today.year})",
            is_explicit=True,
            target_year=today.year,
            target_month=f"{today.year:04d}-{today.month:02d}",
        )

    # 11. "This year" / "throughout this year" / "current year"
    if re.search(
        r"\b(?:this|throughout\s+this|current|present)\s+year\b", clean_q
    ):
        y_start = Date(today.year, 1, 1)
        return DateRangeResult(
            start_date=y_start,
            end_date=today,
            label=f"this year ({today.year})",
            is_explicit=True,
            target_year=today.year,
        )

    # 12. "Previous year" / "last year" / "past year"
    if re.search(r"\b(?:previous|last|past|prior)\s+year\b", clean_q):
        prev_yr = today.year - 1
        return DateRangeResult(
            start_date=Date(prev_yr, 1, 1),
            end_date=Date(prev_yr, 12, 31),
            label=f"{prev_yr}",
            is_explicit=True,
            target_year=prev_yr,
        )

    # 13. Explicit single month with year (e.g. "December 2025" or "2025-12")
    iso_month_match = re.search(r"\b(20\d{2})[-/](0[1-9]|1[0-2])\b", clean_q)
    if iso_month_match:
        yr = int(iso_month_match.group(1))
        mn = int(iso_month_match.group(2))
        last_day = calendar.monthrange(yr, mn)[1]
        return DateRangeResult(
            start_date=Date(yr, mn, 1),
            end_date=Date(yr, mn, last_day),
            label=f"{calendar.month_name[mn]} {yr}",
            is_explicit=True,
            target_year=yr,
            target_month=f"{yr:04d}-{mn:02d}",
        )

    for m_name, m_num in MONTH_NAMES.items():
        month_pattern = r"\b" + m_name + r"\s+(20\d{2})\b"
        m_match = re.search(month_pattern, clean_q)
        if m_match:
            yr = int(m_match.group(1))
            last_day = calendar.monthrange(yr, m_num)[1]
            return DateRangeResult(
                start_date=Date(yr, m_num, 1),
                end_date=Date(yr, m_num, last_day),
                label=f"{calendar.month_name[m_num]} {yr}",
                is_explicit=True,
                target_year=yr,
                target_month=f"{yr:04d}-{m_num:02d}",
            )

    # 14. Explicit single month without year (e.g. "for October", "in November")
    for m_name, m_num in MONTH_NAMES.items():
        if re.search(rf"\b{m_name}\b", clean_q):
            yr = today.year
            last_day = calendar.monthrange(yr, m_num)[1]
            return DateRangeResult(
                start_date=Date(yr, m_num, 1),
                end_date=Date(yr, m_num, last_day),
                label=f"{calendar.month_name[m_num]} {yr}",
                is_explicit=True,
                target_year=yr,
                target_month=f"{yr:04d}-{m_num:02d}",
            )

    # 15. Explicit 4-digit year (e.g. "in 2025", "for 2026")
    year_match = re.search(r"\b(20\d{2})\b", clean_q)
    if year_match:
        yr = int(year_match.group(1))
        # If requested year is current year, end at today; if past year, end at Dec 31
        y_end = today if yr == today.year else Date(yr, 12, 31)
        return DateRangeResult(
            start_date=Date(yr, 1, 1),
            end_date=y_end,
            label=f"{yr}",
            is_explicit=True,
            target_year=yr,
        )

    # 16. All-time / ever / overall / entire history / cross-month rankings / lifetime totals
    if re.search(
        r"\b(all\s*time|ever|overall|entire|whole|all\s+my|highest.*ever|which\s+month|highest.*month|month.*highest|average\s+monthly|earn(?:ed)?\s+from|have\s+i\s+spent)\b",
        clean_q,
    ):
        return DateRangeResult(
            start_date=Date(2000, 1, 1),
            end_date=today,
            label="all-time",
            is_explicit=True,
            is_all_time=True,
        )

    # 17. Explicit ISO date (e.g. "2026-11-20")
    iso_date_match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", clean_q)
    if iso_date_match:
        try:
            d = Date.fromisoformat(iso_date_match.group(1))
            return DateRangeResult(
                start_date=d,
                end_date=d,
                label=f"{d.isoformat()}",
                is_explicit=True,
            )
        except ValueError:
            pass

    # 18. Default fallback:
    # If caller provided request_start and request_end, use them
    if request_start and request_end:
        return DateRangeResult(
            start_date=request_start,
            end_date=request_end,
            label=f"{request_start.isoformat()} to {request_end.isoformat()}",
            is_explicit=False,
        )

    # Default to current month through today
    m_start = Date(today.year, today.month, 1)
    return DateRangeResult(
        start_date=m_start,
        end_date=today,
        label=f"{calendar.month_name[today.month]} {today.year}",
        is_explicit=False,
        target_year=today.year,
        target_month=f"{today.year:04d}-{today.month:02d}",
    )
