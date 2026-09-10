"""Pruebas del adaptador de cotizaciones diarias oficiales por fecha (TWSE MI_INDEX, TPEx dailyQuotes): sin red.
Incluye los contraejemplos de la ronda 16 (R16-01, R16-04, R16-05)."""
import json
from datetime import date, time
from decimal import Decimal as D

import pytest

from twlab.sources import twse_daily as td
from twlab.store import RawStore
from twlab.timeutil import taipei

TWSE_FIELDS = ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差"]
TPEX_FIELDS = ["代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "均價", "成交股數", "成交金額(元)", "成交筆數", "最後買價", "最後買量(張數)",
               "最後賣價", "最後賣量(張數)", "發行股數", "次日 參考價"]


def _put(store, source_id, dataset, body):
    return store.put(source_id=source_id, dataset=dataset, payload=json.dumps(body, ensure_ascii=False).encode("utf-8"), url="u",
                     http_status=200, content_type="application/json", extra={})


def twse_body(date_str, rows, fields=TWSE_FIELDS):
    return {"stat": "OK", "date": date_str, "tables": [
        {"title": "價格指數(臺灣證券交易所)", "fields": ["指數", "收盤指數"], "data": [["發行量加權股價指數", "1"]]},
        {"title": f"{date_str} 每日收盤行情(全部(不含權證、牛熊證、可展延牛熊證))", "fields": fields, "data": rows}]}


def tpex_body(date_str, rows, fields=TPEX_FIELDS):
    return {"date": date_str, "tables": [{"title": "上櫃股票行情", "fields": fields, "data": rows}, {"title": "管理股票", "fields": fields, "data": []}]}


def test_num_parses_commas_and_placeholders():
    assert td._num("1,234,567") == D("1234567") and td._num("15.26") == D("15.26")
    assert td._num("--") is None and td._num("") is None and td._num("除息") is None and td._num("X") is None and td._num("Infinity") is None


def test_twse_rows_and_bars_from_mi_index(tmp_path):
    store = RawStore(tmp_path)
    rows = [["2330", "台積電", "14,102,018", "43,438", "33,917,316,870", "2,415.00", "2,415.00", "2,390.00", "2,410.00", "+", "5.00"],
            ["9999", "sin precio", "48", "18", "1,606", "--", "--", "--", "--", " ", "0.00"]]
    rec = _put(store, "twse", f"{td.TWSE_DATASET}/2026-09-04", twse_body("20260904", rows))
    bars = td.bars_twse(date(2026, 9, 4), td.twse_rows(store, rec))
    b = bars["2330"]
    assert b.open == D("2415.00") and b.close == D("2410.00") and b.volume_shares == 14_102_018 and b.value_twd == D("33917316870")
    assert b.transactions == 43_438 and b.has_regular_price and b.available_at == taipei(date(2026, 9, 4), time(13, 30)) + td.PRICE_AVAILABILITY_LAG
    assert bars["9999"].has_regular_price is False and bars["9999"].volume_shares == 48
    closed = _put(store, "twse", f"{td.TWSE_DATASET}/2024-10-31", {"stat": "很抱歉，沒有符合條件的資料!", "type": "ALLBUT0999"})
    assert td.twse_rows(store, closed) is None
    assert set(td.captured_sessions(store, "twse", td.TWSE_DATASET)) == {date(2026, 9, 4), date(2024, 10, 31)}


def test_tpex_rows_and_bars_from_daily_quotes(tmp_path):
    store = RawStore(tmp_path)
    rows = [["6488", "環球晶", "981.00", "+28.00", "953.00", "983.00", "940.00", "965.31", "8,479,505", "8,185,360,883", "17,795",
             "980.00", "3", "981.00", "5", "435,000,000", "981.00", "1079.00", "883.00"]]
    rec = _put(store, "tpex", f"{td.TPEX_DATASET}/2026-09-04", tpex_body("20260904", rows))
    b = td.bars_tpex(date(2026, 9, 4), td.tpex_rows(store, rec))["6488"]
    assert b.open == D("953.00") and b.close == D("981.00") and b.high == D("983.00") and b.low == D("940.00")
    assert b.volume_shares == 8_479_505 and b.value_twd == D("8185360883") and b.transactions == 17_795
    empty = _put(store, "tpex", f"{td.TPEX_DATASET}/2026-09-05", tpex_body("20260905", []))
    assert td.tpex_rows(store, empty) is None


def test_r16_01_body_date_must_match_the_archived_session(tmp_path):
    store = RawStore(tmp_path)
    rows = [["2330", "台積電", "1,000", "1", "100,000", "100", "100", "100", "100", "+", "0"]]
    rec = _put(store, "twse", f"{td.TWSE_DATASET}/2024-01-05", twse_body("20240112", rows))       # cuerpo del 12-01 archivado como 05-01
    with pytest.raises(td.DailyQuoteSchemaError, match="R16-01"):
        td.twse_rows(store, rec)
    rec2 = _put(store, "tpex", f"{td.TPEX_DATASET}/2024-01-05", tpex_body("20240112", []))
    with pytest.raises(td.DailyQuoteSchemaError, match="R16-01"):
        td.tpex_rows(store, rec2)


def test_r16_04_repeated_symbol_rows_are_an_error_not_an_overwrite():
    rows = [["2330", "台積電", "1,000", "1", "100,000", "100", "100", "100", "100", "+", "0"],
            ["2330", "台積電", "1,000", "1", "200,000", "200", "200", "200", "200", "+", "0"]]
    with pytest.raises(td.DailyQuoteSchemaError, match="R16-04"):
        td.bars_twse(date(2024, 1, 5), [dict(zip(TWSE_FIELDS, r)) for r in rows])
    trows = [["6488", "環球晶", "100", "+1", "100", "100", "100", "100", "1,000", "100,000", "1"] + [""] * 6,
             ["6488", "環球晶", "200", "+1", "200", "200", "200", "200", "1,000", "200,000", "1"] + [""] * 6]
    with pytest.raises(td.DailyQuoteSchemaError, match="R16-04"):
        td.bars_tpex(date(2024, 1, 5), [dict(zip(TPEX_FIELDS, r)) for r in trows])


def test_r16_05_missing_columns_break_the_schema_instead_of_becoming_zeros(tmp_path):
    store = RawStore(tmp_path)
    rec = _put(store, "twse", f"{td.TWSE_DATASET}/2024-01-05", twse_body("20240105", [["2330", "台積電", "100", "100"]], fields=["證券代號", "證券名稱", "開盤價", "收盤價"]))
    with pytest.raises(td.DailyQuoteSchemaError, match="R16-05"):
        td.twse_rows(store, rec)
    with pytest.raises(td.DailyQuoteSchemaError, match="R16-05"):
        td.bars_twse(date(2024, 1, 5), [{"證券代號": "2330", "開盤價": "100", "收盤價": "100"}])
    rec2 = _put(store, "tpex", f"{td.TPEX_DATASET}/2024-01-05", tpex_body("20240105", [["6488", "x", "100", "+1", "100"]], fields=["代號", "名稱", "收盤", "漲跌", "開盤"]))
    with pytest.raises(td.DailyQuoteSchemaError, match="R16-05"):
        td.tpex_rows(store, rec2)
