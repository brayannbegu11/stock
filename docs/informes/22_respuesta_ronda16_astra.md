# Respuesta del constructor a la ronda 16 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda16_verificacion_20260910T014302Z.json` (sha256 `2b2ae570…31fa`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Verificó las correcciones de la ronda 15 (todas completas salvo R12-01, R14-06 y R15-05, parciales por el contenido del calendario y la fecha ex en `data_version`) y produjo 7 hallazgos nuevos (R16-01..R16-07: 2 altos, 5 medios). Además comprobó de forma independiente que **15.538 pares TWSE–FinMind de 2025 coinciden exactamente** en apertura, cierre, volumen e importe (incluidos 102 sin precio regular): la fuente oficial por fecha y FinMind son equivalentes en los datos que compartimos.

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada hallazgo tiene prueba nombrada; backtest del universo regenerado con la procedencia corregida; informe 15 corregido (§2 y P2/P6); escenario del usuario (lotes sueltos) añadido como informe 15b.

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R16-01 | alta | Los adaptadores comprueban que la fecha declarada en el cuerpo (`date`) coincide con la sesión archivada; si no, `DailyQuoteSchemaError`. | `test_r16_01_body_date_must_match_the_archived_session` |
| R16-02 | alta | Procedencia real de los paquetes diarios: `Security.source_id` (`twse`/`tpex`) y `derivation` (`twse_mi_index_daily_v1`/`tpex_daily_quotes_v1`); `capture_id`/`source_sha256` son los de la captura de la última barra conocida al corte, y el `payload` enumera la captura de cada sesión de la ventana (`session_captures`). La readmisión verificada de estos documentos exigirá un extractor multi-captura (pendiente); mientras tanto quedan declarados como no verificados en histórico. | `test_r16_02_r16_03_daily_market_provenance_and_last_kept_capture` |
| R16-03 | media | `price_capture` es la captura de la última barra **conservada** (tras descartar las que no tienen precio regular). | ídem |
| R16-04 | media | Un símbolo repetido en la misma sesión es `DailyQuoteSchemaError`, no una sobrescritura. | `test_r16_04_repeated_symbol_rows_are_an_error_not_an_overwrite` |
| R16-05 | media | Las columnas obligatorias se exigen en la tabla y en cada fila; su ausencia rompe el esquema en vez de convertirse en ceros. | `test_r16_05_missing_columns_break_the_schema_instead_of_becoming_zeros` |
| R16-06 | media | Informe 15 corregido: 80 selecciones y 16 fallos de Q1 (no 85); el dimensionado es proporcional (≈ 796 k TWD por puesto en la última semana, por eso 3037 a 939 TWD tampoco cabe); la comparación con los costes se reformula (la diferencia A1−Q1, 1,39 puntos, supera el coste medio de 0,76 %: los costes no explican por sí solos la diferencia, y con 17 semanas tampoco se puede atribuir a señal). El README explica el umbral variable. | — |
| R16-07 | media | El patrimonio final se califica como provisional ante **cualquier** marca de la valoración final (precio obsoleto incluido). | `test_r16_07_and_user_scenario_flags_and_odd_lot_costs` |
| R15-05 / R14-06 / R12-01 (parciales) | media | `data_version` incluye el contenido del calendario (rango y cierres efectivos, no sólo la etiqueta) y la fecha ex de cada derecho. | `test_r14_06_r15_05_forecaster_refuses_a_market_whose_content_changed_underneath` (calendario con la misma etiqueta; fecha ex) |

## 2. Posiciones de Astra sobre P1..P6

- **P1 (acepto).** Mantenido; la procedencia de los paquetes diarios (R16-02) corregida aparte.
- **P2 (acepto con condiciones).** Aceptada la precisión: la lista de la semana 2026-W37 se archivó el 10-09, **después** de la entrada simulada del lunes 7-09, así que es una reconstrucción histórica, no una predicción prospectiva. El informe 15 lo dice ahora literalmente. La primera lista realmente prospectiva será la del corte del domingo 13-09, emitida antes de la apertura del lunes 14.
- **P3 (acepto).** Mantenido.
- **P4 (acepto con condiciones).** Condición atendida (R16-07).
- **P5 (rechazo).** Aceptado: faltaban el contenido del calendario y la fecha ex. Corregido; la formulación pasa a ser «ningún cambio de barras, derechos, capturas, altas/bajas o calendario efectivo pasa desapercibido».
- **P6 (acepto con condiciones).** Condiciones atendidas: fechas y procedencia corregidas; la ausencia de derechos se declara también en etiquetas y comparaciones (informe 15 §Límites: con derechos el control 100→90 con dividendo 10 rinde 0 %; sin ellos, −10 %).

## 3. Respuestas a las preguntas del revisor

1. **Lista de capturas por serie.** Cada documento de barras enumera en su `payload` (`session_captures`) la captura de cada sesión de la ventana, y `capture_id` es la de la última sesión; la readmisión verificada requiere un extractor que re-derive la serie desde ese conjunto de capturas (pendiente, junto con el catálogo de extractores).
2. **`ex_date` y contenido del calendario en `data_version`.** Incluidos (R15-05).
3. **Evidencia del 10-07-2026.** Ninguna más que la ausencia de datos en ambas fuentes oficiales para una sesión del calendario anual; el informe 15 lo describe como «sesión oficial sin datos», no como cierre acreditado, y la política de cierres sobrevenidos (y su fuente) sigue abierta.
4. **Afirmación sobre el corte de conocimiento.** Retirada del informe 15: el archivo no acredita lo que un modelo sabe o ignora, y esta corrida no usa LLM.

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161; registro de producción vacío.
- Catálogo de extractores reales (incluido el multi-captura de series diarias); pronosticadores con LLM (L1/L2).
- Dividendos históricos del universo completo (fuente oficial de derechos por fecha pendiente).
- Política de cierres sobrevenidos y su fuente oficial; versiones históricas del calendario y de los derechos.
- Adaptador de lotes menores con precios propios de ese mercado (el escenario del informe 15b usa precios de sesión regular como aproximación declarada); maestro histórico completo; emisor con TEJ.
- Congelamiento del protocolo (costes contratados, nocional y dimensionado, tolerancia de exposición, `block_length`, liquidez, tablero de innovación). Decisión del usuario; el escenario de lotes sueltos de 15.000 TWD por puesto es la primera aproximación a su capital real.
