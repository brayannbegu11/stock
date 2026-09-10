"""Pruebas del adaptador de cotizaciones diarias oficiales por fecha (TWSE MI_INDEX, TPEx dailyQuotes): sin red."""
import json
from datetime import date, time
from decimal import Decimal as D

from twlab.sources import twse_daily as td
from twlab.store import RawStore
from twlab.timeutil import taipei


def _put(store, source_id, dataset, body):
    return store.put(source_id=source_id, dataset=dataset, payload=json.dumps(body, ensure_ascii=False).encode("utf-8"), url="u",
                     http_status=200, content_type="application/json", extra={})


def test_num_parses_commas_and_placeholders():
    assert td._num("1,234,567") == D("1234567") and td._num("15.26") == D("15.26")
    assert td._num("--") is None and td._num("") is None and td._num("除息") is None and td._num("X") is None and td._num("Infinity") is None


def test_twse_rows_and_bars_from_mi_index(tmp_path):
    store = RawStore(tmp_path)
    body = {"stat": "OK", "date": "20260904", "tables": [
        {"title": "115年09月04日 價格指數(臺灣證券交易所)", "fields": ["指數", "收盤指數"], "data": [["發行量加權股價指數", "1"]]},
        {"title": "115年09月04日 每日收盤行情(全部(不含權證、牛熊證、可展延牛熊證))",
         "fields": ["證券代號", "證券名稱", "成交股數", "成交筆數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌(+/-)", "漲跌價差"],
         "data": [["2330", "台積電", "14,102,018", "43,438", "33,917,316,870", "2,415.00", "2,415.00", "2,390.00", "2,410.00", "+", "5.00"],
                  ["9999", "sin precio", "48", "18", "1,606", "--", "--", "--", "--", " ", "0.00"]]}]}
    rec = _put(store, "twse", f"{td.TWSE_DATASET}/2026-09-04", body)
    rows = td.twse_rows(store, rec)
    bars = td.bars_twse(date(2026, 9, 4), rows)
    b = bars["2330"]
    assert b.open == D("2415.00") and b.close == D("2410.00") and b.volume_shares == 14_102_018 and b.value_twd == D("33917316870")
    assert b.transactions == 43_438 and b.has_regular_price and b.available_at == taipei(date(2026, 9, 4), time(13, 30)) + td.PRICE_AVAILABILITY_LAG
    assert bars["9999"].has_regular_price is False and bars["9999"].volume_shares == 48
    closed = _put(store, "twse", f"{td.TWSE_DATASET}/2024-10-31", {"stat": "很抱歉，沒有符合條件的資料!", "type": "ALLBUT0999"})
    assert td.twse_rows(store, closed) is None
    assert set(td.captured_sessions(store, "twse", td.TWSE_DATASET)) == {date(2026, 9, 4), date(2024, 10, 31)}


def test_tpex_rows_and_bars_from_daily_quotes(tmp_path):
    store = RawStore(tmp_path)
    fields = ["代號", "名稱", "收盤", "漲跌", "開盤", "最高", "最低", "均價", "成交股數", "成交金額(元)", "成交筆數", "最後買價", "最後買量(張數)",
              "最後賣價", "最後賣量(張數)", "發行股數", "次日 參考價"]
    body = {"date": "20260904", "tables": [
        {"title": "上櫃股票行情", "fields": fields,
         "data": [["6488", "環球晶", "981.00", "+28.00", "953.00", "983.00", "940.00", "965.31", "8,479,505", "8,185,360,883", "17,795",
                   "980.00", "3", "981.00", "5", "435,000,000", "981.00", "1079.00", "883.00"]]},
        {"title": "管理股票", "fields": fields, "data": []}]}
    rec = _put(store, "tpex", f"{td.TPEX_DATASET}/2026-09-04", body)
    b = td.bars_tpex(date(2026, 9, 4), td.tpex_rows(store, rec))["6488"]
    assert b.open == D("953.00") and b.close == D("981.00") and b.high == D("983.00") and b.low == D("940.00")
    assert b.volume_shares == 8_479_505 and b.value_twd == D("8185360883") and b.transactions == 17_795
    empty = _put(store, "tpex", f"{td.TPEX_DATASET}/2026-09-05", {"date": "20260905", "tables": [{"title": "上櫃股票行情", "fields": fields, "data": []}]})
    assert td.tpex_rows(store, empty) is None
