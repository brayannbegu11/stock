"""Plan semanal derivado del protocolo y del calendario oficial.

PROTOCOLO.yaml ``weekly_experiment``: corte **domingo 18:00 Asia/Taipei**;
plazo de emisión 08:30 de la primera sesión real de la semana natural
siguiente; entrada en la primera apertura válida **posterior al plazo**;
salida en el último cierre real de esa misma semana natural.

Reglas (rondas 3 y 4 de Astra):
- El experimento semanal sólo acepta cortes de domingo 18:00 Taipei; cualquier
  otro corte es una violación del protocolo, no una variante silenciosa
  (R04-05). El comparador diario (``daily_challenger``) está desactivado en el
  protocolo y tendrá su propio plan cuando se registre.
- Una semana sin sesiones produce ``invalid:no_sessions`` sin plazo, entrada
  ni salida; el plazo nunca salta a la semana siguiente (R03-03).
- La entrada es la primera apertura estrictamente posterior al plazo; si la
  primera sesión abre antes del plazo (horario especial), se usa la siguiente
  (R04-06).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from .calendar import TradingCalendar
from .timeutil import TAIPEI, taipei, to_utc

WEEKLY_CUTOFF_TIME = time(18, 0)      # domingo
WEEKLY_DEADLINE_TIME = time(8, 30)
STATUS_VALID = "valid"
STATUS_NO_SESSIONS = "invalid:no_sessions"


class NoSessionsInWeek(ValueError):
    pass


class ProtocolViolation(ValueError):
    pass


@dataclass(frozen=True)
class WeekPlan:
    week_id: str                   # semana ISO objetivo, p. ej. 2026-W37
    target_monday: date
    cutoff_at: datetime
    status: str                    # valid | invalid:no_sessions
    sessions: tuple[date, ...]
    deadline_at: Optional[datetime]
    entry_at: Optional[datetime]   # apertura de la primera sesión posterior al plazo
    exit_at: Optional[datetime]    # cierre de la última sesión de la semana

    @property
    def is_valid(self) -> bool:
        return self.status == STATUS_VALID

    @property
    def registration_deadline_at(self) -> datetime:
        """Último instante para archivar y acreditar el registro de la corrida.

        Semana válida: el plazo de emisión. Semana sin sesiones: el final de la
        semana natural objetivo (domingo 24:00 Taipei), porque la corrida
        ``invalid:no_sessions`` se registra sin predicción y no hay plazo de
        emisión que la acote (R05-09).
        """
        if self.deadline_at is not None and self.is_valid:
            return self.deadline_at
        return taipei(self.target_monday + timedelta(days=7), time(0, 0))


def is_weekly_cutoff(cutoff_at: datetime) -> bool:
    local = to_utc(cutoff_at).astimezone(TAIPEI)
    return local.weekday() == 6 and local.time() == WEEKLY_CUTOFF_TIME


def target_monday_for(cutoff_at: datetime) -> date:
    """Lunes de la semana natural que empieza después del corte (en hora de Taipei)."""
    local = to_utc(cutoff_at).astimezone(TAIPEI)
    d = local.date() + timedelta(days=1)
    return d - timedelta(days=d.weekday())


def plan_week(cutoff_at: datetime, calendar: TradingCalendar) -> WeekPlan:
    if not is_weekly_cutoff(cutoff_at):
        raise ProtocolViolation(
            f"weekly experiment requires a Sunday {WEEKLY_CUTOFF_TIME.strftime('%H:%M')} Asia/Taipei cutoff; "
            f"got {to_utc(cutoff_at).astimezone(TAIPEI).isoformat()} (R04-05)"
        )
    monday = target_monday_for(cutoff_at)
    iso = monday.isocalendar()
    week_id = f"{iso[0]}-W{iso[1]:02d}"
    sessions = tuple(calendar.week_sessions(monday))
    if not sessions:
        return WeekPlan(week_id, monday, cutoff_at, STATUS_NO_SESSIONS, (), None, None, None)
    deadline = taipei(sessions[0], WEEKLY_DEADLINE_TIME)
    entry_sessions = [s for s in sessions if to_utc(calendar.session_open(s)) > to_utc(deadline)]
    if not entry_sessions:
        return WeekPlan(week_id, monday, cutoff_at, STATUS_NO_SESSIONS, sessions, deadline, None, None)
    return WeekPlan(
        week_id, monday, cutoff_at, STATUS_VALID, sessions,
        deadline_at=deadline,
        entry_at=calendar.session_open(entry_sessions[0]),
        exit_at=calendar.session_close(sessions[-1]),
    )


def weekly_deadline(cutoff_at: datetime, calendar: TradingCalendar) -> datetime:
    """Plazo del protocolo para el corte dado; falla si la semana objetivo no tiene sesiones."""
    plan = plan_week(cutoff_at, calendar)
    if plan.deadline_at is None or not plan.is_valid:
        raise NoSessionsInWeek(f"week {plan.week_id} starting {plan.target_monday} has no usable sessions; run must be {STATUS_NO_SESSIONS}")
    return plan.deadline_at
