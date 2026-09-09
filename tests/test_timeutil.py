from datetime import date, time

import pytest

from twlab.timeutil import AvailabilityQuality, DateParseError, derive_available_at, parse_date, parse_hhmmss, taipei


@pytest.mark.parametrize("raw,expected", [
    ("1150908", date(2026, 9, 8)),        # ROC compacto (TWSE OpenAPI)
    ("990101", date(2010, 1, 1)),         # ROC de 6 dígitos
    ("115/09/01", date(2026, 9, 1)),      # ROC con barras (suspendListing)
    ("20260901", date(2026, 9, 1)),       # gregoriano compacto (tpex_index)
    ("2026-09-01", date(2026, 9, 1)),     # ISO (FinMind)
    ("民國115年06月11日", date(2026, 6, 11)),
    ("115年6月11日", date(2026, 6, 11)),
])
def test_parse_date_formats(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "abc", "1151332", "115-09-01", "2026/13/01"])
def test_parse_date_never_guesses(raw):
    with pytest.raises(DateParseError):
        parse_date(raw)


@pytest.mark.parametrize("raw,expected", [
    ("3220", time(0, 32, 20)),     # observado en t187ap04_L
    ("70004", time(7, 0, 4)),
    ("163004", time(16, 30, 4)),
    ("080000", time(8, 0, 0)),
])
def test_parse_hhmmss_unpadded(raw, expected):
    assert parse_hhmmss(raw) == expected


def test_parse_hhmmss_rejects_garbage():
    for bad in ["", "9999999", "25:00", "abc"]:
        with pytest.raises(DateParseError):
            parse_hhmmss(bad)


def test_pit05_date_only_is_not_midnight(cal):
    """PIT-05: fecha sin hora → apertura de la siguiente sesión, con marca de inferencia."""
    av = derive_available_at(date(2026, 9, 4), calendar=cal)          # viernes
    assert av.available_at == taipei(date(2026, 9, 7), time(9, 0))    # lunes 09:00
    assert av.quality == AvailabilityQuality.CONSERVATIVE_INFERENCE
    assert av.available_at != taipei(date(2026, 9, 4), time(0, 0))


def test_pit05_date_only_on_weekend(cal):
    av = derive_available_at(date(2026, 9, 6), calendar=cal)          # domingo
    assert av.available_at == taipei(date(2026, 9, 7), time(9, 0))


def test_verified_time_is_used_as_is(cal):
    av = derive_available_at(date(2026, 9, 4), time(15, 5), calendar=cal, time_is_verified=True)
    assert av.available_at == taipei(date(2026, 9, 4), time(15, 5))
    assert av.quality == AvailabilityQuality.VERIFIED_ORIGINAL


def test_unverified_time_falls_back_to_conservative(cal):
    av = derive_available_at(date(2026, 9, 4), time(15, 5), calendar=cal, time_is_verified=False)
    assert av.quality == AvailabilityQuality.CONSERVATIVE_INFERENCE
