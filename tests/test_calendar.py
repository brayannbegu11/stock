from datetime import date, datetime, time

import pytest

from twlab.calendar import (
    ROW_CLOSURE, ROW_SESSION_MARKER, ROW_UNKNOWN, CalendarRangeError, CalendarStore, TradingCalendar,
    UnclassifiedCalendarRow, classify_holiday_row,
)
from twlab.timeutil import TAIPEI

# Cierres oficiales 2026 en día laborable según la captura del 9-09-2026, una vez
# excluidas las filas informativas de negociación (R01-01).
OFFICIAL_2026_WEEKDAY_CLOSURES = {
    date(2026, 1, 1), date(2026, 2, 12), date(2026, 2, 13),
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19), date(2026, 2, 20),
    date(2026, 2, 27), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 1),
    date(2026, 6, 19), date(2026, 9, 25), date(2026, 9, 28), date(2026, 10, 9), date(2026, 10, 26),
    date(2026, 12, 25),
}
TRADING_MARKER_DAYS = (date(2026, 1, 2), date(2026, 2, 11), date(2026, 2, 23))
R = datetime(2026, 9, 9, tzinfo=TAIPEI)


def synthetic(closures, **kw):
    return TradingCalendar(start=date(2026, 1, 1), end=date(2026, 12, 31), closures=closures, source_id="synthetic",
                           recorded_at=R, **kw)


def test_official_2026_closures_match_capture(cal):
    for d in OFFICIAL_2026_WEEKDAY_CLOSURES:
        assert not cal.is_session(d), d
    assert len(cal.sessions) == 261 - len(OFFICIAL_2026_WEEKDAY_CLOSURES) == 243


def test_r01_01_trading_day_markers_are_sessions(cal):
    """Astra R01-01: 開始交易日 / 最後交易日 son sesiones, no cierres."""
    assert [cal.is_session(d) for d in TRADING_MARKER_DAYS] == [True, True, True]


@pytest.mark.parametrize("row,expected", [
    ({"Name": "國曆新年開始交易日", "Description": "國曆新年開始交易。"}, ROW_SESSION_MARKER),
    ({"Name": "農曆春節前最後交易日", "Description": "農曆春節前最後交易。<br>"}, ROW_SESSION_MARKER),
    ({"Name": "市場無交易，僅辦理結算交割作業", "Description": ""}, ROW_CLOSURE),
    ({"Name": "和平紀念日", "Description": "和平紀念日為2月28日適逢星期六，於2月27日（星期五）補假。"}, ROW_CLOSURE),
    ({"Name": "勞動節", "Description": "依規定放假1日。"}, ROW_CLOSURE),
    ({"Name": "颱風", "Description": "尚未公告"}, ROW_UNKNOWN),
    # R02-19: contradicciones y negaciones nunca se clasifican
    ({"Name": "國曆新年開始交易日", "Description": "颱風休市"}, ROW_UNKNOWN),
    ({"Name": "公告", "Description": "不休市，正常交易"}, ROW_UNKNOWN),
    ({"Name": "颱風", "Description": "取消休市"}, ROW_UNKNOWN),
    # R03-12: cancelación de festivo y otras negaciones
    ({"Name": "公告", "Description": "取消放假"}, ROW_UNKNOWN),
    ({"Name": "公告", "Description": "未放假，照常交易"}, ROW_UNKNOWN),
    ({"Name": "公告", "Description": "非交易日，市場無交易"}, ROW_CLOSURE),
])
def test_row_classification(row, expected):
    assert classify_holiday_row(row) == expected


def test_unclassified_or_contradictory_rows_refuse_to_guess():
    for row in ({"Date": "1150601", "Weekday": "一", "Name": "颱風", "Description": "尚未公告"},
                {"Date": "1150102", "Weekday": "五", "Name": "國曆新年開始交易日", "Description": "颱風休市"}):
        with pytest.raises(UnclassifiedCalendarRow):
            TradingCalendar.from_twse_holiday_rows([row], year=2026, source_id="t", recorded_at=R)


def test_sim10_lunar_new_year_weeks(cal):
    """SIM-10: una semana no tiene cinco sesiones por definición."""
    assert cal.week_sessions(date(2026, 2, 9)) == [date(2026, 2, 9), date(2026, 2, 10), date(2026, 2, 11)]
    assert cal.week_sessions(date(2026, 2, 16)) == []
    assert cal.first_session_of_week(date(2026, 2, 16)) is None
    assert cal.last_session_of_week(date(2026, 2, 9)) == date(2026, 2, 11)


def test_sim10_weeks_with_one_and_two_sessions_synthetic():
    """Regla T2: semanas de una y dos sesiones son válidas; la etiqueta va de la primera apertura al último cierre."""
    one = synthetic(OFFICIAL_2026_WEEKDAY_CLOSURES | {date(2026, 6, 16), date(2026, 6, 17), date(2026, 6, 18)})
    assert one.week_sessions(date(2026, 6, 15)) == [date(2026, 6, 15)]           # 19-jun es festivo oficial
    assert one.first_session_of_week(date(2026, 6, 15)) == one.last_session_of_week(date(2026, 6, 15)) == date(2026, 6, 15)
    two = synthetic(OFFICIAL_2026_WEEKDAY_CLOSURES | {date(2026, 6, 16), date(2026, 6, 17)})
    assert two.week_sessions(date(2026, 6, 15)) == [date(2026, 6, 15), date(2026, 6, 18)]
    assert two.session_open(date(2026, 6, 15)) < two.session_close(date(2026, 6, 18))


def test_next_session_after_new_year(cal):
    assert cal.next_session(after=date(2026, 1, 1)) == date(2026, 1, 2)
    assert cal.next_session(after=date(2026, 2, 11)) == date(2026, 2, 23)


def test_session_open_close_are_taipei_aware(cal):
    o = cal.session_open(date(2026, 9, 8))
    c = cal.session_close(date(2026, 9, 8))
    assert o == datetime(2026, 9, 8, 9, 0, tzinfo=TAIPEI)
    assert c == datetime(2026, 9, 8, 13, 30, tzinfo=TAIPEI)
    with pytest.raises(CalendarRangeError):
        cal.session_open(date(2026, 9, 6))  # domingo


def test_out_of_range_is_an_error_not_a_guess(cal):
    with pytest.raises(CalendarRangeError):
        cal.is_session(date(2027, 1, 4))
    with pytest.raises(CalendarRangeError):
        cal.next_session(after=date(2026, 12, 31))


def test_generic_calendar_agrees_with_official_2026(cal):
    """Contraste, no autoridad: tras R01-01, XTAI y la lista oficial coinciden en 2026."""
    xc = pytest.importorskip("exchange_calendars")
    xtai = xc.get_calendar("XTAI")
    xtai_sessions = {s.date() for s in xtai.sessions_in_range("2026-01-01", "2026-12-31")}
    assert xtai_sessions == set(cal.sessions)


def test_session_overrides_half_day():
    cal = synthetic(OFFICIAL_2026_WEEKDAY_CLOSURES, session_overrides={date(2026, 2, 11): (time(9, 0), time(12, 0))})
    assert cal.session_close(date(2026, 2, 11)) == datetime(2026, 2, 11, 12, 0, tzinfo=TAIPEI)
    assert cal.session_close(date(2026, 2, 10)) == datetime(2026, 2, 10, 13, 30, tzinfo=TAIPEI)
    with pytest.raises(CalendarRangeError):
        synthetic(OFFICIAL_2026_WEEKDAY_CLOSURES, session_overrides={date(2026, 2, 16): (time(9, 0), time(12, 0))})


def test_r03_11_session_hours_have_no_mutable_aliases():
    d = date(2026, 9, 7)
    c = synthetic(OFFICIAL_2026_WEEKDAY_CLOSURES, session_overrides={d: [time(9, 0), time(13, 30)]})   # lista de entrada
    store = CalendarStore()
    store.add(c)
    before = store.as_known_at(R).session_open(d)
    hours = c.session_hours(d)
    assert isinstance(hours, tuple)
    with pytest.raises(TypeError):
        hours[0] = time(12, 0)  # type: ignore[index]
    with pytest.raises(TypeError):
        c._overrides[d] = (time(12, 0), time(13, 0))  # type: ignore[index]
    assert store.as_known_at(R).session_open(d) == before
    with pytest.raises(CalendarRangeError):
        synthetic(OFFICIAL_2026_WEEKDAY_CLOSURES, session_overrides={d: (time(13, 30), time(9, 0))})
    with pytest.raises(CalendarRangeError):
        synthetic(OFFICIAL_2026_WEEKDAY_CLOSURES, session_overrides={d: ("09:00", "13:30")})  # type: ignore[dict-item]


def test_r02_18_calendar_is_immutable():
    c = synthetic(OFFICIAL_2026_WEEKDAY_CLOSURES)
    store = CalendarStore()
    store.add(c)
    before = store.as_known_at(R).session_open(date(2026, 9, 7))
    with pytest.raises(AttributeError):
        c.OPEN = time(12, 0)
    with pytest.raises(AttributeError):
        c._closures = frozenset()
    with pytest.raises(AttributeError):
        del c.start
    assert store.as_known_at(R).session_open(date(2026, 9, 7)) == before
    with pytest.raises(TypeError):
        store.add("not a calendar")  # type: ignore[arg-type]


def test_calendar_store_known_vs_effective():
    """Un cierre extraordinario anunciado el 15-06 no existe para quien consulta el 10-06."""
    base = TradingCalendar(start=date(2026, 1, 1), end=date(2026, 12, 31), closures=OFFICIAL_2026_WEEKDAY_CLOSURES,
                           source_id="t", recorded_at=datetime(2026, 1, 1, tzinfo=TAIPEI), version="v1")
    typhoon = TradingCalendar(start=date(2026, 1, 1), end=date(2026, 12, 31),
                              closures=OFFICIAL_2026_WEEKDAY_CLOSURES | {date(2026, 6, 16)},
                              source_id="t", recorded_at=datetime(2026, 6, 15, 20, 0, tzinfo=TAIPEI), version="v2")
    store = CalendarStore()
    store.add(base)
    store.add(typhoon)
    assert store.as_known_at(datetime(2026, 6, 10, tzinfo=TAIPEI)).is_session(date(2026, 6, 16))
    assert not store.as_known_at(datetime(2026, 6, 16, tzinfo=TAIPEI)).is_session(date(2026, 6, 16))
    with pytest.raises(CalendarRangeError):
        store.as_known_at(datetime(2025, 12, 31, tzinfo=TAIPEI))
