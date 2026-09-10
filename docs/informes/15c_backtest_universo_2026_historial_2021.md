# Backtest del universo completo con historial largo (2021-2026): mismo periodo, Q1 entrenado con más semanas

**Qué es:** la corrida del informe 15 (mismo universo de 1.937 acciones, mismas 17 semanas operadas de mayo-septiembre 2026, mismo capital de 5.000.000 TWD y lotes de 1.000, **sin dividendos**) cargando las cotizaciones oficiales por fecha desde el 4 de enero de 2021 (`official_daily_quotes:2021-01-04..2026-09-09`), de modo que Q1 se entrena con todas las semanas de etiqueta disponibles desde 2021 (mínimo configurado: 52, frente a 40 en el informe 15); primera manifestación de entrenamiento: `2026-05-10: q1:tabular_ridge_lgbm_rank_v2|rows=427457|weeks=248|labels=2021-W28..2026-W19|lgbm=yes|data=ccfe0024aa59286a|cfg=1328b1878677`. Etiqueta: `universe_longhist_2021_2026`; cifras tomadas de `data/store/backtest_universe_longhist_2021_2026.json`.

**Qué cambia respecto al informe 15:** Q0 y A1 no aprenden, así que sólo cambian si cambia el universo elegible (835 elegibles por semana de media frente a 835). Medias semanales netas frente al informe 15: Q0: −0,87 % frente a −0,87 %; Q1: −0,87 % frente a −1,04 %; A1: +0,35 % frente a +0,35 %. Entradas fallidas de Q1: 0 (informe 15: 16).

**Qué NO demuestra:** lo mismo que el informe 15: 17 semanas, sin dividendos, censo vigente, costes ilustrativos. Más historial de entrenamiento no añade semanas de evaluación.

## Resultado en una tabla (17 semanas operadas)

| | Q0 momentum | Q1 tabular | A1 azar | Universo elegible (bruto) |
|---|---|---|---|---|
| Media semanal bruta de las selecciones | −0,64 % | +0,05 % | +2,35 % | +1,23 % |
| Media semanal neta de la cartera (apertura→cierre) | −0,87 % | −0,87 % | +0,35 % | — |
| Semanas con neto > 0 (de las medibles) | 5/16 | 3/16 | 9/16 | — |
| Entradas fallidas (lote más caro que el nocional del puesto) | 9 de 80 | 0 de 80 | 4 de 80 | — |
| Coste medio sobre importe comprado + vendido heredado | 0,73 % | 0,74 % | 0,75 % | — |
| Patrimonio final (inicial 5.000.000 TWD) | 3.969.855 (−20,6 %) | 4.310.018 (−13,8 %) | 4.786.273 (−4,3 %) | — |
| Exceso neto emparejado frente a A1 | +0,80 % con 7 semanas emparejables: **no estimable** | −0,47 % con 11 semanas emparejables: **no estimable** | — | — |

## Lista de la semana en curso (2026-W37, corte 2026-09-06 18:00 Taipei)

Reconstrucción emitida después de la entrada simulada (`forecast/universe_longhist_2021_2026/<pronosticador>/2026-W37` en `data/raw`), no predicción prospectiva.

| Pronosticador | Selección (símbolo, nombre) | Estado de la entrada simulada |
|---|---|---|
| Q0 momentum 20 sesiones | 6538 倉和 · 2221 大甲 · 3406 玉晶光 · 6933 AMAX-KY · 3234 光環 | 4 de 5 ejecutadas; sin lote posible: 3406 |
| Q1 tabular | 2633 台灣高鐵 · 4105 東洋 · 4536 拓凱 · 1227 佳格 · 6669 緯穎 | 4 de 5 ejecutadas; sin lote posible: 6669 |
| A1 azar (control) | 1809 中釉 · 2316 楠梓電 · 2880 華南金 · 3293 鈊象 · 3088 艾訊 | 5 de 5 ejecutadas |

## Límites específicos de esta corrida

- 22,120 barras sin precio de sesión regular excluidas; avisos de carga: sin derechos: la fuente oficial por fecha no trae dividendos; libro y etiquetas operan sin ellos; sesiones oficiales sin captura: 1 (p. ej. TPEX:2024-06-04); sesiones oficiales sin datos (cierres sobrevenidos u otros): 14 (p. ej. TWSE:2023-08-03, TPEX:2023-08-03, TWSE.
- Sin dividendos en todo el historial 2021-2026: las etiquetas de Q1 de la temporada de reparto de cada año están sesgadas a la baja.
- Todo lo demás: informe 15 §Límites.

---

*A continuación, el informe generado automáticamente por `scripts/run_backtest.py` (tablas y selecciones semana a semana).*

## Informe generado: backtest universe_longhist_2021_2026

Periodo 2026-05-04 → 2026-09-09 · universo 1937 valores (official_daily_quotes:2021-01-04..2026-09-09) · 17 semanas operadas, 0 sin sesiones, 1 pendientes de desenlace.

Costes ilustrativos (no contratados); universo del censo vigente; disponibilidad de barras por política de 24 h. Nada de esto es una estimación de rendimiento futuro.

| Pronosticador | Media semanal neta apertura→cierre | Media bruta de las selecciones | Costes/semana sobre compras brutas + ventas brutas heredadas | Semanas > 0 (de las medibles) | Patrimonio final | Exceso neto vs A1 (IC 95 %) |
|---|---|---|---|---|---|---|
| Q0 (`rule:momentum_20_sessions_v1`) | -0.87 % | -0.64 % | +0.73 % | 5/16 | 3,969,855 TWD | +0.80 % (incertidumbre no estimable: remuestreo degenerado, n=7) |
| Q1 (`q1:tabular_ridge_lgbm_rank_v2`) | -0.87 % | +0.05 % | +0.74 % | 3/16 | 4,310,018 TWD | -0.47 % (incertidumbre no estimable: remuestreo degenerado, n=11) |
| A1 (`rule:random_eligible_v1`) | +0.35 % | +2.35 % | +0.75 % | 9/16 | 4,786,273 TWD | — |

Referencia equiponderada del universo elegible (bruta, apertura→cierre): +1.23 % semanal.

## Límites

- Universo del censo vigente (sesgo de supervivencia); costes ilustrativos; disponibilidad de barras por política de 24 h, no verificada.
- Derechos (dividendos) según FinMind: la fecha y hora de anuncio acreditan el anuncio, no las revisiones posteriores de importes o fechas; no hay versiones históricas archivadas. Las etiquetas y la contabilidad que dependen de derechos son inferencia conservadora.
- Derechos ambiguos o inválidos detectados en la carga: 0 (etiquetas e intervalos de sus tenedores invalidados); avisos de carga en total: 3. Ejemplos: sin derechos: la fuente oficial por fecha no trae dividendos; libro y etiquetas operan sin ellos; sesiones oficiales sin captura: 1 (p. ej. TPEX:2024-06-04); sesiones oficiales sin datos (cierres sobrevenidos u otros): 14 (p. ej. TWSE:2023-08-03, TPEX:2023-08-03, TWSE:2024-07-2
- Un bootstrap con observaciones fijas o degenerado se declara como tal en la tabla; nunca como un IC ordinario.

## Selecciones semana a semana

| Semana | Q0 | Q1 | A1 |
|---|---|---|---|
| 2026-W20 | 3581 博磊 -12.5 %, 6861 睿生光電 +18.4 %, 2454 聯發科 (sin ejecutar: notional_below_one_lot), 4764 雙鍵 -5.0 %, 1595 川寶 -8.7 % → neto -2.70 % | 3045 台灣大 +4.1 %, 2897 王道銀行 -1.0 %, 9917 中保科 -1.8 %, 2412 中華電 +1.1 %, 2820 華票 -1.2 % → neto -0.49 % | 2104 國際中橡 -5.6 %, 1795 美時 -18.6 %, 2406 國碩 -6.5 %, 8039 台虹 +8.3 %, 5457 宣德 -9.3 % → neto -6.95 % |
| 2026-W21 | 6861 睿生光電 +4.3 %, 6658 聯策 -1.5 %, 3430 奇鈦科 +5.5 %, 3581 博磊 +18.7 %, 5464 霖宏 +32.0 % → neto +10.30 % | 6024 群益期 +0.5 %, 2897 王道銀行 +0.0 %, 9917 中保科 -0.4 %, 2820 華票 +1.2 %, 2838 聯邦銀 -0.5 % → neto -0.60 % | 2340 台亞 +11.4 %, 4721 美琪瑪 +2.1 %, 1307 三芳 -0.9 %, 3041 揚智 +19.1 %, 6451 訊芯-KY -7.9 % → neto +4.47 % |
| 2026-W22 | 6173 信昌電 +12.1 %, 2492 華新科 +28.8 %, 5464 霖宏 +16.1 %, 3090 日電貿 -0.2 %, 2327 國巨* +8.7 % → neto +10.63 % | 2820 華票 -0.3 %, 2897 王道銀行 -2.0 %, 2727 王品 +0.0 %, 4904 遠傳 -0.9 %, 2903 遠百 -2.2 % → neto -1.84 % | 6640 均華 (sin ejecutar: notional_below_one_lot), 1210 大成 +0.4 %, 2801 彰銀 -0.5 %, 6505 台塑化 +0.2 %, 8936 國統 +4.2 % → neto +0.22 % |
| 2026-W23 | 3026 禾伸堂 -6.7 %, 2492 華新科 +2.0 %, 6173 信昌電 -5.7 %, 8042 金山電 -11.3 %, 5464 霖宏 -23.2 % → neto -8.63 % | 2820 華票 +2.4 %, 9917 中保科 +2.2 %, 2897 王道銀行 +3.8 %, 8415 大國鋼 +2.3 %, 6024 群益期 +4.1 % → neto +2.11 % | 6672 騰輝電子-KY -1.8 %, 5904 寶雅* +1.1 %, 4551 智伸科 -10.4 %, 6776 展碁國際 +3.9 %, 3479 安勤 -5.1 % → neto -3.17 % |
| 2026-W24 | 2492 華新科 +9.2 %, 6207 雷科 -5.0 %, 6449 鈺邦 +26.0 %, 5321 美而快 -12.2 %, 6116 彩晶 -6.3 % → neto +0.75 % | 6803 崑鼎 +0.3 %, 9917 中保科 +5.6 %, 4974 亞泰 +5.4 %, 2820 華票 +4.1 %, 4536 拓凱 +6.8 % → neto +3.46 % | 3707 漢磊 +11.9 %, 8234 新漢 +1.6 %, 2460 建通 +8.6 %, 2383 台光電 (sin ejecutar: notional_below_one_lot), 3016 嘉晶 +17.3 % → neto +6.82 % |
| 2026-W25 | 3026 禾伸堂 +7.4 %, 2478 大毅 +29.6 %, 2492 華新科 +26.1 %, 3147 大綜 -3.3 %, 8454 富邦媒 +3.3 % → neto +10.50 % | 6803 崑鼎 -0.3 %, 4736 泰博 +0.4 %, 2636 台驊控股 -2.5 %, 2707 晶華 -0.3 %, 9911 櫻花 -2.1 % → neto -1.67 % | 3260 威剛 +2.1 %, 6462 神盾 +1.8 %, 6651 全宇昕 +13.9 %, 3588 通嘉 +4.0 %, 2455 全新 +12.1 % → neto +5.14 % |
| 2026-W26 | 2243 宏旭-KY +6.0 %, 6654 天正國際 -14.4 %, 2061 風青 +12.4 %, 2492 華新科 -12.3 %, 3026 禾伸堂 -18.1 % → neto -3.53 % | 6023 元大期貨 -0.5 %, 6803 崑鼎 +0.5 %, 1210 大成 +0.9 %, 2636 台驊控股 -2.8 %, 4536 拓凱 +0.6 % → neto -1.01 % | 1305 華夏 -2.6 %, 4542 科嶠 -9.3 %, 8076 伍豐 -4.9 %, 6834 天二科技 +8.5 %, 3591 艾笛森 +9.3 % → neto -0.22 % |
| 2026-W27 | 2483 百容 +20.5 %, 2243 宏旭-KY +31.5 %, 1714 和桐 +25.0 %, 5328 華容 +15.7 %, 2061 風青 +23.3 % → neto +21.82 % | 6024 群益期 +2.3 %, 6170 統振 +0.6 %, 6803 崑鼎 -3.0 %, 2636 台驊控股 +4.1 %, 2820 華票 -5.3 % → neto -0.96 % | 5292 華懋 +8.1 %, 2543 皇昌 +2.8 %, 3231 緯創 +3.2 %, 4585 達明 +15.0 %, 2607 榮運 -4.9 % → neto +3.53 % |
| 2026-W28 | 2483 百容 (salida bloqueada), 2243 宏旭-KY (salida bloqueada), 5328 華容 (salida bloqueada), 4556 旭然 (salida bloqueada), 2466 冠西電 (salida bloqueada) → sin intervalo medible (stale_price) | 6024 群益期 (salida bloqueada), 2897 王道銀行 (salida bloqueada), 2727 王品 (salida bloqueada), 2707 晶華 (salida bloqueada), 2745 五福 (salida bloqueada) → sin intervalo medible (stale_price) | 4147 中裕 (salida bloqueada), 8182 加高 (salida bloqueada), 8271 宇瞻 (salida bloqueada), 8105 凌巨 (salida bloqueada), 4967 十銓 (salida bloqueada) → sin intervalo medible (stale_price) |
| 2026-W29 | (abstained: no_eligible_securities) → neto del libro -6.29 % (posiciones heredadas) | (abstained: no_eligible_securities) → neto del libro -3.43 % (posiciones heredadas) | (abstained: no_eligible_securities) → neto del libro -11.40 % (posiciones heredadas) |
| 2026-W30 | 2466 冠西電 -22.1 %, 2434 統懋 -6.6 %, 3055 蔚華科 -17.1 %, 6226 光鼎 -7.4 %, 4707 磐亞 -10.9 % → neto -12.91 % | 2206 三陽工業 -4.1 %, 2897 王道銀行 -3.3 %, 6024 群益期 +0.2 %, 2801 彰銀 +0.8 %, 2707 晶華 -0.6 % → neto -2.09 % | 4585 達明 -1.8 %, 2458 義隆 +1.2 %, 6579 研揚 +20.7 %, 6205 詮欣 -0.2 %, 2609 陽明 +3.2 % → neto +3.31 % |
| 2026-W31 | 4556 旭然 -40.0 %, 2434 統懋 -23.7 %, 8039 台虹 -26.2 %, 2466 冠西電 -4.1 %, 6505 台塑化 -13.3 % → neto -20.42 % | 5880 合庫金 +7.0 %, 2845 遠東銀 +0.4 %, 6024 群益期 -10.2 %, 2707 晶華 -0.6 %, 2834 臺企銀 +0.6 % → neto -1.29 % | 1717 長興 -2.4 %, 2415 錩新 -5.5 %, 1714 和桐 -11.8 %, 4540 全球傳動 -10.2 %, 3060 銘異 -6.1 % → neto -7.83 % |
| 2026-W32 | 6598 ABC-KY -4.3 %, 6243 迅杰 -4.2 %, 3685 元創精密 +9.5 %, 6505 台塑化 -0.6 %, 2357 華碩 +3.4 % → neto -0.04 % | 1210 大成 -5.9 %, 2845 遠東銀 -1.5 %, 4736 泰博 +1.6 %, 2633 台灣高鐵 -0.8 %, 2820 華票 -2.1 % → neto -2.46 % | 6199 天品 -3.9 %, 6223 旺矽 (sin ejecutar: notional_below_one_lot), 5880 合庫金 -3.0 %, 4916 事欣科 +14.9 %, 8050 廣積 +28.3 % → neto +6.35 % |
| 2026-W33 | 8039 台虹 +9.0 %, 6863 永道-KY -17.6 %, 3653 健策 (sin ejecutar: notional_below_one_lot), 2059 川湖 (sin ejecutar: notional_below_one_lot), 6533 晶心科 -3.0 % → neto -2.50 % | 2845 遠東銀 -0.4 %, 2707 晶華 -1.9 %, 5880 合庫金 -8.5 %, 9925 新保 -0.4 %, 2897 王道銀行 -1.5 % → neto -3.14 % | 8096 擎亞 -13.7 %, 1232 大統益 -4.4 %, 1563 巧新 +8.0 %, 9802 鈺齊-KY +1.3 %, 6937 天虹 +12.7 % → neto -0.05 % |
| 2026-W34 | 3081 聯亞 (sin ejecutar: notional_below_one_lot), 3605 宏致 -17.5 %, 7711 永擎 -3.0 %, 2059 川湖 (sin ejecutar: notional_below_one_lot), 3653 健策 (sin ejecutar: notional_below_one_lot) → neto -3.75 % | 2707 晶華 +3.1 %, 2845 遠東銀 +3.0 %, 2633 台灣高鐵 +0.6 %, 4536 拓凱 +3.0 %, 9925 新保 -1.0 % → neto +0.85 % | 2363 矽統 -4.9 %, 2207 和泰車 +0.8 %, 9914 美利達 +0.3 %, 1563 巧新 -2.2 %, 2465 麗臺 -10.4 % → neto -3.82 % |
| 2026-W35 | 3490 單井 -12.4 %, 2059 川湖 (sin ejecutar: notional_below_one_lot), 3498 陽程 -0.8 %, 3441 聯一光電 +14.5 %, 3081 聯亞 (sin ejecutar: notional_below_one_lot) → neto -0.20 % | 2633 台灣高鐵 +0.6 %, 9911 櫻花 -0.2 %, 2820 華票 +1.8 %, 2897 王道銀行 +1.0 %, 2753 八方雲集 -4.3 % → neto -0.85 % | 2360 致茂 (sin ejecutar: notional_below_one_lot), 5475 德宏 +16.9 %, 5284 jpp-KY -3.3 %, 2340 台亞 +10.7 %, 4764 雙鍵 +15.0 % → neto +7.29 % |
| 2026-W36 | 2491 吉祥全 -17.3 %, 6213 聯茂 -8.2 %, 3498 陽程 +1.6 %, 3081 聯亞 (sin ejecutar: notional_below_one_lot), 8039 台虹 -13.3 % → neto -6.92 % | 2633 台灣高鐵 -0.6 %, 4536 拓凱 -2.1 %, 2707 晶華 -0.6 %, 8415 大國鋼 +2.7 %, 2845 遠東銀 +1.9 % → neto -0.46 % | 6199 天品 +3.0 %, 6829 千附精密 +3.4 %, 6588 東典光電 -1.4 %, 3596 智易 -0.9 %, 5607 遠雄港 +10.1 % → neto +1.97 % |
| 2026-W37 | 6538 倉和, 2221 大甲, 3406 玉晶光 (sin ejecutar: notional_below_one_lot), 6933 AMAX-KY, 3234 光環 → pendiente | 2633 台灣高鐵, 4105 東洋, 4536 拓凱, 1227 佳格, 6669 緯穎 (sin ejecutar: notional_below_one_lot) → pendiente | 1809 中釉, 2316 楠梓電, 2880 華南金, 3293 鈊象, 3088 艾訊 → pendiente |
