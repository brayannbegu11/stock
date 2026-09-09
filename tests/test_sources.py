"""Pruebas de los adaptadores de lectura (TWSE OpenAPI, FinMind), del maestro sobre censos y del calendario multianual.

Todo con filas sintéticas explícitas o con las capturas versionadas en ``data/reference``; sin red.
Incluye los contraejemplos de la ronda 8 de Astra (R08-02, R08-03, R08-04, R08-05, R08-06, R08-07, R08-13).
"""
from datetime import date, datetime, time

import pytest

from twlab.calendar import CalendarRangeError, TradingCalendar, UnclassifiedCalendarRow, classify_holiday_row_en, load_twse_reference_calendar
from twlab.master import SecurityMaster, security_id_for
from twlab.sources import finmind
from twlab.sources.finmind import DuplicateSession, SourceIdentityMismatch
from twlab.sources.twse import (
    census_rows_tpex, census_rows_twse, delisting_rows_twse, resolve_delistings, security_versions_from_census,
)
from twlab.timeutil import TAIPEI, DateParseError, taipei
from decimal import Decimal as D

REC_AT = taipei(date(2026, 9, 9), time(18, 0))
TODAY = date(2026, 9, 9)


# ---- censos y retiradas (TWSE OpenAPI) --------------------------------------------------------------

def test_census_rows_twse_parse_roc_dates_and_tolerate_missing_listing_date():
    rows = [
        {"出表日期": "1150909", "公司代號": "2330", "公司簡稱": "台積電", "產業別": "24", "上市日期": "0830905",
         "外國企業註冊地國": "－", "已發行普通股數或TDR原股發行股數": "25,932,070,980"},
        {"出表日期": "1150909", "公司代號": "9999", "公司簡稱": "sin fecha", "產業別": "01", "上市日期": "",
         "外國企業註冊地國": "KY", "已發行普通股數或TDR原股發行股數": "n/a"},
    ]
    out = census_rows_twse(rows)
    assert out[0].symbol == "2330" and out[0].listing_date == date(1994, 9, 5) and out[0].report_date == date(2026, 9, 9)
    assert out[0].issued_shares == 25_932_070_980 and out[0].registration == "－"
    assert out[1].listing_date is None and out[1].issued_shares is None and out[1].registration == "KY"
    with pytest.raises((DateParseError, KeyError)):
        census_rows_twse([{"公司代號": "1", "出表日期": "no-es-fecha"}])


def test_census_rows_tpex_use_english_keys():
    rows = [{"Date": "1150909", "SecuritiesCompanyCode": "6488", "CompanyAbbreviation": "環球晶", "SecuritiesIndustryCode": "24",
             "DateOfListing": "1040928", "Registration": "－", "IssueShares": "435,000,000"}]
    r = census_rows_tpex(rows)[0]
    assert (r.symbol, r.listing_date, r.industry_code, r.issued_shares) == ("6488", date(2015, 9, 28), "24", 435_000_000)


def test_delisting_rows_twse_parse_roc_slash_dates():
    rows = [{"Code": "1701", "Company": "中化", "DelistingDate": "113/09/02"}]
    r = delisting_rows_twse(rows)[0]
    assert (r.symbol, r.name_zh, r.delisting_date) == ("1701", "中化", date(2024, 9, 2))
    with pytest.raises(DateParseError):
        delisting_rows_twse([{"Code": "1", "DelistingDate": "2024/13/40"}])


def _census(*rows):
    return census_rows_twse([{"出表日期": "1150909", "公司代號": s, "公司簡稱": n, "產業別": "24", "上市日期": d} for s, n, d in rows])


def test_r08_04_unknown_or_absent_category_is_unclassified_never_ordinary_equity():
    instrument, board, _ = finmind.classify_info([
        {"stock_id": "2330", "industry_category": "半導體業", "type": "twse"},
        {"stock_id": "0050", "industry_category": "ETF", "type": "twse"},
        {"stock_id": "6789", "industry_category": "創新板股票", "type": "twse"},
        {"stock_id": "9999", "industry_category": "", "type": "twse"},
        {"stock_id": "9998", "industry_category": "NEW_STRUCTURED_PRODUCT", "type": "twse"},
    ])
    assert instrument["2330"] == "ordinary_equity" and instrument["0050"] == "etf"
    assert instrument["9999"] == "unclassified" and instrument["9998"] == "unclassified"
    rows = _census(("2330", "台積電", "0830905"), ("0050", "元大台灣50", "0920630"), ("6789", "創新板", "1120801"),
                   ("7777", "ausente", "1100101"), ("9999", "vacía", "1100101"), ("9998", "rara", "1100101"), ("8888", "sin alta", ""))
    versions = security_versions_from_census(rows, market="TWSE", instrument_types=instrument, boards=board, recorded_at=REC_AT, source_id="cap-1")
    by = {v.symbol: v for v in versions}
    assert set(by) == {"2330", "0050", "6789", "7777", "9999", "9998"}          # 8888 sin fecha de alta: no entra
    assert by["2330"].instrument_type == "ordinary_equity" and by["2330"].board == "main"
    assert by["0050"].instrument_type == "etf"
    assert by["6789"].instrument_type == "ordinary_equity" and by["6789"].board == "innovation"
    assert {by[s].instrument_type for s in ("7777", "9999", "9998")} == {"unclassified"}


def test_r08_13_default_universe_is_main_board_only_and_innovation_needs_explicit_enablement():
    instrument, board, _ = finmind.classify_info([
        {"stock_id": "2330", "industry_category": "半導體業", "type": "twse"},
        {"stock_id": "6789", "industry_category": "創新板股票", "type": "twse"},
    ])
    versions = security_versions_from_census(_census(("2330", "台積電", "0830905"), ("6789", "創新板", "1120801")), market="TWSE",
                                             instrument_types=instrument, boards=board, recorded_at=REC_AT, source_id="cap-1")
    master = SecurityMaster()
    master.extend(versions)
    assert {v.symbol for v in master.universe(as_of=TODAY)} == {"2330"}
    assert {v.symbol for v in master.universe(as_of=TODAY, boards=("main", "innovation"))} == {"2330", "6789"}
    assert {v.symbol for v in master.universe(as_of=TODAY, boards=("innovation",))} == {"6789"}


def test_r08_05_reused_symbol_gets_distinct_identities_and_delistings_resolve_against_them():
    assert security_id_for("TWSE", "2432", date(2023, 5, 31)) == "TWSE:2432@2023-05-31"
    instrument = {"2432": "ordinary_equity", "1701": "ordinary_equity"}
    master = SecurityMaster()
    master.extend(security_versions_from_census(_census(("2432", "emisor nuevo", "1120531"), ("1701", "中化", "0790101")),
                                                market="TWSE", instrument_types=instrument, boards={}, recorded_at=REC_AT, source_id="cap-1"))
    # el emisor anterior del símbolo 2432 (alta 2000, retirada 2008) recibe otra identidad y no choca con el vigente
    master.add(security_versions_from_census(_census(("2432", "emisor antiguo", "0890101")), market="TWSE", instrument_types=instrument,
                                             boards={}, recorded_at=REC_AT, source_id="cap-0")[0].__class__(
        **{**vars(master.segments_of_symbol("2432")[0]), "security_id": "TWSE:2432@2000-01-01", "issuer_id": "TWSE:2432@2000-01-01",
           "valid_from": date(2000, 1, 1), "valid_to": date(2008, 9, 1)}))
    segs = master.segments_of_symbol("2432")
    assert [s.security_id for s in segs] == ["TWSE:2432@2000-01-01", "TWSE:2432@2023-05-31"]
    rows = delisting_rows_twse([{"Code": "2432", "Company": "antiguo", "DelistingDate": "97/09/01"},
                                {"Code": "1701", "Company": "中化", "DelistingDate": "113/09/02"},
                                {"Code": "5555", "Company": "huérfana", "DelistingDate": "100/01/01"}])
    res = resolve_delistings(rows, master, market="TWSE", recorded_at=REC_AT, source_id="cap-d")
    # 2432: la retirada de 2008 cae dentro del segmento antiguo cerrado → evento sobre el emisor antiguo, no sobre el vigente
    assert [(e.security_id, e.effective) for e in res.events] == [("TWSE:2432@2000-01-01", date(2008, 9, 1)), ("TWSE:1701@1990-01-01", date(2024, 9, 2))]
    assert res.orphan == ("5555",) and res.ambiguous == ()
    # sin el segmento antiguo, la misma retirada es «de un emisor anterior» y no cierra el vigente
    master2 = SecurityMaster()
    master2.extend(security_versions_from_census(_census(("2432", "emisor nuevo", "1120531")), market="TWSE", instrument_types=instrument,
                                                 boards={}, recorded_at=REC_AT, source_id="cap-1"))
    res2 = resolve_delistings(rows[:1], master2, market="TWSE", recorded_at=REC_AT, source_id="cap-d")
    assert res2.events == () and len(res2.prior_issuer) == 1 and res2.prior_issuer[0].startswith("2432 (retirada 2008-09-01")


def test_r09_05_delisting_without_covering_segment_is_unresolved_unless_an_earlier_issuer_is_implied():
    from dataclasses import replace
    instrument = {"A": "ordinary_equity"}
    master = SecurityMaster()
    v = security_versions_from_census(_census(("A", "alta y baja el mismo día", "1130108")), market="TWSE", instrument_types=instrument,
                                      boards={}, recorded_at=REC_AT, source_id="cap-1")[0]
    master.add(v)
    same_day = delisting_rows_twse([{"Code": "A", "Company": "A", "DelistingDate": "113/01/08"}])
    res = resolve_delistings(same_day, master, market="TWSE", recorded_at=REC_AT, source_id="cap-d")
    assert res.events == () and res.prior_issuer == () and len(res.unresolved) == 1 and "2024-01-08" in res.unresolved[0]
    # segmento ya cerrado [2024-01-08, 2024-01-12) y retirada posterior: no hay evidencia de otro emisor
    master2 = SecurityMaster()
    master2.add(replace(v, valid_to=date(2024, 1, 12)))
    later = delisting_rows_twse([{"Code": "A", "Company": "A", "DelistingDate": "113/01/17"}])
    res2 = resolve_delistings(later, master2, market="TWSE", recorded_at=REC_AT, source_id="cap-d")
    assert res2.events == () and res2.prior_issuer == () and len(res2.unresolved) == 1
    # retirada exactamente en valid_to: cubre el segmento cerrado
    at_end = delisting_rows_twse([{"Code": "A", "Company": "A", "DelistingDate": "113/01/12"}])
    res3 = resolve_delistings(at_end, master2, market="TWSE", recorded_at=REC_AT, source_id="cap-d")
    assert [e.effective for e in res3.events] == [date(2024, 1, 12)]


# ---- FinMind ----------------------------------------------------------------------------------------

def test_finmind_classify_info_is_order_independent_and_separates_instruments_boards_and_markets():
    rows = [
        {"stock_id": "2330", "industry_category": "半導體業", "type": "twse"},
        {"stock_id": "2330", "industry_category": "所有證券", "type": "twse"},          # fila agregada: no degrada la anterior
        {"stock_id": "00878", "industry_category": "ETF", "type": "twse"},
        {"stock_id": "020000", "industry_category": "指數投資證券(ETN)", "type": "twse"},
        {"stock_id": "910322", "industry_category": "存託憑證", "type": "twse"},
        {"stock_id": "910322", "industry_category": "所有證券", "type": "twse"},
        {"stock_id": "6488", "industry_category": "半導體業", "type": "tpex"},
        {"stock_id": "6789", "industry_category": "創新板股票", "type": "twse"},
        {"stock_id": "TAIEX", "industry_category": "Index", "type": "twse"},
    ]
    for order in (rows, rows[::-1]):
        instrument, board, market = finmind.classify_info(order)
        assert instrument["2330"] == "ordinary_equity" and instrument["00878"] == "etf"
        assert instrument["020000"] == "etn" and instrument["910322"] == "dr" and instrument["TAIEX"] == "index"
        assert board == {"6789": "innovation"} and market["6488"] == "tpex"


def test_r08_06_r08_07_bars_require_the_expected_stock_id_and_reject_repeated_sessions():
    rows = [
        {"stock_id": "A", "date": "2025-03-04", "open": 100.5, "max": 101, "min": 99, "close": 100, "Trading_Volume": 1000, "Trading_money": 100000, "Trading_turnover": 12},
        {"stock_id": "A", "date": "2025-03-03", "open": 98, "max": 99, "min": 97, "close": 98.5, "Trading_Volume": 2000, "Trading_money": 197000, "Trading_turnover": 20},
        {"stock_id": "A", "date": "2025-03-05", "open": 0, "max": 0, "min": 0, "close": 0, "Trading_Volume": 48, "Trading_money": 1606, "Trading_turnover": 18},
    ]
    bars = finmind.bars_from_rows(rows, stock_id="A")
    assert [b.session for b in bars] == [date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5)]
    assert bars[1].open == D("100.5") and bars[1].value_twd == D("100000") and bars[1].volume_shares == 1000
    assert bars[0].available_at == taipei(date(2025, 3, 3), time(13, 30)) + finmind.PRICE_AVAILABILITY_LAG
    assert bars[0].available_at > taipei(date(2025, 3, 3), time(18, 0))       # política de 24 h: no disponible en el corte del mismo día
    assert bars[2].has_regular_price is False and bars[2].volume_shares == 48   # R08-12: sin precio regular, pero con negociación
    with pytest.raises(SourceIdentityMismatch):
        finmind.bars_from_rows(rows, stock_id="B")
    with pytest.raises(DuplicateSession):
        finmind.bars_from_rows(rows + [dict(rows[0])], stock_id="A")


def test_r08_03_dividend_announcement_without_time_is_a_date_not_an_instant():
    rows = [{
        "stock_id": "2330", "year": "2024", "AnnouncementDate": "2025-02-13", "AnnouncementTime": "8:5:3",
        "CashEarningsDistribution": 4.5, "CashStatutorySurplus": 0.5, "StockEarningsDistribution": 0, "StockStatutorySurplus": 0,
        "CashExDividendTradingDate": "2025-06-12", "CashDividendPaymentDate": "2025-07-10", "StockExDividendTradingDate": "",
    }, {
        "stock_id": "2330", "year": "2023", "AnnouncementDate": "2024-01-05", "AnnouncementTime": "",
        "CashEarningsDistribution": 0, "CashStatutorySurplus": None, "StockEarningsDistribution": 0.9377522407, "StockStatutorySurplus": 0,
        "CashExDividendTradingDate": "", "CashDividendPaymentDate": "", "StockExDividendTradingDate": "2024-07-26",
    }]
    a, b = finmind.dividends_from_rows(rows, stock_id="2330")
    assert a.cash_per_share == D("5.0") and a.cash_ex_date == date(2025, 6, 12) and a.cash_pay_date == date(2025, 7, 10)
    assert a.announced_at == datetime(2025, 2, 13, 8, 5, 3, tzinfo=TAIPEI) and a.announced_date == date(2025, 2, 13)
    assert b.announced_date == date(2024, 1, 5) and b.announced_at is None     # sin hora no hay instante (R08-03)
    assert b.cash_per_share == 0 and b.stock_per_share == D("0.9377522407") and b.stock_ex_date == date(2024, 7, 26)
    with pytest.raises(SourceIdentityMismatch):
        finmind.dividends_from_rows(rows, stock_id="1436")


# ---- calendario multianual (endpoint heredado en inglés) -----------------------------------------------

@pytest.mark.parametrize("desc,kind", [
    ("New Year", "closure"),
    ("New Year (2022)", "closure"),
    ("Adjusted Holiday (2021)", "closure"),
    ("No Trading. Market opens only for Clearing & Settlement", "closure"),
    ("No Trading. Market opens only for Clearing & Settlement.", "closure"),
    ("no trading market opens only for clearing & settlement", "closure"),
    ("Chinese New Year’s Eve", "closure"),
    ("Adjusted Holiday/ Chinese New Year’s Eve", "closure"),
    ("Adjusted Holiday/Children’s Day", "closure"),
    ("Children’s Day & Tomb-sweeping Day", "closure"),
    ("Mid-autumn / Moon Festival", "closure"),
    ("Tomb-sweeping Day", "closure"),
    ("Market Open", "session_marker"),
    ("market open", "session_marker"),
    ("Last Trading Day", "session_marker"),
    ("First Trading Day of the Year", "session_marker"),
    # R08-02 / R09-04: negaciones, contradicciones, anuncios pendientes y cualquier redacción no catalogada
    ("Typhoon Day Off", "unknown"),
    ("Typhoon closure cancelled; normal trading", "unknown"),
    ("Typhoon warning: trading continues", "unknown"),
    ("Market Open: No trading due to typhoon", "unknown"),
    ("Market Open is not confirmed", "unknown"),
    ("Holiday schedule; Market Open", "unknown"),
    ("Holiday schedule to be confirmed", "unknown"),
    ("Not a Holiday", "unknown"),
    ("New Year holiday, subject to confirmation", "unknown"),
    ("Adjusted Holiday / Something never seen", "unknown"),
    ("Something never seen", "unknown"),
    ("", "unknown"),
])
def test_r08_02_r09_04_classify_holiday_row_en_only_accepts_catalogued_phrases(desc, kind):
    assert classify_holiday_row_en(desc) == kind


def test_from_twse_legacy_rows_builds_contiguous_years_and_refuses_unknown_rows():
    rows = {
        2030: [["2030-01-01", "New Year"], ["2030-02-11", "No Trading. Market opens only for Clearing & Settlement"], ["2030-02-14", "Market Open"]],
        2031: [["2031-01-01", "New Year"]],
    }
    cal = TradingCalendar.from_twse_legacy_rows(rows, source_id="S06", recorded_at=REC_AT, version="t")
    assert cal.start == date(2030, 1, 1) and cal.end == date(2031, 12, 31)
    assert not cal.is_session(date(2030, 1, 1)) and not cal.is_session(date(2030, 2, 11)) and cal.is_session(date(2030, 2, 14))
    assert cal.is_session(date(2031, 1, 2)) and not cal.is_session(date(2031, 1, 4))    # sábado
    with pytest.raises(CalendarRangeError):
        TradingCalendar.from_twse_legacy_rows({2030: rows[2030], 2032: rows[2031]}, source_id="S06", recorded_at=REC_AT)
    with pytest.raises(CalendarRangeError):
        TradingCalendar.from_twse_legacy_rows({2030: [["2031-01-01", "New Year"]]}, source_id="S06", recorded_at=REC_AT)
    for bad in ("Fila nunca vista", "Typhoon closure cancelled; normal trading", "Market Open: No trading due to typhoon"):
        with pytest.raises(UnclassifiedCalendarRow):
            TradingCalendar.from_twse_legacy_rows({2030: [["2030-05-05", bad]]}, source_id="S06", recorded_at=REC_AT)


def test_reference_calendar_2021_2026_matches_known_official_dates():
    cal = load_twse_reference_calendar()
    assert (cal.start, cal.end) == (date(2021, 1, 1), date(2026, 12, 31))
    assert len(cal.sessions_between(date(2021, 1, 1), date(2026, 12, 31))) == 1462
    for closed in (date(2024, 1, 1), date(2024, 2, 6), date(2024, 2, 14), date(2024, 4, 4), date(2024, 10, 10), date(2021, 2, 5)):
        assert not cal.is_session(closed), closed
    for open_ in (date(2024, 2, 15), date(2024, 1, 2), date(2025, 12, 31)):
        assert cal.is_session(open_), open_
    # la lista anual oficial NO contiene los cierres extraordinarios por tifón: son sesiones para este calendario;
    # el protocolo necesita una fuente de cierres sobrevenidos (informe 11 §4)
    for typhoon in (date(2024, 7, 24), date(2024, 7, 25), date(2024, 10, 2), date(2024, 10, 3), date(2024, 10, 31)):
        assert cal.is_session(typhoon), typhoon
    assert cal.version.startswith("captured_2026-09-09")
