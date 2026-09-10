# Respuesta del constructor a la ronda 18 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda18_verificacion_20260910T074639Z.json` (sha256 `22139d1e…1a65e`), árbol congelado e íntegro (117 archivos legibles). Veredicto de Astra: **aprobado con cambios**, el primero no adverso en 18 rondas: verificó las trece correcciones de la ronda 17 (todas reproducidas; R17-03 parcial por el mapa vacío, tratado aquí como R18-01), repitió 510 selecciones archivadas reproduciendo 474 entradas y los seis patrimonios finales, inspeccionó 36 paquetes (69.520 series, 8.957.514 referencias por sesión, 108 predicciones archivadas) y produjo **11 hallazgos nuevos** (R18-01..R18-11: 9 medios, 2 bajos; ninguno alto ni bloqueante). Este informe responde a cada uno; las pruebas nuevas llevan el identificador del hallazgo en el nombre. 304 pruebas de aceptación en verde; las pruebas adversariales de Astra de esta ronda (`review/out/astra_scratch/test_r18_attacks.py`) pasan contra el código, el exportador y el sitio corregidos, y las que dependen de los informes regenerados pasan tras la regeneración (§4).

## 1. Correcciones por hallazgo

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R18-01 | media | Contrato de procedencia por fuente: para las fuentes por fecha (`SESSION_CAPTURE_SOURCES = ("twse", "tpex")`) toda sesión de la ventana debe tener captura enumerada; un mapa `bar_captures` vacío ya no convierte la serie en una de captura única, sino que la deja inadmitida con `provenance_incomplete`. Las series FinMind de captura única siguen admitidas por `price_capture`. | `test_r18_01_empty_capture_map_on_a_daily_source_is_not_a_single_capture_series` |
| R18-02 | media | El manifiesto común por fuente no sobrescribe: si dos series de la misma fuente referencian capturas distintas de una misma sesión, `build_week_packet` lanza `ManifestInconsistent` y el paquete no se construye (respuesta a la pregunta 2: se rechaza el conflicto; no se conservan manifiestos divergentes por serie). | `test_r18_02_conflicting_session_captures_between_series_stop_the_packet` |
| R18-03 | media | Exportador: una verificación sólo se reconoce con identificador completo (`fullmatch` de `Rxx-yy/verificacion`) y sólo cuenta si se refiere a un hallazgo emitido y aparece en una ronda **posterior** a la de emisión. | `test_r18_03_review_stats_require_full_identifiers_and_later_rounds`, `test_r18_03_verification_identifier_must_match_completely` |
| R18-04 | media | Sitio: el subtítulo del indicador de rondas, el título de la sección de revisión y el pie del gráfico se derivan de los datos (`verdictCounts`: rechazadas · aprobadas con cambios · aprobadas; `lastBlockingRound`: última ronda con bloqueantes); desaparecen «todas con veredicto rechazado» y «ninguno bloqueante desde la ronda 6». El texto explica qué significa cada veredicto sin afirmar cuál se produjo. | visual; los tres idiomas usan las mismas funciones |
| R18-05 | media | `Runner.run_week` agrega a los costes de la semana los de las ventas de cestas heredadas ejecutadas en el cierre de esa semana (`inherited_exit_costs_twd`) y publica el denominador (`costs_denominator_twd` = importe bruto comprado + importe bruto vendido de cestas heredadas), de modo que una semana sin compras nuevas tiene tasa de costes definida (respuesta a la pregunta 1). Los patrimonios finales no cambian; sí las tasas medias de costes de los informes regenerados. | `test_r18_05_inherited_exit_fills_carry_their_costs_into_the_week` (libro) y regeneración de 15/15b |
| R18-06 | media | `markdown_report` muestra el retorno neto del libro también en las semanas sin selección nueva («→ neto del libro … (posiciones heredadas)»). | regeneración de 15/15b (fila 2026-W29) |
| R18-07 | media | El resumen exporta `weeks_measured` (retornos netos no nulos) y las tablas generadas, las cabeceras de los informes 15/15b y el sitio lo usan como denominador de «semanas positivas» («de las medibles»), separado de `weeks_selected` y `weeks_operated`. | `test_r18_07_summary_counts_measurable_weeks_separately` |
| R18-08 | media | Exportador: conserva `final_flags`, `final_valued_at` y `final_prices_session`; el sitio marca el patrimonio final como PROVISIONAL cuando hay marcas y muestra la fecha y sesión de la valoración final. | `test_r18_08_export_keeps_final_valuation_conditions` |
| R18-09 | baja | Informe 23 §3 remite al recuento derivado (`review_stats.new_total`) y README deja de citar un número fijo de rondas. | textual |
| R18-10 | baja | Informe 15b (cabecera generada) remite a la ubicación real de P7: prompt de la ronda 17, JSON de Astra de esa ronda e informe 23 §2. | textual |
| R18-11 | media | Sitio (tres idiomas): la salida bloqueada se reintenta en el cierre semanal siguiente, no en la sesión siguiente, y la política de cierres sobrevenidos sigue pendiente. | textual |

## 2. Cambios de plan evaluados por Astra

P1–P8 aceptados (P3 y P5 sin condiciones). Condiciones atendidas: mapas vacíos y conflictos entre series (R18-01/02), condiciones de la valoración final en exportador y sitio (R18-08), costes heredados, retornos ocultos, denominadores y textos temporales (R18-05/06/07/11), identificadores completos y rondas posteriores en los recuentos (R18-03), títulos y subtítulos derivados (R18-04), referencia documental de P7 (R18-10). El extractor multicaptura sigue explícitamente pendiente.

## 3. Afirmaciones anteriores que esta ronda corrige

- Informe 23 §1 (R17-03) decía que una serie con sesiones sin captura no se admitía; era cierto sólo si el mapa no estaba vacío. Corregido con R18-01.
- Las tasas de costes publicadas hasta ahora (informes 15 y 15b, sitio) excluían las ventas heredadas: las de la regeneración de §4 son las válidas.
- El sitio afirmaba «todas las rondas con veredicto rechazado»; con el veredicto de esta ronda la afirmación habría sido falsa. Ahora se deriva.

## 4. Regeneración de artefactos

R18-05, R18-06 y R18-07 cambian el JSON y el informe generado por `run_backtest.py` (costes semanales, retornos en semanas sin selección, `weeks_measured`). Los dos escenarios se volvieron a ejecutar con el código corregido; los informes 15 y 15b se regeneraron con cabeceras construidas desde sus JSON; el sitio se reexportó y se volvió a publicar en `gh-pages`.

## 5. Respuestas a las preguntas de Astra

1. Sí: los costes se agregan por fecha de ejecución de todas las cestas (nueva y heredadas) y el denominador publicado es el importe bruto comprado más el vendido de cestas heredadas en la semana (`costs_denominator_twd`); una semana con sólo ventas heredadas tiene tasa definida.
2. Se rechaza el conflicto: dos series de una misma fuente no pueden referenciar capturas distintas de una misma sesión; el paquete no se construye (`ManifestInconsistent`).

## 6. Pendientes que siguen abiertos

Extractor de readmisión para series multicaptura; adaptadores de sello y primera lista prospectiva acreditada (corte del 13-09-2026); dividendos del universo completo; política de cierres sobrevenidos; adaptador oficial de lotes sueltos; backtest con el historial 2021-2026 ya descargado (informe 15c, en cola). Los bloqueantes que dependen del usuario no cambian (informe 21 §4).
