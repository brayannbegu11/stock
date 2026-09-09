from datetime import date, datetime, time

import pytest

from twlab.calendar import TradingCalendar
from twlab.timeutil import TAIPEI, taipei
from twlab.weekly import (
    STATUS_NO_SESSIONS, STATUS_VALID, NoSessionsInWeek, ProtocolViolation, is_weekly_cutoff, plan_week,
    target_monday_for, weekly_deadline,
)

R = datetime(2026, 1, 1, tzinfo=TAIPEI)


def test_sunday_cutoff_targets_following_week(cal):
    cutoff = taipei(date(2026, 9, 6), time(18, 0))
    assert is_weekly_cutoff(cutoff) and target_monday_for(cutoff) == date(2026, 9, 7)
    plan = plan_week(cutoff, cal)
    assert plan.week_id == "2026-W37" and plan.status == STATUS_VALID and plan.is_valid
    assert plan.sessions == tuple(date(2026, 9, d) for d in range(7, 12))
    assert plan.deadline_at == taipei(date(2026, 9, 7), time(8, 30))
    assert plan.entry_at == taipei(date(2026, 9, 7), time(9, 0)) and plan.entry_at > plan.deadline_at
    assert plan.exit_at == taipei(date(2026, 9, 11), time(13, 30))
    assert weekly_deadline(cutoff, cal) == plan.deadline_at
    assert plan.registration_deadline_at == plan.deadline_at


def test_r03_03_week_without_sessions_is_invalid_not_deferred(cal):
    cutoff = taipei(date(2026, 2, 15), time(18, 0))          # semana 16-20 feb: sin sesiones
    plan = plan_week(cutoff, cal)
    assert plan.status == STATUS_NO_SESSIONS and not plan.is_valid
    assert plan.deadline_at is None and plan.entry_at is None and plan.exit_at is None
    assert plan.week_id == "2026-W08"
    assert plan.registration_deadline_at == taipei(date(2026, 2, 23), time(0, 0))      # R05-09: fin de la semana objetivo
    with pytest.raises(NoSessionsInWeek):
        weekly_deadline(cutoff, cal)


def test_short_week_is_valid_with_real_extremes(cal):
    plan = plan_week(taipei(date(2026, 2, 8), time(18, 0)), cal)
    assert plan.is_valid and plan.sessions == (date(2026, 2, 9), date(2026, 2, 10), date(2026, 2, 11))
    assert plan.exit_at == taipei(date(2026, 2, 11), time(13, 30))


def test_r04_05_weekly_experiment_rejects_any_other_cutoff(cal):
    """Un corte a mitad de semana no es una variante: es otra pregunta científica (protocolo 2.0)."""
    for bad in (taipei(date(2026, 9, 10), time(2, 0)), taipei(date(2026, 9, 11), time(14, 0)),
                taipei(date(2026, 9, 6), time(17, 59)), taipei(date(2026, 9, 6), time(23, 30))):
        assert not is_weekly_cutoff(bad)
        with pytest.raises(ProtocolViolation):
            plan_week(bad, cal)
    # el mismo instante expresado en otra zona sigue siendo domingo 18:00 Taipei
    assert is_weekly_cutoff(taipei(date(2026, 9, 6), time(18, 0)).astimezone(datetime.now().astimezone().tzinfo))


def test_r04_06_entry_is_the_first_open_after_the_deadline():
    cutoff = taipei(date(2026, 9, 6), time(18, 0))
    early = TradingCalendar(start=date(2026, 1, 1), end=date(2026, 12, 31), closures=[], source_id="synthetic",
                            recorded_at=R, session_overrides={date(2026, 9, 7): (time(8, 0), time(13, 30))})
    plan = plan_week(cutoff, early)
    assert plan.deadline_at == taipei(date(2026, 9, 7), time(8, 30))
    assert plan.entry_at == taipei(date(2026, 9, 8), time(9, 0)) and plan.entry_at > plan.deadline_at
    lonely = TradingCalendar(start=date(2026, 1, 1), end=date(2026, 12, 31),
                             closures=[date(2026, 9, d) for d in range(8, 12)], source_id="synthetic",
                             recorded_at=R, session_overrides={date(2026, 9, 7): (time(8, 0), time(13, 30))})
    plan2 = plan_week(cutoff, lonely)
    assert plan2.status == STATUS_NO_SESSIONS and plan2.entry_at is None      # ninguna apertura posterior al plazo


def test_target_week_uses_taipei_calendar_day():
    assert target_monday_for(taipei(date(2026, 9, 6), time(23, 30))) == date(2026, 9, 7)
    assert target_monday_for(taipei(date(2026, 9, 7), time(0, 30))) == date(2026, 9, 7)
    assert target_monday_for(taipei(date(2026, 9, 13), time(18, 0))) == date(2026, 9, 14)
