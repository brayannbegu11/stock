# Backtest del universo completo con el capital del usuario: 75.000 TWD en lotes sueltos (mayo-septiembre 2026)

**Qué es:** la misma corrida del informe 15 (mismo universo de 1.937 acciones, mismas 17 semanas operadas, misma fuente oficial por fecha, **sin dividendos**), con el dimensionado que corresponde al capital real del usuario (2-3 mil USD): **75.000 TWD** iniciales, cinco puestos de 15.000 TWD nominales con dimensionado proportional (efectivo disponible / 5), **lotes sueltos** (`lot_size=1`, 零股), comisión 0,1425 % por lado con **mínimo de 20 TWD por orden**, impuesto de venta 0,3 % y deslizamiento de 20 pb por lado (el mercado de lotes sueltos es menos líquido). Etiqueta: `user_75kTWD_oddlots_2026`; cifras tomadas de `data/store/backtest_user_75kTWD_oddlots_2026.json`, generado con el código corregido en la ronda 17 (la cantidad comprada respeta el nocional del puesto incluida la comisión mínima). Aproximación declarada: los precios son los de la sesión regular, no los del mercado de lotes sueltos (cambio de plan P7: propuesto en el prompt de la ronda 17, evaluado por Astra en su ronda 17, recogido como adenda en el informe 22 §2 y en el informe 23 §2).

**Qué cambia respecto al estándar:** el universo elegible es **mayor**: la regla de liquidez del protocolo exige que la mediana del importe negociado en 20 sesiones sea ≥ 20 × el nocional del puesto, es decir 300.000 TWD frente a 20.000.000 TWD en el estándar; entran valores pequeños que en el informe 15 quedaban fuera (1,697 elegibles por semana de media frente a 835), por lo que **las listas de Q0, Q1 y A1 no coinciden con las del informe 15** (A1 se sortea sobre ese universo distinto) y el universo bruto de referencia rinde +0,84 % semanal frente a +1,23 %. Con lotes sueltos casi todas las entradas caben (Q0 3 de 80 (estándar 9); Q1 0 de 80 (estándar 16); A1 0 de 80 (estándar 4)); a cambio, la comisión mínima pesa más sobre importes pequeños (coste medio sobre compras brutas más ventas brutas heredadas: Q0 0,95 % (estándar 0,73 %); Q1 0,93 % (estándar 0,74 %); A1 0,94 % (estándar 0,75 %)). Medias semanales netas frente al escenario estándar: Q0: −1,85 % frente a −0,87 %; Q1: −0,94 % frente a −1,04 %; A1: −1,08 % frente a +0,35 %.

**Qué NO demuestra:** lo mismo que el informe 15: 17 semanas no bastan, no hay dividendos, el universo es el censo vigente y el exceso emparejado se calcula con las semanas emparejables que haya. Las cifras siguientes las reproduce `scripts/run_backtest.py` con los parámetros del README.

## Resultado en una tabla (17 semanas operadas)

| | Q0 momentum | Q1 tabular | A1 azar | Universo elegible (bruto) |
|---|---|---|---|---|
| Media semanal bruta de las selecciones | −0,08 % | +0,30 % | +0,47 % | +0,84 % |
| Media semanal neta de la cartera (apertura→cierre) | −1,85 % | −0,94 % | −1,08 % | — |
| Semanas con neto > 0 (de las medibles) | 5/16 | 6/16 | 5/16 | — |
| Entradas fallidas (lote más caro que el nocional del puesto) | 3 de 80 | 0 de 80 | 0 de 80 | — |
| Coste medio sobre importe comprado + vendido heredado | 0,95 % | 0,93 % | 0,94 % | — |
| Patrimonio final (inicial 75.000 TWD) | 49.623 (−33,8 %) | 60.057 (−19,9 %) | 56.938 (−24,1 %) | — |
| Exceso neto emparejado frente a A1 | −1,05 % con 12 semanas emparejables, IC 95 % [−6,40 %, +0,16 %] (variabilidad limitada: 4 semanas fijas) | −0,23 % con 15 semanas emparejables, IC 95 % [−1,44 %, +0,24 %] | — | — |

Lectura: el orden entre pronosticadores y el signo de las medias se leen en la tabla; ninguna diferencia es estadísticamente distinguible de cero con 17 semanas. Con 15.000 TWD por puesto, la comisión mínima de 20 TWD equivale al 0,13 % del nocional por lado, por encima del 0,1425 % nominal siempre que el importe de la orden baje de 14.035 TWD.

## Lista de la semana en curso (2026-W37, corte 2026-09-06 18:00 Taipei)

Lista **distinta** de la del informe 15: el universo elegible con 15.000 TWD por puesto incluye valores menos líquidos (regla de liquidez escalada con el nocional), y Q0, Q1 y A1 se calculan sobre él. Emitida y archivada (`forecast/user_75kTWD_oddlots_2026/<pronosticador>/2026-W37` en `data/raw`) **después** del plazo o sin identidad verificable (no_forecast_identity:Q0,Q1,A1): es una reconstrucción con datos ya conocidos, no una predicción prospectiva.

| Pronosticador | Selección (símbolo, nombre) | Estado de la entrada simulada con lotes sueltos |
|---|---|---|
| Q0 momentum 20 sesiones | 6225 天瀚 · 6538 倉和 · 2221 大甲 · 3406 玉晶光 · 6933 AMAX-KY | 5 de 5 ejecutadas |
| Q1 tabular | 6669 緯穎 · 2330 台積電 · 4747 強生* · 3037 欣興 · 2317 鴻海 | 5 de 5 ejecutadas |
| A1 azar (control) | 5206 坤悅 · 1528 恩德 · 1799 易威 · 2718 全心投控 · 3224 三顧 | 5 de 5 ejecutadas |

## Límites específicos de esta corrida

- Precios de sesión regular como aproximación a los de lotes sueltos (que se cruzan a las 13:30 y en sesión intradía desde 2020 con su propio libro de órdenes): los deslizamientos reales pueden ser mayores; el 20 pb es una hipótesis declarada, no una medición.
- Comisión mínima de 20 TWD como hipótesis habitual del mercado; la del intermediario del usuario no se ha confirmado.
- Sin dividendos, censo vigente, 17 semanas: mismas advertencias que el informe 15.
- El nocional por puesto es proporcional al efectivo disponible (efectivo / 5), por lo que tras semanas negativas los importes bajan y la comisión mínima pesa más.
- Universo elegible más amplio y menos líquido que el del informe 15 (misma regla, umbral 66 veces menor): los resultados de ambos informes no son comparables valor a valor, sólo como dos escenarios del mismo protocolo.

---

*A continuación, el informe generado automáticamente por `scripts/run_backtest.py` (tablas y selecciones semana a semana).*

## Informe generado: backtest user_75kTWD_oddlots_2026
Periodo 2026-05-04 → 2026-09-09 · universo 1937 valores (official_daily_quotes:2024-07-01..2026-09-09) · 17 semanas operadas, 0 sin sesiones, 1 pendientes de desenlace.

Costes ilustrativos (no contratados); universo del censo vigente; disponibilidad de barras por política de 24 h. Nada de esto es una estimación de rendimiento futuro.

| Pronosticador | Media semanal neta apertura→cierre | Media bruta de las selecciones | Costes/semana sobre compras brutas + ventas brutas heredadas | Semanas > 0 (de las medibles) | Patrimonio final | Exceso neto vs A1 (IC 95 %) |
|---|---|---|---|---|---|---|
| Q0 (`rule:momentum_20_sessions_v1`) | -1.85 % | -0.08 % | +0.95 % | 5/16 | 49,623 TWD | -1.05 % [-6.40 %, +0.16 %] n=12 (variabilidad limitada: 4 semanas fijas) |
| Q1 (`q1:tabular_ridge_lgbm_rank_v2`) | -0.94 % | +0.30 % | +0.93 % | 6/16 | 60,057 TWD | -0.23 % [-1.44 %, +0.24 %] n=15 |
| A1 (`rule:random_eligible_v1`) | -1.08 % | +0.47 % | +0.94 % | 5/16 | 56,938 TWD | — |

Referencia equiponderada del universo elegible (bruta, apertura→cierre): +0.84 % semanal.

## Límites

- Universo del censo vigente (sesgo de supervivencia); costes ilustrativos; disponibilidad de barras por política de 24 h, no verificada.
- Derechos (dividendos) según FinMind: la fecha y hora de anuncio acreditan el anuncio, no las revisiones posteriores de importes o fechas; no hay versiones históricas archivadas. Las etiquetas y la contabilidad que dependen de derechos son inferencia conservadora.
- Derechos ambiguos o inválidos detectados en la carga: 0 (etiquetas e intervalos de sus tenedores invalidados); avisos de carga en total: 2. Ejemplos: sin derechos: la fuente oficial por fecha no trae dividendos; libro y etiquetas operan sin ellos; sesiones oficiales sin datos (cierres sobrevenidos u otros): 12 (p. ej. TWSE:2024-07-24, TPEX:2024-07-24, TWSE:2024-07-2
- Un bootstrap con observaciones fijas o degenerado se declara como tal en la tabla; nunca como un IC ordinario.

## Selecciones semana a semana

| Semana | Q0 | Q1 | A1 |
|---|---|---|---|
| 2026-W20 | 3581 博磊 -12.5 %, 6861 睿生光電 +18.4 %, 2454 聯發科 -8.8 %, 4764 雙鍵 -5.0 %, 1595 川寶 -8.7 % → neto -4.18 % | 2412 中華電 +1.1 %, 3045 台灣大 +4.1 %, 9925 新保 -0.5 %, 2886 兆豐金 -2.0 %, 1232 大統益 +0.3 % → neto -0.36 % | 1731 美吾華 -1.4 %, 1563 巧新 +1.7 %, 2367 燿華 +0.2 %, 7705 三商餐飲 -4.6 %, 5388 中磊 -10.1 % → neto -3.78 % |
| 2026-W21 | 8291 尚茂 +46.0 %, 6861 睿生光電 +4.3 %, 6658 聯策 -1.5 %, 3430 奇鈦科 +5.5 %, 3581 博磊 +18.7 % → neto +13.41 % | 2330 台積電 +1.3 %, 2412 中華電 -0.7 %, 2886 兆豐金 +0.3 %, 2382 廣達 +3.6 %, 2891 中信金 +4.7 % → neto +0.84 % | 2064 晉椿 +1.6 %, 4721 美琪瑪 +2.1 %, 1256 鮮活果汁-KY +2.2 %, 3045 台灣大 -2.2 %, 6526 達發 +7.7 % → neto +1.29 % |
| 2026-W22 | 8291 尚茂 +20.0 %, 6173 信昌電 +12.1 %, 2492 華新科 +28.8 %, 5464 霖宏 +16.1 %, 3090 日電貿 -0.2 % → neto +14.18 % | 2330 台積電 +3.5 %, 1591 駿吉-KY +0.5 %, 2881 富邦金 +15.3 %, 2317 鴻海 +13.3 %, 9925 新保 +0.9 % → neto +5.58 % | 6666 羅麗芬-KY +0.1 %, 1109 信大 +0.0 %, 2729 瓦城 -0.6 %, 6541 泰福-KY +0.4 %, 8472 納維康 +12.5 % → neto +1.49 % |
| 2026-W23 | 8291 尚茂 -34.3 %, 3026 禾伸堂 -6.7 %, 2492 華新科 +2.0 %, 6173 信昌電 -5.7 %, 8042 金山電 -11.3 % → neto -11.99 % | 2330 台積電 +0.4 %, 2412 中華電 +2.9 %, 2897 王道銀行 +3.8 %, 1210 大成 +3.8 %, 2820 華票 +2.4 % → neto +1.69 % | 6870 騰雲 +2.7 %, 6126 信音 +15.0 %, 4716 大立 +13.5 %, 6994 富威電力 -3.2 %, 3583 辛耘 +0.1 % → neto +4.60 % |
| 2026-W24 | 2492 華新科 +9.2 %, 6207 雷科 -5.0 %, 6449 鈺邦 +26.0 %, 5321 美而快 -12.2 %, 8291 尚茂 -33.4 % → neto -4.11 % | 2330 台積電 +3.6 %, 4989 榮科 -2.7 %, 2308 台達電 +6.0 %, 3037 欣興 +7.4 %, 6531 愛普* +2.5 % → neto +2.23 % | 4532 瑞智 +3.6 %, 2471 資通 +5.8 %, 2363 矽統 +3.9 %, 3041 揚智 +10.3 %, 3492 長盛 +5.8 % → neto +4.87 % |
| 2026-W25 | 3026 禾伸堂 +7.4 %, 2478 大毅 +29.6 %, 2492 華新科 +26.1 %, 3147 大綜 -3.3 %, 8454 富邦媒 +3.3 % → neto +11.43 % | 2330 台積電 +2.1 %, 6669 緯穎 +2.4 %, 2603 長榮 -16.1 %, 2317 鴻海 -0.9 %, 2449 京元電子 +5.7 % → neto -2.35 % | 6781 AES-KY +0.9 %, 7709 榮田 -10.3 %, 4188 安克 +0.5 %, 2476 鉅祥 -0.8 %, 1301 台塑 +12.9 % → neto -0.34 % |
| 2026-W26 | 2243 宏旭-KY +6.0 %, 6654 天正國際 -14.4 %, 2061 風青 +12.4 %, 2492 華新科 -12.3 %, 3026 禾伸堂 -18.1 % → neto -6.02 % | 2412 中華電 -0.7 %, 2330 台積電 -4.7 %, 3045 台灣大 -0.4 %, 9925 新保 -0.5 %, 1210 大成 +0.9 % → neto -1.93 % | 4952 凌通 -6.7 %, 8272 全景軟體 -1.6 %, 4433 興采 +1.0 %, 5907 大洋-KY -4.6 %, 2723 美食-KY +2.4 % → neto -2.84 % |
| 2026-W27 | 2483 百容 +20.5 %, 2243 宏旭-KY +31.5 %, 1714 和桐 +25.0 %, 5328 華容 +15.7 %, 2061 風青 +23.3 % → neto +21.99 % | 2330 台積電 +4.9 %, 2881 富邦金 -8.3 %, 2882 國泰金 -10.9 %, 2412 中華電 -2.1 %, 6669 緯穎 +21.0 % → neto -0.80 % | 3501 維熹 +2.8 %, 4973 廣穎電通 -5.3 %, 2754 亞洲藏壽司 +0.6 %, 4722 國精化 -3.3 %, 9938 百和 +6.1 % → neto -0.78 % |
| 2026-W28 | 2380 虹光 (salida bloqueada), 2483 百容 (salida bloqueada), 2243 宏旭-KY (salida bloqueada), 5328 華容 (salida bloqueada), 4556 旭然 (salida bloqueada) → sin intervalo medible (stale_price) | 2881 富邦金 (salida bloqueada), 2330 台積電 (salida bloqueada), 2412 中華電 (salida bloqueada), 2344 華邦電 (salida bloqueada), 5386 青雲 (salida bloqueada) → sin intervalo medible (stale_price) | 9906 欣巴巴 (salida bloqueada), 5345 馥鴻 (salida bloqueada), 4909 新復興 (salida bloqueada), 2484 希華 (salida bloqueada), 6791 虎門科技 (salida bloqueada) → sin intervalo medible (stale_price) |
| 2026-W29 | (abstained: no_eligible_securities) → neto del libro -13.01 % (posiciones heredadas) | (abstained: no_eligible_securities) → neto del libro -3.71 % (posiciones heredadas) | (abstained: no_eligible_securities) → neto del libro -9.42 % (posiciones heredadas) |
| 2026-W30 | 2380 虹光 -1.5 %, 2466 冠西電 -22.1 %, 2434 統懋 -6.6 %, 3055 蔚華科 -17.1 %, 6226 光鼎 -7.4 % → neto -11.76 % | 3624 光頡 -11.2 %, 6223 旺矽 +3.0 %, 2481 強茂 -6.0 %, 3481 群創 -6.8 %, 8261 富鼎 -13.5 % → neto -7.88 % | 6419 京晨科 -0.4 %, 2743 山富 +1.2 %, 1536 和大 +2.7 %, 2409 友達 -2.9 %, 1532 勤美 -0.4 % → neto -0.94 % |
| 2026-W31 | 2380 虹光 -0.3 %, 4556 旭然 -40.0 %, 2434 統懋 -23.7 %, 8039 台虹 -26.2 %, 2466 冠西電 -4.1 % → neto -19.51 % | 2887 台新新光金 +4.2 %, 2330 台積電 +4.1 %, 6174 安碁 -9.8 %, 2412 中華電 +0.0 %, 6207 雷科 -12.3 % → neto -3.80 % | 4551 智伸科 -11.4 %, 3168 眾福科 -6.4 %, 6175 立敦 -13.2 %, 6205 詮欣 -9.8 %, 5529 鉅陞 -2.3 % → neto -9.52 % |
| 2026-W32 | 4139 馬光-KY -4.9 %, 6863 永道-KY -1.5 %, 4442 竣邦-KY -28.1 %, 2923 鼎固-KY -22.3 %, 6598 ABC-KY -4.3 % → neto -13.12 % | 2412 中華電 -0.7 %, 1216 統一 +2.9 %, 3045 台灣大 -1.3 %, 5523 豐謙 -0.2 %, 1737 臺鹽 -0.6 % → neto -1.00 % | 4904 遠傳 -1.4 %, 7753 星亞 +1.6 %, 8147 正淩 +14.1 %, 6890 來億-KY +3.6 %, 1229 聯華 +0.9 % → neto +2.69 % |
| 2026-W33 | 8039 台虹 +9.0 %, 4139 馬光-KY -3.0 %, 6863 永道-KY -17.6 %, 3653 健策 +8.6 %, 2059 川湖 (sin ejecutar: notional_below_one_lot) → neto -1.61 % | 2412 中華電 -1.8 %, 5880 合庫金 -8.5 %, 2845 遠東銀 -0.4 %, 5523 豐謙 -0.2 %, 2886 兆豐金 -8.8 % → neto -4.88 % | 1453 大將 +2.7 %, 8054 安國 -1.7 %, 6721 信實 -1.0 %, 2230 泰茂 -6.6 %, 9935 慶豐富 +0.7 % → neto -2.15 % |
| 2026-W34 | 3081 聯亞 +9.4 %, 3605 宏致 -17.5 %, 7711 永擎 -3.0 %, 2059 川湖 (sin ejecutar: notional_below_one_lot), 6225 天瀚 +45.7 % → neto +5.71 % | 2412 中華電 +1.1 %, 1216 統一 +2.8 %, 2892 第一金 +1.7 %, 5523 豐謙 +0.5 %, 2618 長榮航 +6.4 % → neto +1.44 % | 8917 欣泰 +0.9 %, 1752 南光 +0.5 %, 8028 昇陽半導體 -8.1 %, 1442 名軒 +2.7 %, 2430 燦坤 +3.2 % → neto -1.15 % |
| 2026-W35 | 6225 天瀚 -16.3 %, 3490 單井 -12.4 %, 2059 川湖 (sin ejecutar: notional_below_one_lot), 3498 陽程 -0.8 %, 3441 聯一光電 +14.5 % → neto -3.81 % | 2412 中華電 -0.7 %, 2330 台積電 +0.4 %, 2633 台灣高鐵 +0.6 %, 5523 豐謙 +0.0 %, 3231 緯創 +1.1 % → neto -0.73 % | 2109 華豐 -0.3 %, 5220 萬達光電 +0.5 %, 4924 欣厚-KY +7.0 %, 2027 大成鋼 -5.1 %, 4439 冠星-KY +1.4 % → neto -0.33 % |
| 2026-W36 | 6225 天瀚 -4.8 %, 2491 吉祥全 -17.3 %, 6213 聯茂 -8.2 %, 3498 陽程 +1.6 %, 3081 聯亞 -2.2 % → neto -7.13 % | 2330 台積電 +0.6 %, 2603 長榮 -0.4 %, 2891 中信金 +7.7 %, 2412 中華電 +1.1 %, 2633 台灣高鐵 -0.6 % → neto +0.66 % | 8171 天宇 -3.2 %, 5512 力麒 +0.4 %, 6526 達發 +4.8 %, 6243 迅杰 -4.1 %, 3540 曜越 +2.8 % → neto -0.94 % |
| 2026-W37 | 6225 天瀚, 6538 倉和, 2221 大甲, 3406 玉晶光, 6933 AMAX-KY → pendiente | 6669 緯穎, 2330 台積電, 4747 強生*, 3037 欣興, 2317 鴻海 → pendiente | 5206 坤悅, 1528 恩德, 1799 易威, 2718 全心投控, 3224 三顧 → pendiente |
