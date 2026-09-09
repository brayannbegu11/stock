"""Registro de endpoints auditados el 9-09-2026 con su contrato mínimo.

Cada entrada documenta: fuente, dataset, URL, campo que identifica la
sesión o publicación, formato de fecha observado y unidades. Es el insumo
de ``scripts/capture_daily.py`` y de la tabla ``source_contract``.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Endpoint:
    source_id: str          # twse | tpex | finmind
    dataset: str            # nombre corto usado como carpeta en data/raw
    url: str
    purpose: str
    session_field: str | None = None      # campo con fecha de sesión / publicación
    date_format: str = "roc_compact"      # roc_compact | roc_slash | greg_compact | iso
    time_field: str | None = None
    units: dict[str, str] = field(default_factory=dict)
    instrument_scope: str = "mixed"       # companies | mixed (incluye ETF/ETN/bonos) | esb | index | calendar
    notes: str = ""


TWSE = "https://openapi.twse.com.tw/v1/"
TPEX = "https://www.tpex.org.tw/openapi/v1/"
FINMIND = "https://api.finmindtrade.com/api/v4/data?dataset="

ENDPOINTS: tuple[Endpoint, ...] = (
    # ---- TWSE ----------------------------------------------------------
    Endpoint("twse", "t187ap03_L", TWSE + "opendata/t187ap03_L", "censo sociedades cotizadas", "出表日期",
             instrument_scope="companies", notes="上市日期 en gregoriano compacto; 產業別 código"),
    Endpoint("twse", "t187ap03_P", TWSE + "opendata/t187ap03_P", "emisores públicos no cotizados", "出表日期",
             instrument_scope="companies"),
    Endpoint("twse", "t187ap04_L", TWSE + "opendata/t187ap04_L", "anuncios materiales con hora", "發言日期",
             time_field="發言時間", instrument_scope="companies", notes="hora HHMMSS sin ceros; 事實發生日 ≠ publicación"),
    Endpoint("twse", "t187ap05_L", TWSE + "opendata/t187ap05_L", "ingresos mensuales", "出表日期",
             units={"營業收入-當月營收": "TWD_thousands"}, instrument_scope="companies"),
    Endpoint("twse", "t187ap45_L", TWSE + "opendata/t187ap45_L", "dividendos decididos", "出表日期",
             units={"股東配發-盈餘分配之現金股利(元/股)": "TWD_per_share"}, instrument_scope="companies"),
    Endpoint("twse", "STOCK_DAY_ALL", TWSE + "exchangeReport/STOCK_DAY_ALL", "OHLCV diario", "Date",
             units={"TradeVolume": "shares", "TradeValue": "TWD"}, instrument_scope="mixed"),
    Endpoint("twse", "BWIBBU_ALL", TWSE + "exchangeReport/BWIBBU_ALL", "PER/yield/PB diario", "Date"),
    Endpoint("twse", "MI_INDEX", TWSE + "exchangeReport/MI_INDEX", "cierres de índices", "日期", instrument_scope="index"),
    Endpoint("twse", "MI_INDEX4", TWSE + "exchangeReport/MI_INDEX4", "importe cruzado y Formosa", "Date",
             units={"TradeValue": "TWD"}, instrument_scope="index"),
    Endpoint("twse", "FRMSA", TWSE + "indicesReport/FRMSA", "Formosa price y total return", "Date", instrument_scope="index"),
    Endpoint("twse", "MFI94U", TWSE + "indicesReport/MFI94U", "TAIEX total return", "Date", instrument_scope="index"),
    Endpoint("twse", "TWT48U_ALL", TWSE + "exchangeReport/TWT48U_ALL", "calendario ex-derechos", "Date",
             units={"CashDividend": "TWD_per_share"}),
    Endpoint("twse", "TWTAWU", TWSE + "exchangeReport/TWTAWU", "suspensiones vigentes", "TradingHaltDate",
             time_field="TradingHaltTime"),
    Endpoint("twse", "TWT85U", TWSE + "exchangeReport/TWT85U", "negociación alterada"),
    Endpoint("twse", "holidaySchedule", TWSE + "holidaySchedule/holidaySchedule", "calendario oficial", "Date",
             instrument_scope="calendar"),
    Endpoint("twse", "suspendListing", TWSE + "company/suspendListingCsvAndHtml", "retiradas", "DelistingDate",
             date_format="roc_slash", instrument_scope="companies"),
    Endpoint("twse", "newlisting", TWSE + "company/newlisting", "altas y admisión", "ListingDate", instrument_scope="companies"),
    # ---- TPEx ----------------------------------------------------------
    Endpoint("tpex", "t187ap03_O", TPEX + "mopsfin_t187ap03_O", "censo sociedades TPEx", "Date", instrument_scope="companies"),
    Endpoint("tpex", "t187ap03_R", TPEX + "mopsfin_t187ap03_R", "censo ESB", "Date", instrument_scope="esb"),
    Endpoint("tpex", "t187ap04_O", TPEX + "mopsfin_t187ap04_O", "anuncios materiales con hora", "發言日期",
             time_field="發言時間", instrument_scope="companies"),
    Endpoint("tpex", "t187ap05_O", TPEX + "mopsfin_t187ap05_O", "ingresos mensuales TPEx", "出表日期",
             units={"營業收入-當月營收": "TWD_thousands"}, instrument_scope="companies"),
    Endpoint("tpex", "t187ap05_R", TPEX + "t187ap05_R", "ingresos mensuales ESB", "出表日期",
             units={"營業收入-當月營收": "TWD_thousands"}, instrument_scope="esb"),
    Endpoint("tpex", "t187ap39_O", TPEX + "mopsfin_t187ap39_O", "dividendos aprobados por consejo", instrument_scope="companies"),
    Endpoint("tpex", "mainboard_quotes", TPEX + "tpex_mainboard_quotes", "cierre diario tablero principal", "Date",
             units={"TradingShares": "shares", "TransactionAmount": "TWD"}, instrument_scope="mixed"),
    Endpoint("tpex", "mainboard_peratio", TPEX + "tpex_mainboard_peratio_analysis", "PER/yield/PB", "Date"),
    Endpoint("tpex", "reward_index", TPEX + "tpex_reward_index", "TPEx index y total return", "Date", instrument_scope="index"),
    Endpoint("tpex", "index", TPEX + "tpex_index", "OHLC índice TPEx", "Date", date_format="greg_compact", instrument_scope="index"),
    Endpoint("tpex", "spendi_today", TPEX + "tpex_spendi_today", "suspensiones del día"),
    Endpoint("tpex", "spendi_history", TPEX + "tpex_spendi_history", "historial suspensiones", "DateOfSuspendedTrading",
             time_field="TimeOfSuspendedTrading"),
    Endpoint("tpex", "cmode", TPEX + "tpex_cmode", "negociación alterada/gestionada/suspendida", "Date"),
    Endpoint("tpex", "exright_daily", TPEX + "tpex_exright_daily", "ex-derechos del día", "Date"),
    Endpoint("tpex", "exright_prepost", TPEX + "tpex_exright_prepost", "ex-derechos previstos", "Date"),
    Endpoint("tpex", "3insti_daily", TPEX + "tpex_3insti_daily_trading", "flujos tres institucionales", "Date",
             units={"*": "shares"}),
    Endpoint("tpex", "esb_latest", TPEX + "tpex_esb_latest_statistics", "cotizaciones ESB", "Date", time_field="Time",
             instrument_scope="esb"),
    Endpoint("tpex", "ipo_no_limit", TPEX + "tpex_ipo_no_limit", "primeros cinco días sin límite", "Date"),
    # ---- FinMind (metadatos; histórico se pide aparte por valor) ---------
    Endpoint("finmind", "TaiwanStockInfo", FINMIND + "TaiwanStockInfo", "catálogo con tipo e industria", "date",
             date_format="iso", notes="date = última actualización de FinMind, no fecha de alta"),
    Endpoint("finmind", "TaiwanStockDelisting", FINMIND + "TaiwanStockDelisting", "retiradas (todos los tipos)", "date",
             date_format="iso"),
)


def by_source(source_id: str) -> list[Endpoint]:
    return [e for e in ENDPOINTS if e.source_id == source_id]
