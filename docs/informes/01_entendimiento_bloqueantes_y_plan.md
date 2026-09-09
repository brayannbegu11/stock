# Informe de entendimiento, bloqueantes y plan de construcción

**Constructor:** Fable 5.1 · **Revisor:** GPT-6 Astra (Codex CLI 0.153.4) · **Fecha:** 9 de septiembre de 2026
**Base:** paquete `Taiwan_IA_Research_v2_2026-09-09` (sha256 de `INVESTIGACION.md` verificado contra `MANIFEST.json`).

Este es el «primer mensaje del constructor» que exige `TRASPASO_FABLE_ASTRA.md`. No contiene resultados financieros. Las cifras de cobertura son recuentos de capturas del 9-09-2026, no un censo validado.

## 1. Alcance entendido

| Dimensión | Entendimiento |
|---|---|
| Cobertura | Todas las acciones ordinarias de TWSE y TPEx en cada fecha, con maestro histórico (altas, retiradas, cambios de mercado). ESB/興櫃 sólo catalogado. ETF, ETN, DR, warrants y fondos fuera de la cartera. |
| Modelos | Motor determinista sin LLM (censo, calendario, paquetes, libro). Modelo tabular compartido (lineal regularizado + LightGBM) como Q1. Híbrido H1 = Q1 + eventos extraídos. Fable/Astra como pronosticadores directos (L1/L2) y como constructor/revisor. |
| Actualización | Tres ritmos: datos (captura incremental fechada), pronósticos (semanal congelado, diario opcional), modelos (mensual, en sombra). Cada predicción es inmutable. |
| Validación | Prospectiva desde el congelamiento del protocolo. Histórico 2021-2025 con partición temporal; resultados de LLM actuales etiquetados como exploratorios con posible contaminación. Métrica principal: exceso neto semanal de H1 sobre Q1 con exposición emparejada. |
| Producto inicial | Análisis y carteras simuladas. Sin órdenes, sin intermediarios, sin credenciales de bróker. |

## 2. Estado del entorno (verificado)

- Codex CLI 0.153.4, autenticado con ChatGPT, modelo `gpt-6-astra`. El primer intento del día devolvió **límite de uso agotado hasta el 12-09**; a las pocas horas el usuario restableció la suscripción y la prueba respondió (4.560 tokens). Riesgo operativo registrado en §4.
- `~/.codex/config.toml` fija `model_reasoning_effort = "low"`; los scripts de revisión fuerzan `high` por invocación.
- Python 3.13 con pandas, pyarrow, duckdb, lightgbm, scikit-learn, jsonschema, exchange_calendars y FinMind instalados. No se importa ninguna librería de ML en el núcleo.
- Existe una variable de entorno `OPENAI_API_KEY` en la cuenta de usuario. El proyecto **no la lee** ni la usará sin autorización explícita y tope de gasto.

## 3. Resultado de la auditoría de fuentes (detalle en `02_auditoria_fuentes_entrega_A.md`)

1. **Las OpenAPI oficiales sirven instantáneas, no historia.** TWSE (143 endpoints) y TPEx (225) devuelven el último estado; no admiten parámetros de fecha. Consecuencia: cada día sin captura se pierde para la rama prospectiva. La historia 2021-2025 debe venir de FinMind (gratuito, precios nominales confirmados), de los endpoints heredados de TWSE/TPEx o de TEJ.
2. **El endpoint oficial de festivos mezcla dos clases de filas** (corregido tras el hallazgo R01-01 de Astra). Junto a los cierres (放假, 補假, 市場無交易) incluye filas informativas de negociación (國曆新年開始交易日 2-ene, 農曆春節前最後交易日 11-feb, 農曆春節後開始交易日 23-feb). Mi primera versión las trató como cierres, produjo 240 sesiones en vez de 243 y atribuyó falsamente la diferencia a `exchange_calendars`. Ahora cada fila se clasifica y una fila no reconocida detiene la carga; XTAI coincide con la lista oficial en 2026 y queda como contraste, no como autoridad.
3. **Existen timestamps verificados de publicación** en los anuncios materiales (`t187ap04_L`, `mopsfin_t187ap04_O`: campos 發言日期/發言時間) y en dividendos de FinMind (`AnnouncementDate`+`AnnouncementTime`). Los ingresos mensuales históricos de FinMind **no** los tienen (`create_time` vacío en 2021; fecha de rastreo desde 2026).
4. **Índice de referencia disponible.** `indicesReport/FRMSA` devuelve `FormosaIndex` y `FormosaTotalReturnIndex`; TPEx `tpex_reward_index` devuelve su versión de rentabilidad total. Sólo instantánea de días recientes: hay que capturar a diario y rellenar historia por otra vía.
5. **Unidades y formatos heterogéneos.** Ingresos mensuales de TWSE/TPEx declarados en miles de TWD; FinMind en TWD. Los órdenes de magnitud observados son coherentes con cada unidad declarada (TSMC diciembre 2020 en FinMind: 117.364.912.000 TWD; 台泥 julio 2026 en TWSE: 13.744.103 miles), pero son emisores y meses distintos: **no constituyen una verificación de equivalencia** (R01-25). La prueba emparejada por emisor, mes, alcance y versión se hará sobre el archivo real. Fechas en ROC compacto, ROC con barras, gregoriano compacto e ISO; horas HHMMSS sin ceros (``3220`` = 00:32:20), cubiertas por `timeutil` y sus pruebas.
6. **Latencia observada.** En la captura vespertina del 9-09 (hora local del usuario) `STOCK_DAY_ALL`, `BWIBBU_ALL`, `MI_INDEX` y `FRMSA` traían fecha 1150908, mientras `tpex_mainboard_quotes` ya traía 1150909. La latencia real de TWSE se medirá con la captura diaria; no se asume «disponible al cierre».
7. **Censo de partida (capturas, no validado):** TWSE 1.094 sociedades cotizadas (`t187ap03_L`), TPEx 890 (`mopsfin_t187ap03_O`), ESB 363; filas de cotización 1.382 (TWSE) y 1.014 (TPEx) porque incluyen ETF/ETN/bonos; FinMind `TaiwanStockInfo` 4.319 filas (incluye ETF, ETN, DR e índices). Retiradas: TWSE 265 filas, FinMind 725 (todos los tipos).

## 4. Bloqueantes

### 4.1 Resolubles inspeccionando APIs y documentación (en curso)

| Bloqueante del protocolo | Estado | Cómo se resuelve |
|---|---|---|
| `verified_benchmark_series` | Parcial | Captura diaria de `FRMSA` y `tpex_reward_index`; historial vía endpoint heredado de TWSE o TEJ; validar continuidad. |
| Calendario efectivo | Resuelto para 2026 (corregido tras R01-01) | Lista oficial capturada y clasificada por tipo de fila; versiones con `CalendarStore` para cierres extraordinarios con fecha de anuncio; añadir 2021-2025 desde el endpoint heredado. |
| Semántica de fechas y unidades | Formatos resueltos; equivalencia de unidades pendiente | `timeutil.parse_date`, `parse_hhmmss`; unidades declaradas en `sources/catalog.py`; prueba emparejada pendiente (R01-25). |
| Latencia de publicación de TWSE | Primera medición hecha; serie pendiente | A las 02:04 Taipei del 10-09 las tablas diarias de TWSE iban una sesión por detrás de TPEx (informe 02 §5.6). Capturas a distintas horas durante dos semanas. |
| Historial de maestro (tableros, cambios de mercado) | Pendiente | Cruzar `company/newlisting`, `suspendListing`, `tpex_cmode` y FinMind `TaiwanStockInfo`/`TaiwanStockDelisting`; la muestra de TEJ conserva todos los casos de §6.3. |
| `date_without_time_policy` | Implementado con restricción (R01-24) | `derive_available_at` sólo para fechas de publicación **verificadas**. Un plazo legal no es evidencia: los ingresos históricos sin timestamp de publicación se clasifican `unknown` y quedan fuera del paquete principal. Ver tensión T1. |

### 4.2 Requieren presupuesto, licencia o decisión del usuario

| Bloqueante | Por qué no se puede adivinar |
|---|---|
| `data_provider_and_license` (TEJ) | Precio y permisos de reutilización/envío a APIs de IA no publicados. Petición de muestra ya acotada (§6, A9). |
| `versioned_news_coverage` | Licencia de noticias en chino tradicional con originales y correcciones. Se saca del camino crítico de A-C (ver A2). |
| `budget_cap_usd` | Sin tope no se puede diseñar la cola de revisión profunda ni los experimentos L1/L2. |
| `notional_twd`, `participation_cap`, `liquidity_eligibility_rule` | Definen elegibilidad; `classify_coverage` deja la elegibilidad en `False` con motivo `liquidity_rule_not_frozen` hasta que se fijen. |
| `contracted_commission_per_side`, `central_slippage_scenario` | El libro usa 0,1425 % ilustrativo y escenarios 5/10/25 pb; el central se congela antes de la reserva. |
| `unsettled_cash_policy`, `delisting_terminal_valuation_policy` | El libro marca `delisted_unresolved` y no reutiliza efectivo; la valoración terminal es una decisión de protocolo. |
| `bootstrap_block_length`, `sequential_review_plan` | `block_bootstrap_mean` exige el parámetro; no hay valor por defecto. |
| Uso de la API de OpenAI con clave propia | Gasto real fuera de la suscripción. Decisión del usuario (§4.3). |

### 4.3 Tensiones detectadas en la especificación

- **T1 · Política conservadora vs. corte dominical** (revisada tras R01-24 y la evaluación de Astra). Para un documento cuya **fecha de publicación está verificada** pero no su hora, la regla lo admite en la apertura de la siguiente sesión. Si esa fecha es viernes, entra después del corte del domingo y pasa a la semana siguiente; si es lunes, entra el martes y llega al corte ordinario. El efecto depende del día de la semana y se medirá como sensibilidad registrada. Un plazo legal (ingresos «hasta el día 10») **no** es una fecha de publicación verificada: esos registros históricos se clasifican `unknown` hasta disponer de evidencia por versión; en prospectivo se capturan los anuncios con hora verificada.
- **T2 · Semanas sin cinco sesiones.** La semana del 16-02-2026 no tiene sesiones; la del 9-02 tiene tres (9, 10 y 11 de febrero). El protocolo dice `five_sessions_assumed: false` pero no define qué ocurre con cero sesiones. Propuesta a congelar: semana sin sesiones → corrida `invalid` con motivo `no_sessions`, sin abrir ni cerrar posiciones, **manteniendo el procesamiento de dividendos, pagos y demás eventos del libro**; semana con una, dos o tres sesiones → válida, etiqueta desde la primera apertura hasta el último cierre reales; el tratamiento estadístico de las semanas inválidas se declara (se cuentan, no se ocultan).
- **T3 · Cuota de la suscripción.** Un límite semanal agotado el día del pronóstico produce un fallo OPS-02 (predicción tardía). Opciones: reservar cuota, adelantar la corrida L2 al inicio de ventana, o usar API con tope. No se decide aquí.
- **T4 · Fine-tuning.** Confirmado en la ficha de Astra: no admitido. Ningún módulo asumirá adaptación de pesos de modelos frontera.

## 5. Cambios propuestos al plan, con fundamento

| Id | Cambio | Fundamento | Coste |
|---|---|---|---|
| A1 | **Añadir** captura diaria de ~40 endpoints oficiales desde hoy, con `ingested_at` real y sha256 (`scripts/capture_daily.py`). | Las OpenAPI son instantáneas: la historia prospectiva no se puede reconstruir después. | <20 MB/día; una tarea programada. |
| A2 | **Reordenar**: los anuncios materiales oficiales (con campo de hora) son la primera clase documental que se intentará acreditar como `verified_original`; la licencia de noticias sale del camino crítico de las entregas A-C y vuelve en la E. La clase `verified_original` **no se concede por existir un campo de hora**: exige captura con hash, `source_sha256` y evidencia de versión. | Fuente primaria y gratuita con timestamp declarado por el emisor; la cobertura documental de noticias queda declarada como pendiente, no descartada. | Ninguno. |
| A3 | **Retirado** (rechazado por Astra, R01-01). La lista oficial sigue siendo la autoridad, pero interpretada por clasificación de filas; `exchange_calendars` coincide en 2026 y queda como contraste. | Las «tres discrepancias» eran días de negociación mal leídos por mí. | Ninguno. |
| A4 | **Añadir** la serie Formosa TR y TPEx TR a la captura diaria. `verified_benchmark_series` **sigue bloqueado** hasta probar continuidad histórica, revisiones y equivalencia apertura-cierre (condición de Astra). | Los endpoints existen y devuelven la versión de rentabilidad total; eso resuelve el descubrimiento, no la validación. | Ninguno. |
| A5 | **Añadir** contrato de unidades por endpoint y una prueba de equivalencia emparejada (mismo emisor, mes, alcance y versión) sobre el archivo real. | Unidades declaradas distintas (miles vs. TWD); la equivalencia aún no está verificada (R01-25). | Pequeño. |
| A6 | **Añadir** esquema estructurado de hallazgos para el revisor (`review/schemas/hallazgos.schema.json`), esfuerzo `high` y comprobación de integridad del árbol durante la ronda. | Invariante del proyecto: un hallazgo sin archivo, línea y contraejemplo ejecutable es una hipótesis, no una evidencia; la distinción `reproducido`/`hipotesis` se conserva en cada ronda. | Ninguno. |
| A7 | **Aplazar** LightGBM, TimesFM-3, Chronos-2 y LoRA hasta que la entrega B supere sus pruebas con datos reales; el núcleo no importa ML. | Ya lo pide la investigación; se hace verificable. | Ninguno. |
| A8 | **Añadir** al protocolo la regla de semanas con 0/1/2 sesiones (T2) antes del congelamiento. | Caso real de 2026. | Ninguno. |
| A9 | **Retirado** (rechazado por Astra). La petición a TEJ conserva la muestra completa de INVESTIGACION §6.3 (retirada, cambio de mercado, revisión de ingresos, dividendo, división, suspensión, cierre extraordinario, noticia corregida); sólo se **prioriza** el orden: primero timestamps de publicación de ingresos históricos, precios terminales de retiradas y maestro con tableros. | No está demostrado que las fuentes gratuitas resuelvan el resto. | Decisión de gasto. |
| A10 | **Añadir** sello temporal independiente (OpenTimestamps o TSA RFC 3161) para cada predicción y captura prospectiva. Implementado el modelo de recibo verificable (`Receipt`, `verify_receipt`); **el verificador criptográfico real es la condición pendiente** y hasta entonces ningún registro está sellado. | PIT-12: un hash sin sello no prueba fecha; guardar el nombre de una autoridad tampoco (R01-20). | Ninguno; requiere aprobar el servicio. |

No se quita nada de la pregunta científica. No se añade ninguna afirmación de rentabilidad.

## 6. Árbol de módulos

```
taiwan-ia-lab/
  docs/spec/v2/          especificación recibida (inmutable; sha256 en MANIFEST.json)
  docs/informes/         00 perfil Astra · 01 este informe · 02 auditoría A · 03+ rondas de revisión
  data/reference/        capturas oficiales pequeñas versionadas en git (calendario 2026)
  data/raw/              archivo original (manifest.jsonl con sha256 + ingested_at); fuera de git
  data/audit/            inventario de fuentes
  src/twlab/
    timeutil.py          fechas ROC, horas HHMMSS, política de disponibilidad
    calendar.py          calendario oficial versionado; semanas con sesiones reales
    master.py            maestro SCD2, resolución símbolo→identidad, cobertura
    store.py             archivo sólo anexado, hashes, recibos de sello temporal
    packet.py            paquetes por corte, modos histórico/prospectivo, aislamiento del predictor
    schemas.py           validación de PREDICCION.schema.json + TXT-05
    ledger.py            libro determinista (lotes, costes, impuestos, acciones corporativas)
    simulation.py        cesta semanal de cinco puestos con efectivo
    evaluation.py        exceso emparejado, bootstrap por bloques
    sources/catalog.py   registro de endpoints con unidades, formatos y campo de sesión
    audit/               (siguiente) inventario reproducible
    features/ models/ extraction/   posteriores; fuera del núcleo
  scripts/capture_daily.py          captura diaria a data/raw
  review/                brief, prompts, esquema de hallazgos, salidas archivadas de Astra
  tests/                 72 pruebas de aceptación (PIT, UNI, TXT, SIM, STA)
```

## 7. Primera entrega verificable (existe hoy)

`python -m pytest -q -p no:cacheprovider` ejecuta 187 pruebas que cubren PIT-01 a PIT-12, UNI-01/02/03/05/07, TXT-05/07, SIM-01/02/03/05/06/07/08/09/10/11/12, STA-01/04, la aritmética de fricción de 0,585 % y los contraejemplos reproducibles de las rondas 1 a 6 de Astra (`docs/informes/03_…` a `08_respuesta_ronda6_astra.md`). Todo con datos sintéticos explícitos o con la captura oficial del calendario. Ninguna prueba usa red. La primera corrida real de `scripts/capture_daily.py` (37 endpoints, 0 fallos) está registrada en `data/audit/manifest_2026-09-09.jsonl`.

Lo que **no** existe todavía: adaptadores de ingestión completos, maestro poblado con datos reales, doce cortes históricos auditados, verificador criptográfico de recibos, módulo de informe estadístico (STA-02/03/05/06/07), modelo numérico, extracción de eventos, interfaz.

## 8. Siguientes pasos en orden

1. ~~Ronda 1 de revisión adversarial de Astra~~ — hecha: veredicto rechazado, 25 hallazgos, corregidos con prueba (informe 03). ~~Ronda 2~~ — hecha: 16 correcciones confirmadas, 21 hallazgos nuevos o parciales (cuatro regresiones mías), corregidos con prueba (informe 04).
2. ~~Rondas 3 a 6~~ — hechas: 17 + 14 + 12 + 10 hallazgos, corregidos con prueba; lotes con propietario, sello sobre la predicción canónica + paquete recalculado sólo desde el archivo, registro fijo (sólo lectura, vacío) de verificadores de producción, corte semanal estricto (informes 05-08). Ronda 7 preparada: `.eviewun_astra.ps1 -Ronda ronda7_verificacion -Effort high`.
3. Activar la captura diaria (decisión del usuario: tarea programada) y medir latencias dos semanas.
4. Poblar el maestro con TWSE/TPEx/FinMind y superar UNI-01..07 con datos reales; documentar exclusiones; prueba de equivalencia de unidades emparejada.
5. Congelar los valores pendientes del protocolo con el usuario (§4.2, más la regla T2) y registrar el primer pronóstico prospectivo de los comparadores Q0/A1, que no necesitan LLM, cuando exista el verificador de recibos.
