# Backtest del universo completo, mayo-septiembre 2026 (Q0, Q1, A1; sin dividendos)

**Qué es:** el primer recorrido del protocolo sobre **todas** las acciones ordinarias del tablero principal de TWSE y TPEx (1,937 valores del maestro, informe 10), con las cotizaciones oficiales diarias por fecha (`twlab/sources/twse_daily.py`: TWSE `MI_INDEX`, TPEx `dailyQuotes`, capturadas el 9 y 10 de septiembre de 2026 para las sesiones desde julio de 2024; Astra comprobó que 15.538 pares TWSE–FinMind de 2025 coinciden exactamente). Periodo: cortes dominicales del 10 de mayo al 6 de septiembre de 2026 (18 semanas: 17 operadas y la semana en curso, pendiente de desenlace). La corrida no usa ningún LLM; es una reconstrucción histórica con datos archivados después de los cortes, **no** evidencia prospectiva (véase la lista de la semana más abajo). Etiqueta: `universe_2026-05-04_2026-09-09`; cifras tomadas de `data/store/backtest_universe_2026-05-04_2026-09-09.json`, generado con el código corregido en la ronda 17 (dimensionado exacto con comisión, estados de entrada de la semana pendiente).

**Qué demuestra:** que la cadena completa (paquete → predicción validada → libro → emparejamiento) funciona sobre el universo real, con unos 835 valores elegibles por semana de media; que gestiona una sesión oficial sin datos (viernes 10-07-2026: ninguna de las 1,937 acciones tiene cotización en ninguna de las dos fuentes; no hay anuncio de cierre archivado, sólo la ausencia de datos; las salidas quedaron bloqueadas y se reintentaron la semana siguiente, y la semana 2026-W28 quedó fuera de la estadística); y que emite y archiva la lista de la semana en curso.

**Qué NO demuestra:** rentabilidad. 17 semanas no bastan; la fuente no trae dividendos (mayo-septiembre es la temporada de reparto en Taiwán: los retornos, las etiquetas de Q1 y las comparaciones están **sesgados a la baja**; el control 100→90 con dividendo de 10 rinde 0 % con derechos y −10 % sin ellos); el universo es el censo vigente (supervivencia); los costes son ilustrativos; y el exceso emparejado es **degenerado** cuando quedan pocas semanas emparejables (las entradas fallidas de Q0 y Q1 dejan exposiciones muy distintas de las de A1): en ese caso no hay intervalo de confianza que publicar.

## Resultado en una tabla (17 semanas operadas, 2026-W20 a 2026-W36)

| | Q0 momentum | Q1 tabular | A1 azar | Universo elegible (bruto) |
|---|---|---|---|---|
| Media semanal bruta de las selecciones | −0,64 % | −0,65 % | +2,35 % | +1,23 % |
| Media semanal neta de la cartera (apertura→cierre) | −0,87 % | −1,04 % | +0,35 % | — |
| Semanas con neto > 0 (de las medibles) | 5/16 | 6/16 | 9/16 | — |
| Entradas fallidas (lote más caro que el nocional del puesto) | 9 de 80 | 16 de 80 | 4 de 80 | — |
| Coste medio sobre importe comprado + vendido heredado | 0,73 % | 0,74 % | 0,75 % | — |
| Patrimonio final (inicial 5.000.000 TWD) | 3.969.855 (−20,6 %) | 3.962.879 (−20,7 %) | 4.786.273 (−4,3 %) | — |
| Exceso neto emparejado frente a A1 | +0,80 % con 7 semanas emparejables: **no estimable** | −0,34 % con 5 semanas emparejables: **no estimable** | — | — |

Lectura correcta: en un mercado que subió (+1,23 % semanal el universo elegible, bruto), las dos reglas de precios lo hicieron peor que el azar, y el azar peor que el mercado. La diferencia media neta A1−Q1 (+1,39 % por semana) es mayor que el coste medio (0,74 % del importe invertido); con 17 semanas, sin dividendos y sin intervalo, la diferencia no puede atribuirse a la señal. Lo que sí es un hecho operativo:

1. **El dimensionado proporcional (efectivo disponible / 5 por puesto, ≈ 0,8-1 M TWD) no puede comprar un lote de 1.000 acciones de los valores más caros.** Q1 elige con frecuencia 台積電 (2330, ≈ 2.400 TWD), 鴻海, 緯穎 o 欣興: 16 entradas fallidas de 80. Hay que decidir: subir el capital, admitir lotes sueltos (零股; escenario del informe 15b) o filtrar el universo por precio. Es una decisión de protocolo y cambia el universo elegible.
2. **La regla de emparejamiento (misma exposición ±0.10) deja fuera a la mayoría de las semanas** cuando un pronosticador falla entradas y el otro no. O se corrige el dimensionado (punto 1) o el emparejamiento debe definirse de otro modo.
3. Los costes ilustrativos (≈ 0,75 % semanal sobre lo invertido) son del orden de las diferencias semanales entre pronosticadores.

## Lista de la semana en curso (corte 2026-09-06 18:00 Taipei; semana 2026-W37)

Emitida y archivada con hora real **después** de la entrada simulada del lunes siguiente al corte (`forecast/universe_2026-05-04_2026-09-09/<pronosticador>/2026-W37` en `data/raw`): es una reconstrucción, no una predicción prospectiva. La primera lista prospectiva será la del corte del domingo 13-09, emitida antes de la apertura del lunes 14. Entrada simulada en la primera apertura tras el plazo; salida prevista en el último cierre de la semana (pendiente).

| Pronosticador | Selección (símbolo, nombre) | Estado de la entrada simulada |
|---|---|---|
| Q0 momentum 20 sesiones | 6538 倉和 · 2221 大甲 · 3406 玉晶光 · 6933 AMAX-KY · 3234 光環 | 4 de 5 ejecutadas; sin lote posible: 3406 |
| Q1 tabular | 6669 緯穎 · 2330 台積電 · 3037 欣興 · 2317 鴻海 · 2412 中華電 | 2 de 5 ejecutadas; sin lote posible: 6669, 2330, 3037 |
| A1 azar (control) | 1809 中釉 · 2316 楠梓電 · 2880 華南金 · 3293 鈊象 · 3088 艾訊 | 5 de 5 ejecutadas |

Estas listas son la salida del laboratorio, no una recomendación: los dos pronosticadores han quedado por debajo del azar en las 17 semanas anteriores.

## Límites específicos de esta corrida

- Sin dividendos: la fuente oficial por fecha no los trae; libro, etiquetas de Q1 y comparaciones operan sin derechos (FinMind, que sí los trae, limita a ~300 peticiones por hora en el nivel gratuito).
- Q1 entrenado con un mínimo de 40 semanas de etiqueta (no 52): el historial descargado empieza en julio de 2024; la segunda fase de descarga (2021-2024) lo ampliará.
- 8,787 barras sin precio de sesión regular excluidas; sesiones oficiales sin datos en ambas fuentes según `market_warnings` del JSON (cierres por tifón de 2024 y el 10-07-2026, sin anuncio archivado).
- Procedencia de los paquetes: cada documento de barras declara la fuente (`twse`/`tpex`), el extractor y, por fuente, el manifiesto de capturas de cada sesión de su ventana; una serie con sesiones sin captura enumerada no se admite (ronda 17). La readmisión verificada de series multi-captura queda pendiente (extractor por escribir).
- Todo lo demás: informe 11 §4-5 (costes, dimensionado, tolerancia de exposición, liquidez, tablero de innovación, disponibilidad de barras por política de 24 h, calendario capturado en 2026).

---

*A continuación, el informe generado automáticamente por `scripts/run_backtest.py` (tablas y selecciones semana a semana).*

## Informe generado: backtest universe_2026-05-04_2026-09-09

Periodo 2026-05-04 → 2026-09-09 · universo 1937 valores (official_daily_quotes:2024-07-01..2026-09-09) · 17 semanas operadas, 0 sin sesiones, 1 pendientes de desenlace.

Costes ilustrativos (no contratados); universo del censo vigente; disponibilidad de barras por política de 24 h. Nada de esto es una estimación de rendimiento futuro.

| Pronosticador | Media semanal neta apertura→cierre | Media bruta de las selecciones | Costes/semana sobre invertido | Semanas > 0 (de las medibles) | Patrimonio final | Exceso neto vs A1 (IC 95 %) |
|---|---|---|---|---|---|---|
| Q0 (`rule:momentum_20_sessions_v1`) | -0.87 % | -0.64 % | +0.73 % | 5/16 | 3,969,855 TWD | +0.80 % (incertidumbre no estimable: remuestreo degenerado, n=7) |
| Q1 (`q1:tabular_ridge_lgbm_rank_v2`) | -1.04 % | -0.65 % | +0.74 % | 6/16 | 3,962,879 TWD | -0.34 % (incertidumbre no estimable: remuestreo degenerado, n=5) |
| A1 (`rule:random_eligible_v1`) | +0.35 % | +2.35 % | +0.75 % | 9/16 | 4,786,273 TWD | — |

Referencia equiponderada del universo elegible (bruta, apertura→cierre): +1.23 % semanal.

## Límites

- Universo del censo vigente (sesgo de supervivencia); costes ilustrativos; disponibilidad de barras por política de 24 h, no verificada.
- Derechos (dividendos) según FinMind: la fecha y hora de anuncio acreditan el anuncio, no las revisiones posteriores de importes o fechas; no hay versiones históricas archivadas. Las etiquetas y la contabilidad que dependen de derechos son inferencia conservadora.
- Derechos ambiguos o inválidos detectados en la carga: 0 (etiquetas e intervalos de sus tenedores invalidados); avisos de carga en total: 2. Ejemplos: sin derechos: la fuente oficial por fecha no trae dividendos; libro y etiquetas operan sin ellos; sesiones oficiales sin datos (cierres sobrevenidos u otros): 12 (p. ej. TWSE:2024-07-24, TPEX:2024-07-24, TWSE:2024-07-2
- Un bootstrap con observaciones fijas o degenerado se declara como tal en la tabla; nunca como un IC ordinario.

## Selecciones semana a semana

| Semana | Q0 | Q1 | A1 |
|---|---|---|---|
| 2026-W20 | 3581 博磊 -12.5 %, 6861 睿生光電 +18.4 %, 2454 聯發科 (sin ejecutar: notional_below_one_lot), 4764 雙鍵 -5.0 %, 1595 川寶 -8.7 % → neto -2.70 % | 2412 中華電 +1.1 %, 3045 台灣大 +4.1 %, 2886 兆豐金 -2.0 %, 5876 上海商銀 +2.6 %, 2801 彰銀 -3.8 % → neto -0.38 % | 2104 國際中橡 -5.6 %, 1795 美時 -18.6 %, 2406 國碩 -6.5 %, 8039 台虹 +8.3 %, 5457 宣德 -9.3 % → neto -6.95 % |
| 2026-W21 | 6861 睿生光電 +4.3 %, 6658 聯策 -1.5 %, 3430 奇鈦科 +5.5 %, 3581 博磊 +18.7 %, 5464 霖宏 +32.0 % → neto +10.30 % | 2330 台積電 (sin ejecutar: notional_below_one_lot), 2412 中華電 -0.7 %, 2886 兆豐金 +0.3 %, 2382 廣達 +3.6 %, 2891 中信金 +4.7 % → neto +0.90 % | 2340 台亞 +11.4 %, 4721 美琪瑪 +2.1 %, 1307 三芳 -0.9 %, 3041 揚智 +19.1 %, 6451 訊芯-KY -7.9 % → neto +4.47 % |
| 2026-W22 | 6173 信昌電 +12.1 %, 2492 華新科 +28.8 %, 5464 霖宏 +16.1 %, 3090 日電貿 -0.2 %, 2327 國巨* +8.7 % → neto +10.63 % | 2330 台積電 (sin ejecutar: notional_below_one_lot), 1591 駿吉-KY +0.5 %, 2881 富邦金 +15.3 %, 2317 鴻海 +13.3 %, 3045 台灣大 -0.4 % → neto +4.36 % | 6640 均華 (sin ejecutar: notional_below_one_lot), 1210 大成 +0.4 %, 2801 彰銀 -0.5 %, 6505 台塑化 +0.2 %, 8936 國統 +4.2 % → neto +0.22 % |
| 2026-W23 | 3026 禾伸堂 -6.7 %, 2492 華新科 +2.0 %, 6173 信昌電 -5.7 %, 8042 金山電 -11.3 %, 5464 霖宏 -23.2 % → neto -8.63 % | 2330 台積電 (sin ejecutar: notional_below_one_lot), 2412 中華電 +2.9 %, 3045 台灣大 +3.1 %, 2897 王道銀行 +3.8 %, 1210 大成 +3.8 % → neto +2.01 % | 6672 騰輝電子-KY -1.8 %, 5904 寶雅* +1.1 %, 4551 智伸科 -10.4 %, 6776 展碁國際 +3.9 %, 3479 安勤 -5.1 % → neto -3.17 % |
| 2026-W24 | 2492 華新科 +9.2 %, 6207 雷科 -5.0 %, 6449 鈺邦 +26.0 %, 5321 美而快 -12.2 %, 6116 彩晶 -6.3 % → neto +0.75 % | 2330 台積電 (sin ejecutar: notional_below_one_lot), 4989 榮科 -2.7 %, 2308 台達電 (sin ejecutar: notional_below_one_lot), 3037 欣興 +7.4 %, 6531 愛普* +2.5 % → neto +0.64 % | 3707 漢磊 +11.9 %, 8234 新漢 +1.6 %, 2460 建通 +8.6 %, 2383 台光電 (sin ejecutar: notional_below_one_lot), 3016 嘉晶 +17.3 % → neto +6.82 % |
| 2026-W25 | 3026 禾伸堂 +7.4 %, 2478 大毅 +29.6 %, 2492 華新科 +26.1 %, 3147 大綜 -3.3 %, 8454 富邦媒 +3.3 % → neto +10.50 % | 2330 台積電 (sin ejecutar: notional_below_one_lot), 6669 緯穎 (sin ejecutar: notional_below_one_lot), 2603 長榮 -16.1 %, 2317 鴻海 -0.9 %, 2449 京元電子 +5.7 % → neto -2.34 % | 3260 威剛 +2.1 %, 6462 神盾 +1.8 %, 6651 全宇昕 +13.9 %, 3588 通嘉 +4.0 %, 2455 全新 +12.1 % → neto +5.14 % |
| 2026-W26 | 2243 宏旭-KY +6.0 %, 6654 天正國際 -14.4 %, 2061 風青 +12.4 %, 2492 華新科 -12.3 %, 3026 禾伸堂 -18.1 % → neto -3.53 % | 2412 中華電 -0.7 %, 2330 台積電 (sin ejecutar: notional_below_one_lot), 3045 台灣大 -0.4 %, 1210 大成 +0.9 %, 5871 中租-KY -2.2 % → neto -1.06 % | 1305 華夏 -2.6 %, 4542 科嶠 -9.3 %, 8076 伍豐 -4.9 %, 6834 天二科技 +8.5 %, 3591 艾笛森 +9.3 % → neto -0.22 % |
| 2026-W27 | 2483 百容 +20.5 %, 2243 宏旭-KY +31.5 %, 1714 和桐 +25.0 %, 5328 華容 +15.7 %, 2061 風青 +23.3 % → neto +21.82 % | 2330 台積電 (sin ejecutar: notional_below_one_lot), 2882 國泰金 -10.9 %, 2881 富邦金 -8.3 %, 2412 中華電 -2.1 %, 6669 緯穎 (sin ejecutar: notional_below_one_lot) → neto -4.27 % | 5292 華懋 +8.1 %, 2543 皇昌 +2.8 %, 3231 緯創 +3.2 %, 4585 達明 +15.0 %, 2607 榮運 -4.9 % → neto +3.53 % |
| 2026-W28 | 2483 百容 (salida bloqueada), 2243 宏旭-KY (salida bloqueada), 5328 華容 (salida bloqueada), 4556 旭然 (salida bloqueada), 2466 冠西電 (salida bloqueada) → sin intervalo medible (stale_price) | 2881 富邦金 (salida bloqueada), 2330 台積電 (sin ejecutar: notional_below_one_lot), 2412 中華電 (salida bloqueada), 2344 華邦電 (salida bloqueada), 5386 青雲 (salida bloqueada) → sin intervalo medible (stale_price) | 4147 中裕 (salida bloqueada), 8182 加高 (salida bloqueada), 8271 宇瞻 (salida bloqueada), 8105 凌巨 (salida bloqueada), 4967 十銓 (salida bloqueada) → sin intervalo medible (stale_price) |
| 2026-W29 | (abstained: no_eligible_securities) → neto del libro -6.29 % (posiciones heredadas) | (abstained: no_eligible_securities) → neto del libro -2.10 % (posiciones heredadas) | (abstained: no_eligible_securities) → neto del libro -11.40 % (posiciones heredadas) |
| 2026-W30 | 2466 冠西電 -22.1 %, 2434 統懋 -6.6 %, 3055 蔚華科 -17.1 %, 6226 光鼎 -7.4 %, 4707 磐亞 -10.9 % → neto -12.91 % | 3624 光頡 -11.2 %, 6223 旺矽 (sin ejecutar: notional_below_one_lot), 2481 強茂 -6.0 %, 3481 群創 -6.8 %, 5425 台半 -7.6 % → neto -6.65 % | 4585 達明 -1.8 %, 2458 義隆 +1.2 %, 6579 研揚 +20.7 %, 6205 詮欣 -0.2 %, 2609 陽明 +3.2 % → neto +3.31 % |
| 2026-W31 | 4556 旭然 -40.0 %, 2434 統懋 -23.7 %, 8039 台虹 -26.2 %, 2466 冠西電 -4.1 %, 6505 台塑化 -13.3 % → neto -20.42 % | 2887 台新新光金 +4.2 %, 2330 台積電 (sin ejecutar: notional_below_one_lot), 6174 安碁 -9.8 %, 2412 中華電 +0.0 %, 6175 立敦 -13.2 % → neto -4.18 % | 1717 長興 -2.4 %, 2415 錩新 -5.5 %, 1714 和桐 -11.8 %, 4540 全球傳動 -10.2 %, 3060 銘異 -6.1 % → neto -7.83 % |
| 2026-W32 | 6598 ABC-KY -4.3 %, 6243 迅杰 -4.2 %, 3685 元創精密 +9.5 %, 6505 台塑化 -0.6 %, 2357 華碩 +3.4 % → neto -0.04 % | 2412 中華電 -0.7 %, 1216 統一 +2.9 %, 3045 台灣大 -1.3 %, 5871 中租-KY -1.8 %, 2845 遠東銀 -1.5 % → neto -1.19 % | 6199 天品 -3.9 %, 6223 旺矽 (sin ejecutar: notional_below_one_lot), 5880 合庫金 -3.0 %, 4916 事欣科 +14.9 %, 8050 廣積 +28.3 % → neto +6.35 % |
| 2026-W33 | 8039 台虹 +9.0 %, 6863 永道-KY -17.6 %, 3653 健策 (sin ejecutar: notional_below_one_lot), 2059 川湖 (sin ejecutar: notional_below_one_lot), 6533 晶心科 -3.0 % → neto -2.50 % | 2412 中華電 -1.8 %, 5880 合庫金 -8.5 %, 2845 遠東銀 -0.4 %, 2886 兆豐金 -8.8 %, 2330 台積電 (sin ejecutar: notional_below_one_lot) → neto -4.28 % | 8096 擎亞 -13.7 %, 1232 大統益 -4.4 %, 1563 巧新 +8.0 %, 9802 鈺齊-KY +1.3 %, 6937 天虹 +12.7 % → neto -0.05 % |
| 2026-W34 | 3081 聯亞 (sin ejecutar: notional_below_one_lot), 3605 宏致 -17.5 %, 7711 永擎 -3.0 %, 2059 川湖 (sin ejecutar: notional_below_one_lot), 3653 健策 (sin ejecutar: notional_below_one_lot) → neto -3.75 % | 2412 中華電 +1.1 %, 2618 長榮航 +6.4 %, 1216 統一 +2.8 %, 2884 玉山金 +1.9 %, 2892 第一金 +1.7 % → neto +1.90 % | 2363 矽統 -4.9 %, 2207 和泰車 +0.8 %, 9914 美利達 +0.3 %, 1563 巧新 -2.2 %, 2465 麗臺 -10.4 % → neto -3.82 % |
| 2026-W35 | 3490 單井 -12.4 %, 2059 川湖 (sin ejecutar: notional_below_one_lot), 3498 陽程 -0.8 %, 3441 聯一光電 +14.5 %, 3081 聯亞 (sin ejecutar: notional_below_one_lot) → neto -0.20 % | 2412 中華電 -0.7 %, 2330 台積電 (sin ejecutar: notional_below_one_lot), 3231 緯創 +1.1 %, 2633 台灣高鐵 +0.6 %, 2002 中鋼 -2.3 % → neto -0.84 % | 2360 致茂 (sin ejecutar: notional_below_one_lot), 5475 德宏 +16.9 %, 5284 jpp-KY -3.3 %, 2340 台亞 +10.7 %, 4764 雙鍵 +15.0 % → neto +7.29 % |
| 2026-W36 | 2491 吉祥全 -17.3 %, 6213 聯茂 -8.2 %, 3498 陽程 +1.6 %, 3081 聯亞 (sin ejecutar: notional_below_one_lot), 8039 台虹 -13.3 % → neto -6.92 % | 2330 台積電 (sin ejecutar: notional_below_one_lot), 2603 長榮 -0.4 %, 2412 中華電 +1.1 %, 2891 中信金 +7.7 %, 2633 台灣高鐵 -0.6 % → neto +0.91 % | 6199 天品 +3.0 %, 6829 千附精密 +3.4 %, 6588 東典光電 -1.4 %, 3596 智易 -0.9 %, 5607 遠雄港 +10.1 % → neto +1.97 % |
| 2026-W37 | 6538 倉和, 2221 大甲, 3406 玉晶光 (sin ejecutar: notional_below_one_lot), 6933 AMAX-KY, 3234 光環 → pendiente | 6669 緯穎 (sin ejecutar: notional_below_one_lot), 2330 台積電 (sin ejecutar: notional_below_one_lot), 3037 欣興 (sin ejecutar: notional_below_one_lot), 2317 鴻海, 2412 中華電 → pendiente | 1809 中釉, 2316 楠梓電, 2880 華南金, 3293 鈊象, 3088 艾訊 → pendiente |
