from datetime import date, time

import pytest

from twlab.calendar import load_twse_reference_calendar_2026
from twlab.timeutil import taipei


@pytest.fixture(scope="session")
def cal():
    return load_twse_reference_calendar_2026()


@pytest.fixture
def sunday_cutoff():
    # Domingo 6-09-2026 18:00 Asia/Taipei (PROTOCOLO weekly_experiment.information_cutoff)
    return taipei(date(2026, 9, 6), time(18, 0))
