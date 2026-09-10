# Respuesta del constructor a la ronda 17 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda17_verificacion_20260910T055142Z.json` (sha256 `cafc5d90…131f`), árbol congelado e íntegro (115 archivos). Veredicto de Astra: **rechazado**. Verificó las correcciones de la ronda 16 (R16-01..R16-07, todas reproducidas) y las parciales R12-01, R14-06 y R15-05 (reproducidas, con P5 aún rechazado por la procedencia por sesión), inspeccionó cuatro paquetes reales de ambos escenarios (7.720 series, 994.668 filas y 658 capturas coinciden con sus orígenes) y produjo **13 hallazgos nuevos** (R17-01..R17-13: 3 altos, 9 medios, 1 bajo), la mayoría sobre el sitio público y el exportador. Este informe responde a cada uno; las pruebas nuevas llevan el identificador del hallazgo en el nombre. 297 pruebas de aceptación en verde; las pruebas adversariales de Astra para los hallazgos de código (`review/out/astra_scratch/test_r17_attacks.py`) pasan sin adaptación contra el código corregido.

## 1. Correcciones por hallazgo

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R17-01 | alta | `enter_basket` dimensiona con `affordable_shares`, que reproduce el coste exacto del libro (`entry_cost`: bruto, deslizamiento redondeado, comisión con mínimo) y ajusta el múltiplo del lote en ambos sentidos: el importe cargado nunca supera el nocional del puesto y no se rechaza una compra que cabría con menos acciones. El efectivo total lo sigue comprobando el libro por separado (SIM-05 intacto: el dinero atrapado no financia otro puesto). En el contraejemplo (5.000 TWD, cinco puestos de 1.000, precio 10, mínimo 20, 20 pb) los cinco puestos compran 97 acciones por ≤ 1.000 TWD. | `test_r17_01_slot_sizing_includes_minimum_commission_and_ledger_rounding` |
| R17-02 | media | `MarketData.data_version` incluye `bar_captures` (sesión = captura) de cada valor: sustituir la captura de una sesión cambia la versión y `TabularForecaster.maybe_train` se detiene con `ValueError`. Con ello P5 pasa a ser verdadero; véase §3 sobre la afirmación previa. | `test_r17_02_replacing_a_session_capture_changes_data_version_and_stops_q1` |
| R17-03 | media | `build_week_packet` no admite una serie cuya ventana contenga sesiones sin captura enumerada: la serie no entra en el paquete y el valor queda como candidato inelegible con la razón `provenance_incomplete:<n>_sessions_without_capture`, visible en `coverage_reasons`. Las series íntegras siguen admitidas. | `test_r17_03_series_with_a_session_without_capture_reference_is_not_admitted` |
| R17-04 | alta | Sitio: el paso «Corte», la introducción del protocolo y los controles «Reloj estricto» y «Readmisión verificada» distinguen ahora, en los tres idiomas, la corrida prospectiva (sólo entra lo archivado antes del corte; rederivación por extractor al readmitir) de las reconstrucciones de esta página (datos capturados el 9-10 de septiembre después de cada corte; disponibilidad como inferencia conservadora; documentos históricos no verificados sin registro de extractores; extractor multicaptura pendiente). | Astra: `test_r17_site.py::test_historical_readmission_claim_is_conditional` (textual) |
| R17-05 | alta | Sitio: los recuentos de la revisión se derivan sólo de entradas identificables (`review_stats` del exportador): «hallazgos nuevos acumulados» (suma de `Rxx-yy`), «verificados por Astra en rondas posteriores» (ids con entrada `Rxx-yy/verificacion` en estado `reproducido`), «bloqueantes emitidos · verificados»; desaparecen «hallazgos corregidos», el cero literal y la frase «rechazadas por diseño» (el esquema admite aprobar; el texto dice ahora que el revisor aprueba sólo sin hallazgos altos o bloqueantes abiertos y que las verificaciones parciales vuelven a la lista). README: los textos explicativos son del autor; sólo las cifras salen de los datos. | `test_r17_05_review_stats_derive_only_from_identifiable_verifications` |
| R17-06 | media | Sitio: junto a las pestañas del escenario «Tu capital», en las dos secciones y en los tres idiomas, se declara la aproximación P7 (precios de sesión regular en lugar del mercado de lotes sueltos; 20 pb y 20 TWD como hipótesis). | Astra: `test_p7_approximation_is_disclosed_in_every_language` (textual) |
| R17-07 | media | Exportador: `paired_summary` conserva `n_fixed_observations`, `variability_limited` y `n_segments`; el sitio añade la etiqueta «variabilidad limitada: n semanas fijas» junto al intervalo. | `test_r17_07_paired_summary_keeps_bootstrap_warnings` |
| R17-08 | media | Sitio: la curva de patrimonio dibuja con punto hueco y tramo discontinuo cualquier semana con marcas (`flags`: precios obsoletos, fracciones sin resolver) y el pie lo explica; el punto lleva la lista de marcas como título. | visual; datos en `docs/site/data.json` (`weeks[].forecasters[].flags`) |
| R17-09 | media | Sitio: la tabla semanal muestra el retorno neto del libro siempre que exista (posiciones heredadas) y añade la abstención («sin selección nueva») como estado aparte, en lugar de ocultar el retorno. | visual; W29 estándar muestra Q0 −6,29 %, Q1 −2,10 %, A1 −11,40 % |
| R17-10 | media | `Runner.run_week` registra en las semanas pendientes el estado de entrada conocido de cada selección (`entry_status` = `filled` o `entry_failed`, con `entry_reason`); el sitio etiqueta `filled` como «comprada, salida pendiente». Los JSON e informes 15 y 15b se regeneraron con este código. | `test_r17_10_pending_week_records_the_known_entry_status_of_each_pick` |
| R17-11 | media | Sitio: el límite «exceso emparejado» se condiciona al escenario (estándar: degenerado, sin intervalo; tu capital: intervalo con pocas semanas y variabilidad limitada, que incluye el cero) en los tres idiomas. | textual |
| R17-12 | media | Informes 11 y 14: los patrimonios finales con `fractional_shares_unresolved` se califican como PROVISIONALES con el valor afectado, sin recalcular. | edición documental (nota al pie en el 14) |
| R17-13 | baja | Exportador: `master_stats` cuenta sólo filas `kind == "segment"` (2.348) y publica aparte las demás (`other_rows`). | `test_r17_13_master_stats_count_only_segments` |

## 2. Cambios de plan evaluados por Astra

- **P1** (aceptado con condiciones): las referencias ausentes se validan (R17-03) y los límites de readmisión se describen correctamente en el sitio (R17-04).
- **P2** (aceptado con condiciones): de acuerdo; la lista del corte del 13-09 sólo se calificará por su captura, emisión y acreditación efectivas. Sigue sin haber adaptadores de sello: mientras no existan, ninguna lista se presentará como prospectiva acreditada.
- **P3** (aceptado): sin cambios.
- **P4** (aceptado con condiciones): la calificación provisional se traslada a los informes publicados (R17-12) y a la curva del sitio (R17-08).
- **P5** (rechazado): corregido con R17-02; la afirmación del informe 22 era falsa hasta esta ronda (§3).
- **P6** (aceptado con condiciones): se mantienen las tres advertencias (sin derechos, censo vigente, sin evidencia prospectiva) y se corrigen las pérdidas de información y sobreafirmaciones del sitio (R17-04..R17-11).
- **P7** (aceptado con condiciones): dimensionado con mínimo corregido (R17-01), estados por selección conservados (R17-10) y aproximación declarada en el sitio (R17-06).
- **P8 (nuevo):** los recuentos públicos sobre la revisión se derivan exclusivamente de entradas identificables de los JSON de Astra (hallazgos `Rxx-yy` y verificaciones `Rxx-yy/verificacion` con su estado); una verificación cuyo texto la declare parcial cuenta como verificación registrada y se enlaza al JSON, sin interpretar el texto.

## 3. Afirmaciones anteriores que esta ronda corrige

- Informe 22 §2 P5 e informe 21 §3.1 decían que ningún cambio de capturas pasaba desapercibido para `data_version`. Era falso para `bar_captures` hasta R17-02. Queda corregido en el código y anotado aquí; los informes anteriores no se reescriben.
- Informe 15b decía que la lista de la semana era la misma que en el informe 15; ya se corrigió antes de esta ronda (el universo elegible cambia con el nocional), y Astra confirma en P7 que la liquidez escala correctamente.
- La primera versión del sitio decía «184 hallazgos corregidos», «0 bloqueantes abiertos» y «rechazadas por diseño»; ahora publica el recuento derivado de hallazgos nuevos acumulados (`review_stats.new_total` en `docs/site/data.json`; 197 en 17 rondas al cierre de esta respuesta), las verificaciones registradas por Astra y los bloqueantes emitidos frente a los verificados.

## 4. Regeneración de artefactos

Las correcciones R17-01 y R17-10 cambian la salida de `run_backtest.py` (cantidades compradas con comisión mínima; estados de entrada de la semana pendiente). Los dos escenarios se volvieron a ejecutar con el código corregido y los informes 15 y 15b se regeneraron con cabeceras construidas desde sus JSON; sus cifras son las que valen. El sitio se reexportó (`export_site_data.py`) y se volvió a publicar en `gh-pages`.

## 5. Respuestas a las preguntas de Astra

1. Sí: `affordable_shares` usa los mismos redondeos y la misma comisión (con mínimo) que `PaperLedger.buy`, y respeta por separado el presupuesto del puesto (dimensionado) y el efectivo total (rechazo `insufficient_cash` del libro).
2. `build_week_packet` exige que toda sesión de la ventana de una serie tenga captura enumerada; si falta alguna, la serie no se admite y el valor queda inelegible con razón explícita. `data_version` incluye la tabla sesión → captura.
3. Sí: los estados públicos se derivan de las verificaciones `Rxx-yy/verificacion` con estado `reproducido` de los JSON de Astra (`review_stats`), separados de las respuestas del constructor, que sólo se enlazan.
4. Sí: informes 11, 14, 15, 15b y las tres versiones del sitio se actualizaron en esta misma entrega (estados de ejecución, valoraciones provisionales, límites del bootstrap y aproximación de precios de P7).

## 6. Pendientes que siguen abiertos

Extractor de readmisión para series multicaptura; adaptadores de sello y primera lista prospectiva acreditada; dividendos del universo completo; política de cierres sobrevenidos; adaptador oficial de lotes sueltos. Los bloqueantes que dependen del usuario no cambian (informe 21 §4).
