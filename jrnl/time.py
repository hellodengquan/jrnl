# Copyright © 2012-2023 jrnl contributors
# License: https://www.gnu.org/licenses/gpl-3.0.html

import datetime
from dataclasses import dataclass
from typing import Optional

FAKE_YEAR = 9999
DEFAULT_FUTURE = datetime.datetime(FAKE_YEAR, 12, 31, 23, 59, 59)
DEFAULT_PAST = datetime.datetime(FAKE_YEAR, 1, 1, 0, 0)


@dataclass
class DateRange:
    """统一的日期范围数据类，用于表示搜索的开始和结束日期。

    Attributes:
        start: 范围开始日期（包含）。None 表示无下限。
        end: 范围结束日期（包含）。None 表示无上限。
        month: 仅匹配特定月份（1-12）。None 表示不限制。
        day: 仅匹配特定日期（1-31）。None 表示不限制。
        year: 仅匹配特定年份。None 表示不限制。
    """

    start: Optional[datetime.datetime] = None
    end: Optional[datetime.datetime] = None
    month: Optional[int] = None
    day: Optional[int] = None
    year: Optional[int] = None

    def __post_init__(self):
        if self.start and self.end and self.start > self.end:
            self.start, self.end = self.end, self.start

    def matches(self, date: datetime.datetime) -> bool:
        """检查给定日期是否在此范围内。"""
        if self.start and date < self.start:
            return False
        if self.end and date > self.end:
            return False
        if self.month and date.month != self.month:
            return False
        if self.day and date.day != self.day:
            return False
        if self.year and date.year != self.year:
            return False
        return True

    @property
    def is_empty(self) -> bool:
        """判断是否没有任何日期约束。"""
        return all(
            x is None for x in (self.start, self.end, self.month, self.day, self.year)
        )


def __get_pdt_calendar():
    import parsedatetime as pdt

    consts = pdt.Constants(usePyICU=False)
    consts.DOWParseStyle = -1  # "Monday" will be either today or the last Monday
    calendar = pdt.Calendar(consts, version=pdt.VERSION_CONTEXT_STYLE)

    return calendar


def parse(
    date_str: str | datetime.datetime,
    inclusive: bool = False,
    default_hour: int | None = None,
    default_minute: int | None = None,
    bracketed: bool = False,
) -> datetime.datetime | None:
    """Parses a string containing a fuzzy date and returns a datetime.datetime object"""
    if not date_str:
        return None
    elif isinstance(date_str, datetime.datetime):
        return date_str

    # Don't try to parse anything with 6 or fewer characters and was parsed from the
    # existing journal. It's probably a markdown footnote
    if len(date_str) <= 6 and bracketed:
        return None

    default_date = DEFAULT_FUTURE if inclusive else DEFAULT_PAST
    date = None
    year_present = False

    hasTime = False
    hasDate = False

    while not date:
        try:
            from dateutil.parser import parse as dateparse

            date = dateparse(date_str, default=default_date)
            if date.year == FAKE_YEAR:
                date = datetime.datetime(
                    datetime.datetime.now().year, date.timetuple()[1:6]
                )
            else:
                year_present = True
            hasTime = not (date.hour == date.minute == 0)
            hasDate = True
            date = date.timetuple()
        except Exception as e:
            if e.args[0] == "day is out of range for month":
                y, m, d, H, M, S = default_date.timetuple()[:6]
                default_date = datetime.datetime(y, m, d - 1, H, M, S)
            else:
                calendar = __get_pdt_calendar()
                date, parse_context = calendar.parse(date_str)
                hasTime = parse_context.hasTime
                hasDate = parse_context.hasDate

    if not hasDate and not hasTime:
        try:  # Try and parse this as a single year
            year = int(date_str)
            return datetime.datetime(year, 1, 1)
        except ValueError:
            return None
        except TypeError:
            return None

    if hasDate and not hasTime:
        date = datetime.datetime(  # Use the default time
            *date[:3],
            hour=23 if inclusive else default_hour or 0,
            minute=59 if inclusive else default_minute or 0,
            second=59 if inclusive else 0,
        )
    else:
        date = datetime.datetime(*date[:6])

    # Ugly heuristic: if the date is more than 4 weeks in the future, we got the year
    # wrong. Rather than this, we would like to see parsedatetime patched so we can
    # tell it to prefer past dates
    dt = datetime.datetime.now() - date
    if dt.days < -28 and not year_present:
        date = date.replace(date.year - 1)
    return date


def _parse_month_day_year(
    month_str: Optional[str], day_str: Optional[str], year_str: Optional[str]
) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """统一解析 month/day/year 参数为整数元组。

    对于纯数字字符串，优先直接转换为整数，避免被 parse() 误解析为年份。
    """
    month = day = year = None

    if month_str:
        if month_str.isdigit():
            try:
                month = int(month_str)
                if not 1 <= month <= 12:
                    msg = f"Month out of range: {month}"
                    raise ValueError(msg)
            except (ValueError, TypeError):
                msg = f"Invalid month value: {month_str}"
                raise ValueError(msg)
        else:
            parsed = parse(month_str)
            if parsed:
                month = parsed.month
            else:
                msg = f"Invalid month value: {month_str}"
                raise ValueError(msg)

    if day_str:
        if day_str.isdigit():
            try:
                day = int(day_str)
                if not 1 <= day <= 31:
                    msg = f"Day out of range: {day}"
                    raise ValueError(msg)
            except (ValueError, TypeError):
                msg = f"Invalid day value: {day_str}"
                raise ValueError(msg)
        else:
            parsed = parse(day_str)
            if parsed:
                day = parsed.day
            else:
                msg = f"Invalid day value: {day_str}"
                raise ValueError(msg)

    if year_str:
        if year_str.isdigit():
            try:
                year = int(year_str)
                if year < 1:
                    msg = f"Year out of range: {year}"
                    raise ValueError(msg)
            except (ValueError, TypeError):
                msg = f"Invalid year value: {year_str}"
                raise ValueError(msg)
        else:
            parsed = parse(year_str)
            if parsed:
                year = parsed.year
            else:
                msg = f"Invalid year value: {year_str}"
                raise ValueError(msg)

    return month, day, year


def parse_date_range(
    on_date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    month: Optional[str] = None,
    day: Optional[str] = None,
    year: Optional[str] = None,
    today_in_history: bool = False,
    default_hour: Optional[int] = None,
    default_minute: Optional[int] = None,
) -> DateRange:
    """统一的日期范围解析入口。

    处理所有日期相关的搜索参数，返回一个规范化的 DateRange 对象。

    Args:
        on_date: 精确匹配某一天（会同时设置 start 和 end）
        start_date: 范围起始日期（包含）
        end_date: 范围结束日期（包含）
        month: 仅匹配特定月份（可以是 "january", "1", "jan" 等格式）
        day: 仅匹配特定日期（1-31）
        year: 仅匹配特定年份
        today_in_history: 匹配历史上的今天（设置 month 和 day 为今天）
        default_hour: 开始日期的默认小时
        default_minute: 开始日期的默认分钟

    Returns:
        DateRange: 规范化后的日期范围对象

    Raises:
        ValueError: 当参数非法或无法解析时抛出
    """
    result_start = None
    result_end = None

    if today_in_history:
        now = parse("now")
        if now:
            month = str(now.month) if not month else month
            day = str(now.day) if not day else day

    if on_date:
        result_start = parse(
            on_date,
            inclusive=False,
            default_hour=default_hour,
            default_minute=default_minute,
        )
        result_end = parse(on_date, inclusive=True)
        if not result_start or not result_end:
            msg = f"Invalid date for -on: {on_date}"
            raise ValueError(msg)

    else:
        if start_date:
            result_start = parse(
                start_date,
                inclusive=False,
                default_hour=default_hour,
                default_minute=default_minute,
            )
            if not result_start:
                msg = f"Invalid start date for -from: {start_date}"
                raise ValueError(msg)

        if end_date:
            result_end = parse(end_date, inclusive=True)
            if not result_end:
                msg = f"Invalid end date for -to: {end_date}"
                raise ValueError(msg)

    result_month, result_day, result_year = _parse_month_day_year(month, day, year)

    if (
        result_start is None
        and result_end is None
        and result_month is None
        and result_day is None
        and result_year is None
    ):
        return DateRange()

    return DateRange(
        start=result_start,
        end=result_end,
        month=result_month,
        day=result_day,
        year=result_year,
    )


def is_valid_date(year: int, month: int, day: int) -> bool:
    try:
        datetime.datetime(year, month, day)
        return True
    except ValueError:
        return False
