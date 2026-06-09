# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime

import pytest

from jrnl import time


def test_default_hour_is_added():
    assert time.parse(
        "2020-06-20", inclusive=False, default_hour=9, default_minute=0, bracketed=False
    ) == datetime.datetime(2020, 6, 20, 9)


def test_default_minute_is_added():
    assert time.parse(
        "2020-06-20",
        inclusive=False,
        default_hour=0,
        default_minute=30,
        bracketed=False,
    ) == datetime.datetime(2020, 6, 20, 0, 30)


@pytest.mark.parametrize(
    "inputs",
    [
        [2000, 2, 29, True],
        [2023, 1, 0, False],
        [2023, 1, 1, True],
        [2023, 4, 31, False],
        [2023, 12, 31, True],
        [2023, 12, 32, False],
        [2023, 13, 1, False],
        [2100, 2, 27, True],
        [2100, 2, 28, True],
        [2100, 2, 29, False],
    ],
)
def test_is_valid_date(inputs):
    year, month, day, expected_result = inputs
    assert time.is_valid_date(year, month, day) == expected_result


def test_date_range_empty():
    dr = time.DateRange()
    assert dr.is_empty
    assert dr.matches(datetime.datetime.now())


def test_date_range_start_end():
    start = datetime.datetime(2023, 1, 1)
    end = datetime.datetime(2023, 12, 31, 23, 59, 59)
    dr = time.DateRange(start=start, end=end)
    assert not dr.is_empty
    assert dr.matches(datetime.datetime(2023, 6, 15))
    assert not dr.matches(datetime.datetime(2022, 12, 31))
    assert not dr.matches(datetime.datetime(2024, 1, 1))


def test_date_range_auto_swap():
    start = datetime.datetime(2023, 12, 31)
    end = datetime.datetime(2023, 1, 1)
    dr = time.DateRange(start=start, end=end)
    assert dr.start == datetime.datetime(2023, 1, 1)
    assert dr.end == datetime.datetime(2023, 12, 31)


def test_date_range_month():
    dr = time.DateRange(month=6)
    assert not dr.is_empty
    assert dr.matches(datetime.datetime(2020, 6, 15))
    assert dr.matches(datetime.datetime(2023, 6, 30))
    assert not dr.matches(datetime.datetime(2023, 5, 31))
    assert not dr.matches(datetime.datetime(2023, 7, 1))


def test_date_range_day():
    dr = time.DateRange(day=15)
    assert not dr.is_empty
    assert dr.matches(datetime.datetime(2020, 1, 15))
    assert dr.matches(datetime.datetime(2023, 12, 15))
    assert not dr.matches(datetime.datetime(2023, 1, 14))
    assert not dr.matches(datetime.datetime(2023, 1, 16))


def test_date_range_year():
    dr = time.DateRange(year=2023)
    assert not dr.is_empty
    assert dr.matches(datetime.datetime(2023, 1, 1))
    assert dr.matches(datetime.datetime(2023, 12, 31, 23, 59, 59))
    assert not dr.matches(datetime.datetime(2022, 12, 31))
    assert not dr.matches(datetime.datetime(2024, 1, 1))


def test_date_range_combined_month_day():
    dr = time.DateRange(month=2, day=29)
    assert dr.matches(datetime.datetime(2020, 2, 29))
    assert not dr.matches(datetime.datetime(2023, 2, 28))
    assert not dr.matches(datetime.datetime(2023, 3, 29))


def test_parse_date_range_no_args():
    dr = time.parse_date_range()
    assert dr.is_empty


def test_parse_date_range_on_date():
    dr = time.parse_date_range(on_date="2023-06-15")
    assert not dr.is_empty
    assert dr.start == datetime.datetime(2023, 6, 15, 0, 0, 0)
    assert dr.end == datetime.datetime(2023, 6, 15, 23, 59, 59)


def test_parse_date_range_on_date_with_default_hour():
    dr = time.parse_date_range(on_date="2023-06-15", default_hour=9, default_minute=30)
    assert dr.start == datetime.datetime(2023, 6, 15, 9, 30, 0)
    assert dr.end == datetime.datetime(2023, 6, 15, 23, 59, 59)


def test_parse_date_range_start_end():
    dr = time.parse_date_range(start_date="2023-01-01", end_date="2023-12-31")
    assert dr.start == datetime.datetime(2023, 1, 1, 0, 0, 0)
    assert dr.end == datetime.datetime(2023, 12, 31, 23, 59, 59)


def test_parse_date_range_month_numeric():
    dr = time.parse_date_range(month="6")
    assert dr.month == 6


def test_parse_date_range_month_name():
    dr = time.parse_date_range(month="january")
    assert dr.month == 1


def test_parse_date_range_month_short_name():
    dr = time.parse_date_range(month="feb")
    assert dr.month == 2


def test_parse_date_range_day():
    dr = time.parse_date_range(day="15")
    assert dr.day == 15


def test_parse_date_range_year():
    dr = time.parse_date_range(year="2023")
    assert dr.year == 2023


def test_parse_date_range_invalid_on_date():
    with pytest.raises(ValueError, match="Invalid date for -on"):
        time.parse_date_range(on_date="not-a-real-date-xyz")


def test_parse_date_range_invalid_start_date():
    with pytest.raises(ValueError, match="Invalid start date for -from"):
        time.parse_date_range(start_date="not-a-real-date-xyz")


def test_parse_date_range_invalid_end_date():
    with pytest.raises(ValueError, match="Invalid end date for -to"):
        time.parse_date_range(end_date="not-a-real-date-xyz")


def test_parse_date_range_invalid_month():
    with pytest.raises(ValueError, match="Invalid month value"):
        time.parse_date_range(month="invalid-month-name")


def test_parse_date_range_invalid_day():
    with pytest.raises(ValueError, match="Invalid day value"):
        time.parse_date_range(day="999")


def test_parse_date_range_invalid_year():
    with pytest.raises(ValueError, match="Invalid year value"):
        time.parse_date_range(year="not-a-year")


def test_parse_date_range_month_out_of_range():
    with pytest.raises(ValueError, match="Invalid month value"):
        time.parse_date_range(month="13")


def test_parse_date_range_day_out_of_range():
    with pytest.raises(ValueError, match="Invalid day value"):
        time.parse_date_range(day="32")
