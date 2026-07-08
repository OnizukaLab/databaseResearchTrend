from __future__ import annotations


DEFAULT_PERIOD_START = 2010
DEFAULT_PERIOD_END = 2025
DEFAULT_PERIOD_SIZE = 5

DEFAULT_PERIOD_WINDOWS = [
    ("2010-2015", 2010, 2014),
    ("2015-2020", 2015, 2019),
    ("2020-2025", 2020, 2025),
]


def build_periods(
    start_year: int = DEFAULT_PERIOD_START,
    end_year: int = DEFAULT_PERIOD_END,
    period_size: int = DEFAULT_PERIOD_SIZE,
) -> list[str]:
    if (start_year, end_year, period_size) == (
        DEFAULT_PERIOD_START,
        DEFAULT_PERIOD_END,
        DEFAULT_PERIOD_SIZE,
    ):
        return [label for label, _, _ in DEFAULT_PERIOD_WINDOWS]

    labels: list[str] = []
    current = start_year
    while current <= end_year:
        labels.append(f"{current}-{min(current + period_size, end_year)}")
        current += period_size
    return labels


def period_of(
    year: int,
    start_year: int = DEFAULT_PERIOD_START,
    end_year: int = DEFAULT_PERIOD_END,
    period_size: int = DEFAULT_PERIOD_SIZE,
) -> str:
    if (start_year, end_year, period_size) == (
        DEFAULT_PERIOD_START,
        DEFAULT_PERIOD_END,
        DEFAULT_PERIOD_SIZE,
    ):
        for label, lower, upper in DEFAULT_PERIOD_WINDOWS:
            if lower <= year <= upper:
                return label
        return "other"

    if year < start_year or year > end_year:
        return "other"
    offset = year - start_year
    bucket_start = start_year + (offset // period_size) * period_size
    bucket_end = min(bucket_start + period_size - 1, end_year)
    return f"{bucket_start}-{bucket_end}"


def period_bounds(period_label: str) -> tuple[int, int]:
    for label, lower, upper in DEFAULT_PERIOD_WINDOWS:
        if period_label == label:
            return lower, upper
    start_text, end_text = period_label.split("-", 1)
    return int(start_text), int(end_text)
