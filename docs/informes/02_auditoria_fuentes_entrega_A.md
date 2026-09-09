# Auditoría de fuentes · Entrega A (primera pasada)

**Fecha de captura:** 9 de septiembre de 2026, tarde-noche hora local del usuario (madrugada del 10-09 en Taipei). Los archivos crudos de esta pasada están en el scratchpad de la sesión; la captura reproducible con `ingested_at` real empieza con `scripts/capture_daily.py`.

Estado de cada fuente: `candidate` hasta superar la muestra de §6.3 de la investigación (retirada, cambio de mercado, revisión de ingresos, dividendo, división, suspensión, cierre extraordinario, noticia corregida). Ninguna fuente está `validated`.

## 1. TWSE OpenAPI — `https://openapi.twse.com.tw/v1` (S07)

Swagger 2.0, 143 endpoints, JSON sin autenticación. Fechas en ROC compacto (`1150908`), excepto `company/suspendListingCsvAndHtml` (`115/09/01`). Valores numéricos como cadenas. **Sólo instantánea actual: no acepta fecha.**

| Endpoint | Filas | Uso previsto | Campo de sesión / publicación | Unidades y notas |
|---|---|---|---|---|
| `opendata/t187ap03_L` | 1.094 | Censo de sociedades cotizadas (sin ETF) | 出表日期 | 產業別 código; 上市日期 gregoriano `19620209`; 已發行普通股數 |
| `opendata/t187ap03_P` | 301 | Emisores públicos no cotizados (contexto) | 出表日期 | — |
| `opendata/t187ap04_L` | 108 | **Anuncios materiales con hora**: 發言日期 + 發言時間 (`3220` = 00:32:20) | 發言日期/發言時間 | Cuerpo en chino tradicional; 事實發生日 ≠ publicación |
| `opendata/t187ap05_L` | 1.085 | Ingresos mensuales | 出表日期 (fecha del informe agregado, no por empresa) | **Miles de TWD** (台泥 jul-2026: 13.744.103) |
| `opendata/t187ap45_L` | 1.226 | Dividendos decididos | 董事會（擬議）股利分派日, 股東會日期 | TWD por acción |
| `exchangeReport/STOCK_DAY_ALL` | 1.382 | OHLCV diario (incluye ETF/ETN) | Date | Volumen en acciones, importe en TWD |
| `exchangeReport/BWIBBU_ALL` | 1.083 | PER, rentabilidad por dividendo, P/B | Date | Cadenas vacías cuando no aplica |
| `exchangeReport/MI_INDEX` | 273 | Cierres de índices, incluye 寶島股價指數 | 日期 | — |
| `exchangeReport/MI_INDEX4` | 6 | Importe cruzado TWSE+TPEx y Formosa | Date | — |
| `indicesReport/FRMSA` | 6 | **Formosa Index y Formosa Total Return Index** | Date | Sólo últimos días |
| `indicesReport/MFI94U` | 6 | TAIEX Total Return | Date | — |
| `exchangeReport/TWT48U_ALL` | 83 | Calendario ex-derechos/ex-dividendo | Date | 現金股利 por acción |
| `exchangeReport/TWTAWU` | 1 | Suspensiones vigentes con hora (`080000`) | TradingHaltDate/Time | — |
| `exchangeReport/TWT85U` | 10 | Valores en negociación alterada | — | — |
| `holidaySchedule/holidaySchedule` | 27 | Calendario oficial 2026 | Date | **Mezcla cierres con filas informativas de negociación** (2-ene, 11-feb, 23-feb son sesiones, no cierres; R01-01). 18 cierres en día laborable → 243 sesiones |
| `company/suspendListingCsvAndHtml` | 265 | Retiradas históricas | DelistingDate (`115/09/01`) | Sin precio terminal |
| `company/newlisting` | 792 | Altas y proceso de admisión | ApplicationDate…ListingDate | Nota 創新板 para tablero de innovación |
| `opendata/t187ap06_L_*`, `t187ap07_L_*` | — | Estados financieros por tipo de industria (ci, basi, fh, ins, bd, mim) | — | No probados en esta pasada |

Endpoints que respondieron 302 (no disponibles): `opendata/t187ap03_O`, `fund/TWT38U`.

## 2. TPEx OpenAPI — `https://www.tpex.org.tw/openapi/v1` (S08)

OpenAPI 3.0.0, 225 endpoints, JSON sin autenticación. La raíz `https://www.tpex.org.tw/openapi/` carga el swagger desde `swagger.json` (no `v1/swagger.json`, que redirige). Mayoría de fechas ROC compacto; `tpex_index` usa gregoriano compacto `20260909`.

| Endpoint | Filas | Uso previsto | Campo de sesión / publicación | Notas |
|---|---|---|---|---|
| `mopsfin_t187ap03_O` | 890 | Censo de sociedades TPEx | Date | Claves en inglés (`SecuritiesCompanyCode`, `DateOfListing`) |
| `mopsfin_t187ap03_R` | 363 | Censo ESB/興櫃 (sólo catálogo) | Date | — |
| `mopsfin_t187ap04_O` | 47 | Anuncios materiales con hora | 發言日期/發言時間 | Igual estructura que TWSE |
| `mopsfin_t187ap05_O` | 890 | Ingresos mensuales TPEx | 出表日期 | Miles de TWD |
| `t187ap05_R` | — | Ingresos mensuales ESB | — | — |
| `mopsfin_t187ap39_O` | — | Dividendos aprobados por consejo | — | — |
| `tpex_mainboard_quotes` | 1.014 | Cierre diario (incluye ETF/bonos) | Date | `TradingShares`, `TransactionAmount`, `NextLimitUp/Down` |
| `tpex_reward_index` | 7 | **TPEx Index y TPEx Total Return Index** | Date | — |
| `tpex_index` | 7 | OHLC del índice TPEx | Date gregoriano | — |
| `tpex_spendi_history` | 362 | Historial de suspensiones/reanudaciones del año | DateOfSuspended/ResumedTrading + hora | Filas separadas para suspensión y reanudación |
| `tpex_cmode` | 20 | Negociación alterada, gestionada, suspendida | Date | Marcas `Ｙ` en ancho completo |
| `tpex_exright_daily`, `tpex_exright_prepost` | 9 / — | Ex-derechos y precio de referencia | Date | `OpeningReferencePrice`, `LimitUp/Down` |
| `tpex_3insti_daily_trading` | 899 | Flujos de tres institucionales por valor | Date | Encabezados largos con espacios irregulares |
| `tpex_esb_latest_statistics` | 363 | Cotizaciones ESB | Date + Time (`163004`) | Unidades distintas al tablero principal |

## 3. FinMind — `https://api.finmindtrade.com/api/v4/data` (S10–S12)

Sin token (nivel gratuito): respondió en todas las consultas de prueba; el límite de tasa no se expuso en cabeceras y deberá medirse. **Precios ajustados (`TaiwanStockPriceAdj`) exigen nivel de pago**; el laboratorio usa nominales, así que no es una carencia.

| Dataset | Observación | Clase de disponibilidad propuesta |
|---|---|---|
| `TaiwanStockInfo` | 4.319 filas: twse 2.399, tpex 1.373, emerging 547. Incluye ETF (271 TWSE), ETN, DR (36), 受益證券 y filas de índice. `date` = última actualización de FinMind (3.319 filas con 2026-09-10), no fecha de alta. | Metadato; no temporal |
| `TaiwanStockPrice` | Histórico nominal desde ≥2021 (TSMC 2021-01-04 close 536). Campos `Trading_Volume` (acciones), `Trading_money` (TWD). | `conservative_inference` hasta medir latencia |
| `TaiwanStockMonthRevenue` | `date` = primer día del mes de publicación; `revenue` en **TWD**; `create_time` vacío en 2021 y con fecha de rastreo en 2026 (`2026-06-10`, `2026-07-13`, `2026-08-10`). | Histórico: **`unknown`** (sin evidencia de publicación por versión; el plazo legal no acredita publicación ni excluye correcciones posteriores — R01-24). La regla «día 10/15 → siguiente sesión» sólo como experimento de sensibilidad registrado. 2026: `create_time` es cota superior, no timestamp de publicación |
| `TaiwanStockDividend` | Incluye `AnnouncementDate` + `AnnouncementTime` (`2020-11-12 17:05:40`), `CashExDividendTradingDate`, `CashDividendPaymentDate`. | `verified_version` si se confirma contra MOPS |
| `TaiwanStockDelisting` | 725 filas (todos los tipos), sin precio terminal. | Metadato; requiere precio terminal externo |

## 4. Otras comprobaciones

- `exchange_calendars` 4.13.2 (`XTAI`): 243 sesiones en 2026, **coincidentes** con la lista oficial una vez clasificadas correctamente sus filas (mi lectura inicial de 240 sesiones era errónea; corregida tras R01-01). Cobertura 2006-09-11 → 2027-09-09. Sirve de contraste, no de autoridad.
- Formosa TR y TAIEX TR: sólo seis filas recientes por endpoint. Historial pendiente (endpoint heredado `www.twse.com.tw/indicesReport/FRMSA?date=` o TEJ).
- Ningún endpoint probado exige credenciales ni aceptó condiciones nuevas. Los términos de reutilización de TWSE/TPEx/FinMind **no se han revisado jurídicamente**; hasta entonces, uso privado de investigación.

## 5. Hallazgos que cambian el diseño

1. Captura diaria obligatoria desde ya (A1 del informe 01), con medición de pérdidas entre capturas.
2. Anuncios materiales oficiales como primera clase documental con hora; `verified_original` sólo con evidencia de versión (captura con hash) (A2).
3. Calendario oficial como autoridad **con clasificación de filas**; XTAI como contraste (A3 retirado y reemplazado tras R01-01).
4. Serie de referencia descubierta, no validada (A4).
5. Contrato de unidades por endpoint: miles vs. TWD, con prueba de equivalencia emparejada pendiente (A5, R01-25).
6. **Latencia de TWSE medida con reloj real** (primera corrida de `scripts/capture_daily.py`, 37 endpoints, 0 fallos, 15 MB): a las 02:04 del 10-09-2026 hora de Taipei, es decir 12,5 horas después del cierre de la sesión del 9-09, `STOCK_DAY_ALL`, `BWIBBU_ALL`, `MI_INDEX` y `FRMSA` todavía traían la sesión del **8-09**, mientras `tpex_mainboard_quotes`, `tpex_reward_index`, `tpex_3insti_daily_trading` y los anuncios materiales de TWSE (`t187ap04_L`) ya traían el **9-09**. Conclusión provisional: las tablas diarias de TWSE OpenAPI se publican con al menos una sesión de retraso a esa hora; la hora exacta de refresco se fijará con capturas a distintas horas. Ningún paquete asumirá el cierre de TWSE «disponible al cierre».

## 6. Evidencia archivada en el repositorio

`data/audit/manifest_2026-09-09.jsonl` es el manifiesto de la primera corrida real de `scripts/capture_daily.py`: 37 endpoints, sha256 de cada respuesta, `ingested_at` del reloj del sistema (UTC), código HTTP, tipo de contenido, filas y latencia. Los bytes crudos (15 MB) están en `data/raw/` fuera de git y se verifican con `RawStore.verify()`. Las muestras exploratorias anteriores (curl manual, sin `RawStore`) no tienen hora verificable y no se usan como evidencia.

## 7. Lo que esta pasada no cubre

No se probaron los estados financieros trimestrales, los endpoints heredados con parámetro de fecha, MOPS directamente, TDCC, EDGAR ni ALFRED. No se midió el límite de tasa de FinMind ni la hora exacta a la que TWSE publica `STOCK_DAY_ALL`. No se pidió muestra a TEJ.
