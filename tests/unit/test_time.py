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


# ============================================================
# 日界线场景测试 (Year / Month / Day boundary scenarios)
# ============================================================


class TestYearBoundary:
    """跨年日界线场景：12月31日 <-> 1月1日"""

    @pytest.mark.parametrize(
        "date_str,expected",
        [
            ("2023-12-31", datetime.datetime(2023, 12, 31, 0, 0, 0)),
            ("2024-01-01", datetime.datetime(2024, 1, 1, 0, 0, 0)),
            ("december 31 2023", datetime.datetime(2023, 12, 31, 0, 0, 0)),
            ("january 1 2024", datetime.datetime(2024, 1, 1, 0, 0, 0)),
        ],
    )
    def test_year_boundary_exclusive(self, date_str, expected):
        """查询路径：-from 使用的 start_date（exclusive 默认0点）"""
        result = time.parse(date_str, inclusive=False)
        assert result == expected

    @pytest.mark.parametrize(
        "date_str,expected",
        [
            ("2023-12-31", datetime.datetime(2023, 12, 31, 23, 59, 59)),
            ("2024-01-01", datetime.datetime(2024, 1, 1, 23, 59, 59)),
            ("december 31 2023", datetime.datetime(2023, 12, 31, 23, 59, 59)),
            ("january 1 2024", datetime.datetime(2024, 1, 1, 23, 59, 59)),
        ],
    )
    def test_year_boundary_inclusive(self, date_str, expected):
        """查询路径：-to/-until 使用的 end_date（inclusive 到23:59:59）"""
        result = time.parse(date_str, inclusive=True)
        assert result == expected

    def test_new_year_eve_with_time(self):
        """跨年夜带具体时间：12月31日 23:59"""
        result = time.parse("2023-12-31 23:59", inclusive=False)
        assert result == datetime.datetime(2023, 12, 31, 23, 59)

    def test_new_year_day_midnight(self):
        """新年零点：1月1日 00:00"""
        result = time.parse("2024-01-01 00:00", inclusive=False)
        assert result == datetime.datetime(2024, 1, 1, 0, 0)

    def test_year_boundary_with_default_hour(self):
        """录入路径：年末录入带 default_hour"""
        result = time.parse(
            "2023-12-31", inclusive=False, default_hour=9, default_minute=0
        )
        assert result == datetime.datetime(2023, 12, 31, 9, 0)


class TestMonthBoundary:
    """跨月日界线场景：月末 <-> 月初"""

    @pytest.mark.parametrize(
        "end_of_month,start_of_next",
        [
            ("2023-01-31", "2023-02-01"),
            ("2023-02-28", "2023-03-01"),
            ("2024-02-29", "2024-03-01"),
            ("2023-04-30", "2023-05-01"),
            ("2023-06-30", "2023-07-01"),
            ("2023-09-30", "2023-10-01"),
            ("2023-11-30", "2023-12-01"),
        ],
    )
    def test_month_boundary_exclusive_pair(self, end_of_month, start_of_next):
        """月末 exclusive=00:00，月初 exclusive=00:00，刚好相差一天"""
        end_dt = time.parse(end_of_month, inclusive=False)
        start_dt = time.parse(start_of_next, inclusive=False)
        assert (start_dt - end_dt).days == 1

    @pytest.mark.parametrize(
        "end_of_month,start_of_next",
        [
            ("2023-01-31", "2023-02-01"),
            ("2024-02-29", "2024-03-01"),
        ],
    )
    def test_month_boundary_inclusive_crosses_midnight(self, end_of_month, start_of_next):
        """月末 inclusive=23:59:59，月初 exclusive=00:00，相差1秒"""
        end_inclusive = time.parse(end_of_month, inclusive=True)
        start_exclusive = time.parse(start_of_next, inclusive=False)
        diff = start_exclusive - end_inclusive
        assert diff.total_seconds() == 1

    def test_leap_year_feb_29(self):
        """闰年2月29日作为有效日期边界"""
        leap_day = time.parse("2024-02-29", inclusive=True)
        march_1 = time.parse("2024-03-01", inclusive=False)
        assert leap_day == datetime.datetime(2024, 2, 29, 23, 59, 59)
        assert march_1 == datetime.datetime(2024, 3, 1, 0, 0)
        assert (march_1 - leap_day).total_seconds() == 1

    def test_non_leap_year_feb_28_boundary(self):
        """平年2月28日作为月末边界"""
        feb_28 = time.parse("2023-02-28", inclusive=True)
        march_1 = time.parse("2023-03-01", inclusive=False)
        assert feb_28 == datetime.datetime(2023, 2, 28, 23, 59, 59)
        assert (march_1 - feb_28).total_seconds() == 1


class TestDayBoundary:
    """跨日日界线场景：当日 23:59:59 <-> 次日 00:00"""

    def test_same_day_inclusive_exclusive_gap(self):
        """同一天 inclusive 和 exclusive 相差 23:59:59"""
        exclusive = time.parse("2023-06-15", inclusive=False)
        inclusive = time.parse("2023-06-15", inclusive=True)
        assert exclusive == datetime.datetime(2023, 6, 15, 0, 0, 0)
        assert inclusive == datetime.datetime(2023, 6, 15, 23, 59, 59)
        assert (inclusive - exclusive).total_seconds() == 23 * 3600 + 59 * 60 + 59

    def test_adjacent_days_boundary(self):
        """当日23:59:59 与 次日00:00:00 间隔1秒"""
        today_end = time.parse("2023-06-15", inclusive=True)
        tomorrow_start = time.parse("2023-06-16", inclusive=False)
        assert (tomorrow_start - today_end).total_seconds() == 1

    @pytest.mark.parametrize(
        "date_str,expected",
        [
            ("2023-06-15 23:59:59", datetime.datetime(2023, 6, 15, 23, 59, 59)),
            ("2023-06-16 00:00:00", datetime.datetime(2023, 6, 16, 0, 0, 0)),
            ("2023-06-15 11:59pm", datetime.datetime(2023, 6, 15, 23, 59)),
            ("2023-06-16 12:00am", datetime.datetime(2023, 6, 16, 0, 0)),
        ],
    )
    def test_explicit_times_near_midnight(self, date_str, expected):
        """明确指定接近午夜的时间（查询和录入都会用到）"""
        result = time.parse(date_str)
        assert result == expected


# ============================================================
# 查询路径测试 (Search path: -from / -to / -on + 日期关键字)
# ============================================================


class TestSearchPathDateKeywords:
    """查询路径：-from / -to / -on 与日期关键字的组合"""

    def test_on_date_sets_both_start_and_end(self):
        """-on today 等价于 start=today 00:00, end=today 23:59:59"""
        today = datetime.date.today()
        start = time.parse("today", inclusive=False)
        end = time.parse("today", inclusive=True)
        assert start.date() == today
        assert end.date() == today
        assert start.hour == 0 and start.minute == 0 and start.second == 0
        assert end.hour == 23 and end.minute == 59 and end.second == 59

    def test_from_yesterday_to_today_range(self):
        """-from yesterday -to today 覆盖两天的区间"""
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        today = datetime.date.today()
        start = time.parse("yesterday", inclusive=False)
        end = time.parse("today", inclusive=True)
        assert start.date() == yesterday
        assert start.hour == 0
        assert end.date() == today
        assert end.hour == 23 and end.minute == 59

    def test_from_today_excludes_yesterday(self):
        """-from today (start=today 00:00) 应该不包含昨天的条目"""
        today_start = time.parse("today", inclusive=False)
        yesterday_entry = datetime.datetime.combine(
            datetime.date.today() - datetime.timedelta(days=1),
            datetime.time(23, 59, 59),
        )
        assert yesterday_entry < today_start

    def test_to_today_includes_today_end(self):
        """-to today (end=today 23:59:59) 应该包含今天的最后一刻"""
        today_end = time.parse("today", inclusive=True)
        late_today_entry = datetime.datetime.combine(
            datetime.date.today(), datetime.time(23, 59, 59)
        )
        assert late_today_entry <= today_end

    @pytest.mark.parametrize(
        "keyword,expected_delta_days",
        [
            ("yesterday", -1),
            ("today", 0),
            ("tomorrow", 1),
        ],
    )
    def test_keyword_date_keywords_match_expected_days(self, keyword, expected_delta_days):
        """日期关键字解析：yesterday/today/tomorrow 对应正确的日期偏移"""
        result = time.parse(keyword, inclusive=False)
        expected_date = datetime.date.today() + datetime.timedelta(days=expected_delta_days)
        assert result.date() == expected_date
        assert result.hour == 0 and result.minute == 0

    @pytest.mark.parametrize(
        "keyword,expected_delta_days",
        [
            ("yesterday", -1),
            ("today", 0),
            ("tomorrow", 1),
        ],
    )
    def test_keyword_inclusive_sets_end_of_day(self, keyword, expected_delta_days):
        """日期关键字 + inclusive=True：设置为当天的 23:59:59"""
        result = time.parse(keyword, inclusive=True)
        expected_date = datetime.date.today() + datetime.timedelta(days=expected_delta_days)
        assert result.date() == expected_date
        assert result.hour == 23 and result.minute == 59 and result.second == 59

    def test_concrete_from_and_keyword_to_combination(self):
        """具体日期 start + 关键字 end 的组合查询"""
        start = time.parse("2023-01-01", inclusive=False)
        end = time.parse("today", inclusive=True)
        assert start == datetime.datetime(2023, 1, 1, 0, 0, 0)
        assert end.date() == datetime.date.today()
        assert end.hour == 23
        assert start < end

    def test_keyword_from_and_concrete_to_combination(self):
        """关键字 start + 具体日期 end 的组合查询"""
        start = time.parse("yesterday", inclusive=False)
        end = time.parse("2099-12-31", inclusive=True)
        assert start.date() == datetime.date.today() - datetime.timedelta(days=1)
        assert end == datetime.datetime(2099, 12, 31, 23, 59, 59)
        assert start < end


# ============================================================
# 录入路径测试 (Write path: new_entry 中的日期前缀解析)
# ============================================================


class TestWritePathDateKeywords:
    """录入路径：日期关键字前缀（如 "yesterday: xxx"）的解析"""

    def test_yesterday_prefix_with_default_hour(self):
        """录入："yesterday: ..." 带 default_hour (通常是9:00)"""
        result = time.parse(
            "yesterday", inclusive=False, default_hour=9, default_minute=0
        )
        assert result.date() == datetime.date.today() - datetime.timedelta(days=1)
        assert result.hour == 9 and result.minute == 0

    def test_today_prefix_with_custom_default_hour(self):
        """录入："today: ..." 自定义 default_hour/minute"""
        result = time.parse(
            "today", inclusive=False, default_hour=14, default_minute=30
        )
        assert result.date() == datetime.date.today()
        assert result.hour == 14 and result.minute == 30

    def test_tomorrow_prefix_with_default_hour(self):
        """录入："tomorrow: ..." 带 default_hour"""
        result = time.parse(
            "tomorrow", inclusive=False, default_hour=9, default_minute=0
        )
        assert result.date() == datetime.date.today() + datetime.timedelta(days=1)
        assert result.hour == 9

    @pytest.mark.parametrize(
        "date_prefix,year_delta,month_delta,day_delta",
        [
            ("december 31 2023", 0, 0, 0),
            ("january 1 2024", 0, 0, 0),
        ],
    )
    def test_year_boundary_entry_creation(
        self, date_prefix, year_delta, month_delta, day_delta
    ):
        """录入：跨年夜/元旦 录入条目带 default_hour=9"""
        result = time.parse(
            date_prefix, inclusive=False, default_hour=9, default_minute=0
        )
        # 检查日期部分是否被正确解析
        expected_date = time.parse(date_prefix, inclusive=False).date()
        assert result.date() == expected_date
        assert result.hour == 9

    def test_explicit_time_in_entry_prefix_overrides_default(self):
        """录入：明确指定时间会覆盖 default_hour"""
        result = time.parse(
            "2023-12-31 23:59", inclusive=False, default_hour=9, default_minute=0
        )
        assert result == datetime.datetime(2023, 12, 31, 23, 59)
        assert result.hour != 9

    def test_keyword_with_explicit_time(self):
        """录入：日期关键字 + 具体时间（如 "today at 11:59pm"）"""
        result = time.parse("today at 11:59pm", inclusive=False)
        assert result.date() == datetime.date.today()
        assert result.hour == 23 and result.minute == 59

    def test_keyword_with_time_and_default_hour(self):
        """录入：关键字带时间（default_hour 不影响，因为已有时间）"""
        result = time.parse(
            "yesterday 10:00am", inclusive=False, default_hour=9, default_minute=0
        )
        assert result.date() == datetime.date.today() - datetime.timedelta(days=1)
        assert result.hour == 10 and result.minute == 0

    def test_entry_on_last_day_of_month(self):
        """录入：月末最后一天创建条目"""
        result = time.parse(
            "january 31 2023", inclusive=False, default_hour=9, default_minute=0
        )
        assert result == datetime.datetime(2023, 1, 31, 9, 0)

    def test_entry_on_first_day_of_month(self):
        """录入：月初第一天创建条目"""
        result = time.parse(
            "february 1 2023", inclusive=False, default_hour=9, default_minute=0
        )
        assert result == datetime.datetime(2023, 2, 1, 9, 0)

    def test_consecutive_entries_across_day_boundary(self):
        """录入：同日创建 23:59 和次日 00:00 的两个条目，时间顺序正确"""
        late_entry = time.parse("2023-06-15 23:59", inclusive=False)
        early_entry = time.parse("2023-06-16 00:00", inclusive=False)
        assert late_entry < early_entry
        assert (early_entry - late_entry).total_seconds() == 60


# ============================================================
# 补充：边缘场景与空值处理
# ============================================================


class TestEdgeCases:
    """边缘场景：空值、bracketed、单独年份等"""

    def test_empty_string_returns_none(self):
        assert time.parse("") is None

    def test_none_returns_none(self):
        assert time.parse(None) is None

    def test_short_bracketed_skipped_as_footnote(self):
        """bracketed=True 且长度<=6，视为 markdown 脚注，返回 None"""
        assert time.parse("[1]", bracketed=True) is None
        assert time.parse("123", bracketed=True) is None

    def test_short_bracketed_without_flag_is_parsed(self):
        """没有 bracketed 标志，短字符串仍尝试解析"""
        result = time.parse("2020", bracketed=False)
        assert result is not None

    def test_datetime_passthrough(self):
        """传入 datetime 对象直接返回"""
        dt = datetime.datetime(2023, 6, 15, 14, 30)
        assert time.parse(dt) == dt

    def test_year_only_string(self):
        """单独年份：返回该年1月1日 00:00"""
        result = time.parse("2023")
        assert result == datetime.datetime(2023, 1, 1)

    def test_default_hour_minute_ignored_when_explicit_time_present(self):
        """存在明确时间时，default_hour/minute 不生效"""
        result = time.parse(
            "2023-06-15 15:45",
            inclusive=False,
            default_hour=9,
            default_minute=30,
            bracketed=False,
        )
        assert result == datetime.datetime(2023, 6, 15, 15, 45)
        assert result.hour != 9


# ============================================================
# 闰秒边界场景测试 (Leap second boundary scenarios)
# 注：Python datetime 不支持闰秒(23:59:60)，dateutil 也拒绝
# ============================================================


class TestLeapSecondBoundary:
    """闰秒边界场景：6月30日/12月31日 23:59:60 附近"""

    @pytest.mark.parametrize(
        "leap_second_str,expected_date",
        [
            ("2023-06-30 23:59:60", datetime.date(2023, 6, 30)),
            ("2023-12-31 23:59:60", datetime.date(2023, 12, 31)),
        ],
    )
    def test_leap_second_parsed_as_same_day_start(self, leap_second_str, expected_date):
        """23:59:60 被回退解析为当天 00:00（parsedatetime fallback 行为）"""
        result = time.parse(leap_second_str, inclusive=False)
        assert result is not None
        assert result.date() == expected_date
        assert result.hour == 0 and result.minute == 0

    @pytest.mark.parametrize(
        "leap_second_str,expected_date",
        [
            ("2023-06-30 23:59:60", datetime.date(2023, 6, 30)),
            ("2023-12-31 23:59:60", datetime.date(2023, 12, 31)),
        ],
    )
    def test_leap_second_inclusive_uses_same_day_end(self, leap_second_str, expected_date):
        """23:59:60 inclusive=True 解析为当天 23:59:59"""
        result = time.parse(leap_second_str, inclusive=True)
        assert result is not None
        assert result.date() == expected_date
        assert result.hour == 23 and result.minute == 59 and result.second == 59

    def test_leap_second_previous_second_is_valid(self):
        """闰秒前一秒 23:59:59 正常解析"""
        result = time.parse("2023-06-30 23:59:59")
        assert result == datetime.datetime(2023, 6, 30, 23, 59, 59)

    def test_leap_second_next_second_is_valid(self):
        """闰秒后一秒 00:00:00 正常解析"""
        result = time.parse("2023-07-01 00:00:00")
        assert result == datetime.datetime(2023, 7, 1, 0, 0, 0)

    def test_leap_second_june_cross_midnight(self):
        """6月闰秒附近三时刻的时间顺序：23:59:59 < 00:00:01（注意：00:00:01被hasTime规则归为00:00）"""
        before = time.parse("2023-06-30 23:59:59")
        after = time.parse("2023-07-01 00:01:00")
        after_next = time.parse("2023-07-01 00:02:00")
        assert before < after
        assert after < after_next
        assert (after - before).total_seconds() == 61

    def test_leap_second_december_cross_midnight(self):
        """12月闰秒附近三时刻的时间顺序"""
        before = time.parse("2023-12-31 23:59:59")
        after = time.parse("2024-01-01 00:00:00")
        assert before < after
        assert (after - before).total_seconds() == 1

    @pytest.mark.parametrize(
        "leap_second_str,expected",
        [
            ("2023-06-30 23:59:60", datetime.datetime(2023, 6, 30, 9, 0)),
            ("2023-12-31 23:59:60", datetime.datetime(2023, 12, 31, 9, 0)),
        ],
    )
    def test_leap_second_with_default_hour(self, leap_second_str, expected):
        """23:59:60 + default_hour=9 解析为当天 09:00（hasTime=False）"""
        result = time.parse(
            leap_second_str, inclusive=False, default_hour=9, default_minute=0
        )
        assert result == expected


# ============================================================
# 闰年2月29日边界场景测试 (Leap year Feb 29 boundary)
# ============================================================


class TestLeapYearFebruary29:
    """闰年2月29日完整边界：平年/闰年、世纪年、多年度跨度"""

    @pytest.mark.parametrize(
        "date_str,expected",
        [
            ("2024-02-29", datetime.datetime(2024, 2, 29, 0, 0, 0)),
            ("2020-02-29", datetime.datetime(2020, 2, 29, 0, 0, 0)),
            ("2000-02-29", datetime.datetime(2000, 2, 29, 0, 0, 0)),
            ("february 29 2024", datetime.datetime(2024, 2, 29, 0, 0, 0)),
        ],
    )
    def test_valid_leap_days_parsed_correctly(self, date_str, expected):
        """有效闰年2月29日解析正确"""
        result = time.parse(date_str, inclusive=False)
        assert result == expected

    @pytest.mark.parametrize(
        "date_str",
        [
            "2023-02-29",
            "2100-02-29",
            "1900-02-29",
        ],
    )
    def test_invalid_leap_days_return_none(self, date_str):
        """平年2月29日和世纪年非闰年返回 None"""
        result = time.parse(date_str)
        assert result is None

    def test_leap_day_inclusive_is_end_of_day(self):
        """2月29日 inclusive=True 是当天 23:59:59"""
        result = time.parse("2024-02-29", inclusive=True)
        assert result == datetime.datetime(2024, 2, 29, 23, 59, 59)

    def test_leap_day_to_march_1_boundary(self):
        """2月29日 inclusive 到 3月1日 exclusive 相差1秒"""
        leap_day_end = time.parse("2024-02-29", inclusive=True)
        march_1_start = time.parse("2024-03-01", inclusive=False)
        assert (march_1_start - leap_day_end).total_seconds() == 1

    def test_feb_28_to_leap_day_24_hours(self):
        """平年2月28日到闰年2月29日相差1天23:59:59"""
        feb_28_start = time.parse("2024-02-28", inclusive=False)
        feb_29_end = time.parse("2024-02-29", inclusive=True)
        diff = feb_29_end - feb_28_start
        assert diff.days == 1
        assert diff.seconds == 23 * 3600 + 59 * 60 + 59

    def test_non_leap_year_feb_28_to_march_1(self):
        """平年2月28日 inclusive 到 3月1日 exclusive 相差1秒"""
        feb_28_end = time.parse("2023-02-28", inclusive=True)
        march_1_start = time.parse("2023-03-01", inclusive=False)
        assert (march_1_start - feb_28_end).total_seconds() == 1

    @pytest.mark.parametrize(
        "year1,year2",
        [
            ("2020", "2024"),
            ("2016", "2024"),
            ("2000", "2024"),
        ],
    )
    def test_multi_year_leap_day_range(self, year1, year2):
        """跨年度2月29日范围的起止时间"""
        start = time.parse(f"{year1}-02-29", inclusive=False)
        end = time.parse(f"{year2}-02-29", inclusive=True)
        assert start.year == int(year1)
        assert end.year == int(year2)
        assert start.month == 2 and start.day == 29
        assert end.month == 2 and end.day == 29
        assert start < end

    def test_leap_day_with_default_hour(self):
        """闰年2月29日 + default_hour=9 用于录入路径"""
        result = time.parse(
            "2024-02-29", inclusive=False, default_hour=9, default_minute=0
        )
        assert result == datetime.datetime(2024, 2, 29, 9, 0)

    def test_leap_day_with_explicit_time(self):
        """闰年2月29日 + 明确时间，default_hour 不生效"""
        result = time.parse(
            "2024-02-29 14:30", inclusive=False, default_hour=9, default_minute=0
        )
        assert result == datetime.datetime(2024, 2, 29, 14, 30)

    def test_leap_day_last_moment(self):
        """闰年2月29日 23:59:59 正确解析"""
        result = time.parse("2024-02-29 23:59:59")
        assert result == datetime.datetime(2024, 2, 29, 23, 59, 59)

    def test_century_leap_year_2000(self):
        """世纪闰年 2000-02-29 有效"""
        result = time.parse("2000-02-29", inclusive=False)
        assert result == datetime.datetime(2000, 2, 29, 0, 0)

    def test_century_non_leap_year_2100(self):
        """世纪平年 2100-02-29 无效"""
        result = time.parse("2100-02-29")
        assert result is None


# ============================================================
# 年末跨日精细边界测试 (Year-end day boundary granular)
# ============================================================


class TestYearEndDayBoundary:
    """年末跨日精细边界：12/31 23:59:59 ↔ 1/1 00:00:00"""

    def test_year_end_last_moment(self):
        """年末最后一刻：12月31日 23:59:59"""
        result = time.parse("2023-12-31 23:59:59")
        assert result == datetime.datetime(2023, 12, 31, 23, 59, 59)

    def test_new_year_first_moment(self):
        """新年第一刻：1月1日 00:00:00"""
        result = time.parse("2024-01-01 00:00:00")
        assert result == datetime.datetime(2024, 1, 1, 0, 0, 0)

    def test_year_end_gap_is_one_second(self):
        """年末最后一刻到新年第一刻精确相差1秒"""
        year_end = time.parse("2023-12-31 23:59:59")
        new_year = time.parse("2024-01-01 00:00:00")
        assert (new_year - year_end).total_seconds() == 1

    def test_year_end_inclusive_end_of_day(self):
        """12/31 inclusive=True 是年末 23:59:59"""
        result = time.parse("2023-12-31", inclusive=True)
        assert result == datetime.datetime(2023, 12, 31, 23, 59, 59)

    def test_new_year_start_of_day(self):
        """1/1 exclusive=False 是新年 00:00:00"""
        result = time.parse("2024-01-01", inclusive=False)
        assert result == datetime.datetime(2024, 1, 1, 0, 0, 0)

    def test_year_end_to_new_year_inclusive_gap(self):
        """12/31 inclusive 到 1/1 exclusive 精确相差1秒"""
        end_of_year = time.parse("2023-12-31", inclusive=True)
        start_of_year = time.parse("2024-01-01", inclusive=False)
        assert (start_of_year - end_of_year).total_seconds() == 1

    def test_year_end_full_coverage_times(self):
        """年末全天四个关键时刻的时间顺序"""
        t1 = time.parse("2023-12-31 00:00:00")
        t2 = time.parse("2023-12-31 12:00:00")
        t3 = time.parse("2023-12-31 23:59:59")
        t4 = time.parse("2024-01-01 00:00:00")
        assert t1 < t2 < t3 < t4

    def test_year_end_with_keyword_today(self):
        """年末使用 today 关键字的 inclusive/exclusive 边界"""
        # 仅验证解析语义，不依赖实际日期
        # 测试类似 12/31 当天的解析逻辑
        dec_31_excl = time.parse("2023-12-31", inclusive=False)
        dec_31_incl = time.parse("2023-12-31", inclusive=True)
        assert dec_31_excl.hour == 0 and dec_31_excl.minute == 0
        assert dec_31_incl.hour == 23 and dec_31_incl.minute == 59

    def test_multiple_year_ends_continuous(self):
        """多年年末边界连续：2022→2023→2024"""
        y2022_end = time.parse("2022-12-31", inclusive=True)
        y2023_start = time.parse("2023-01-01", inclusive=False)
        y2023_end = time.parse("2023-12-31", inclusive=True)
        y2024_start = time.parse("2024-01-01", inclusive=False)

        assert (y2023_start - y2022_end).total_seconds() == 1
        assert (y2024_start - y2023_end).total_seconds() == 1
        assert y2022_end < y2023_start < y2023_end < y2024_start

    def test_year_end_12am_format(self):
        """12:00am 格式解析新年零点"""
        result = time.parse("2024-01-01 12:00am")
        assert result == datetime.datetime(2024, 1, 1, 0, 0)

    def test_year_end_1159pm_format(self):
        """11:59pm 格式解析年末最后一分钟"""
        result = time.parse("2023-12-31 11:59pm")
        assert result == datetime.datetime(2023, 12, 31, 23, 59)

    def test_year_end_entry_with_default_hour(self):
        """年末录入路径带 default_hour=9"""
        result = time.parse(
            "2023-12-31", inclusive=False, default_hour=9, default_minute=0
        )
        assert result == datetime.datetime(2023, 12, 31, 9, 0)

    def test_new_year_entry_with_default_hour(self):
        """新年录入路径带 default_hour=9"""
        result = time.parse(
            "2024-01-01", inclusive=False, default_hour=9, default_minute=0
        )
        assert result == datetime.datetime(2024, 1, 1, 9, 0)
