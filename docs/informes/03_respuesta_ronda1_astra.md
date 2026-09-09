# Respuesta del constructor a la ronda 1 de revisión (GPT-6 Astra)

> **Nota de vigencia (R05-12):** las descripciones de API y garantías de este informe corresponden a la ronda en que se escribió y fueron sustituidas o precisadas por rondas posteriores (`WeeklyObservation.sealed` → `seal_capture_id` + `store`; `sealed_receipts` → sello recalculado desde `RawStore` con registro fijo en `twlab.seals`; atribución proporcional → lotes con propietario). El estado vigente es el del informe de respuesta más reciente.

**Entrada:** `review/out/ronda1_nucleo_20260909T180407Z.json` (sha256 `f5eb4dec…7b216`), esfuerzo `high`, sandbox `read-only`. Veredicto de Astra: **rechazado**, 25 hallazgos (6 bloqueantes, 13 altos, 6 medios; 24 reproducidos, 1 hipótesis).
**Salida:** 111 pruebas en verde (`python -m pytest -q -p no:cacheprovider`), 39 nuevas; cada hallazgo reproducible tiene una prueba que fallaba antes de la corrección y pasa después.

La revisión fue correcta en lo esencial: encontró un error factual mío (R01-01) que había convertido en «hallazgo de auditoría», dos caminos de filtración temporal (R01-02, R01-03), un aislamiento de predictor que no aislaba (R01-05) y una decena de errores contables. Ninguno lo habría detectado una lectura aprobatoria.

## 1. Hallazgos y acción tomada

| Id | Sev. | Qué estaba mal | Corrección | Prueba |
|---|---|---|---|---|
| R01-01 | bloq. | El endpoint de festivos mezcla cierres con filas informativas de negociación (開始交易日, 最後交易日); las traté todas como cierres → 240 sesiones en vez de 243 y una acusación falsa a `exchange_calendars`. | `classify_holiday_row` distingue `closure`, `session_marker` y `unknown`; una fila no clasificable **detiene la carga**. Informes 01/02 corregidos; A3 retirado. | `test_r01_01_trading_day_markers_are_sessions`, `test_generic_calendar_agrees_with_official_2026`, `test_unclassified_row_refuses_to_guess` |
| R01-02 | bloq. | `available_at`/`first_seen_at` los ponía el llamante; `published_at` posterior a `available_at` se admitía. | `published_at > available_at` → `inconsistent_metadata`. En prospectivo cada documento debe enlazar un `CaptureRecord` del `RawStore`; `first_seen_at` se toma de `ingested_at` de la captura, un reloj inyectado se rechaza (`synthetic_capture_not_prospective`) y `allow_injected_clock` es incompatible con `prospective_registered`. | `test_r01_02_*` (2), `test_pit04_and_pit06_*`, `test_pit07_*` |
| R01-03 | alta | Comparación de `datetime` con la misma zona ignora `fold`. | Todas las comparaciones pasan por `to_utc`/`is_after`. | `test_r01_03_dst_fold_does_not_admit_future` |
| R01-04 | bloq. | `payload` mutable; `packet_hash` usaba un manifiesto previo y omitía metadatos. | `Document` congela el payload (`MappingProxyType` recursivo, copia profunda); `content_hash` cubre todos los campos; `Packet` es inmutable y `packet_hash` se recalcula. | `test_r01_04_delivered_content_is_immutable_and_fully_hashed` |
| R01-05 | bloq. | `GuardedWorkspace` guardaba los resultados en el objeto del predictor y `role` era escribible. | `PredictorView` (con `__slots__`, `role` de sólo lectura) nunca recibe resultados; `open_workspace(role="predictor", outcomes=…)` lanza error; `EvaluatorView` es otra clase. | `test_r01_05_predictor_view_cannot_reach_outcomes` |
| R01-06 | alta | Segmentos solapados admitidos; cerrar el último resucitaba el anterior. | `add` rechaza solapes (`OverlappingSegment`); `change_segment` cierra y abre en una operación (la ronda 2 demostró que no era atómica ni cubría vistas históricas: corregido en R02-03/R02-12, informe 04); una fila sustituta no puede fecharse antes que la sustituida. | `test_r01_06_*`, `test_superseding_row_cannot_predate_*` |
| R01-07 | alta | Eventos terminales sobrescritos. | Lista versionada; `terminal_event(known_at)` devuelve el último conocido entonces. | `test_r01_07_terminal_event_revisions_are_versioned` |
| R01-08 | alta | `classify_coverage` ignoraba mercado e instrumento. | ESB o cualquier instrumento distinto de acción ordinaria nunca elegible. | `test_r01_08_esb_and_non_equity_never_execution_eligible` |
| R01-09 | alta | `exit_basket` vendía las acciones de entrada, no la posición vigente. | Vende la posición del libro (múltiplo de lote); `gross_pick_return` sobre importes de referencia. | `test_r01_09_exit_sells_current_position_after_split` |
| R01-10 | alta | Salida bloqueada no reintentable. | `exit_basket` procesa `filled` y `exit_blocked`; intentos registrados en `notes`. | `test_r01_10_blocked_exit_can_be_retried_after_resumption` |
| R01-11 | alta | `event_id` consumido antes de validar. | Validación completa antes de tocar estado o consumir el id. | `test_sim02_*_r01_11_*` |
| R01-12 | alta | Dividendo pagado a quien compró después de la fecha efectiva; sin orden cronológico; derechos y pago mezclados. | `OutOfOrderEvent` para cualquier evento anterior al último; derechos exigen posición abierta en `effective_at`; `pay_at` separa el pago (cuentas a cobrar, no financian compras). | `test_r01_12_*`, `test_dividend_rights_and_payment_are_separated` |
| R01-13 | media | Impuesto sobre bruto, comisión sobre ejecutado. | Ambos sobre el importe ejecutado (referencia ± deslizamiento). | `test_r01_13_*` |
| R01-14 | media | Componentes redondeados no conciliaban con el efectivo. | Cada componente se redondea con la política declarada (`CostModel.rounding`, por defecto `floor`, a confirmar con el bróker) y el efectivo se mueve por su suma exacta. La fricción de referencia pasa a 584 TWD (`floor`) o 586 (`half_up`) sobre 100.000; la tasa sigue siendo 0,585 %. | `test_r01_14_*`, `test_round_trip_friction_*` |
| R01-15 | media | Venta parcial no reducía la base de coste. | Base proporcional; `realized_pnl` en el `Fill`. | `test_r01_15_*` |
| R01-16 | alta | Precios negativos creaban efectivo. | Validación de dominio (positivo, finito, enteros) antes de cualquier cambio; `CostModel` valida sus tasas. | `test_r01_16_*` |
| R01-17 | alta | Ventas sin restricción de lote. | Venta de lote menor → `odd_lot_requires_separate_mechanism`; la cesta vende sólo múltiplos y deja el residuo anotado. | `test_r01_17_*` |
| R01-18 | bloq. | Sin orden temporal ni igualdad de corte con el paquete. | `cutoff < issued_at <= deadline_at` para `selected`; corte y `packet_id` deben coincidir con el paquete; una corrida tardía sólo puede ser `invalid`. | `test_r01_18_*` |
| R01-19 | alta | Valores y rangos repetidos. | Unicidad de `security_id` y `rank`, rangos contiguos desde 1; `enter_basket` rechaza duplicados. | `test_r01_19_*` (2) |
| R01-20 | bloq. | «Sellado» = dos cadenas no vacías. | `Receipt` con `digest`, `attested_at`, `status` (`pending`/`verified`/`invalid`); `attach_receipt` exige digest = sha256; `verify_receipt` ejecuta un verificador; sólo capturas con reloj del sistema y recibo verificado están selladas. El adaptador real OpenTimestamps/RFC 3161 sigue pendiente (condición de A10). | `test_r01_20_*` (2) |
| R01-21 | alta | `IntervalReturn` sin exposición, moneda ni coste; bootstrap sin unidad semanal. | `IntervalReturn` exige `exposure`, `currency`, `net_of_costs`, `week_id` en la clave de emparejamiento; `WeeklyObservation` con `week_id` único, orden cronológico, una sola clase de evidencia, sellado opcional y corridas inválidas contadas. STA-02/03/05/06/07 siguen pendientes de un módulo de informe. | `test_r01_21_*`, `test_sta01_*`, `test_sta04_*` |
| R01-22 | media | Cualquier cadena valía como calibrador. | Registro de calibradores evaluados (`known_calibrators`); no registrado → problema TXT-07. | `test_r01_22_*` |
| R01-23 | media | Suspensión sin bandera si se pasaba precio. | Bandera siempre. | `test_sim03_*_r01_23_*` |
| R01-24 | alta (hip.) | Plazo legal usado como evidencia de disponibilidad de ingresos históricos. | Política cambiada: sin evidencia de publicación por versión → `unknown` (excluido del paquete principal). La regla de plazo legal queda sólo como experimento de sensibilidad registrado. Los timestamps de publicación de ingresos históricos pasan a ser el primer requisito de la muestra de TEJ. Documentado en informes 01/02; el adaptador con dos versiones sintéticas se escribirá con la ingestión real. | pendiente de adaptador |
| R01-25 | media | «Verificación» de unidades con dos observaciones no comparables. | Redacción corregida: órdenes de magnitud coherentes con la unidad declarada; la prueba de equivalencia emparejada (emisor, mes, alcance, versión) se hará con el archivo real. | `test_revenue_endpoints_declare_thousands_of_twd` sólo cubre la declaración |

## 2. Cambios del plan tras la evaluación de Astra

| Id | Posición de Astra | Resultado |
|---|---|---|
| T1 | acepto con condiciones | Reescrita: la política conservadora sólo aplica a fechas de publicación verificadas; el efecto depende del día de la semana; sensibilidad registrada. |
| T2 | acepto con condiciones | Corregido el hecho (semana del 9-02: tres sesiones). Regla propuesta: semana sin sesiones → corrida `invalid:no_sessions` sin abrir ni cerrar posiciones, **pero el libro sigue procesando dividendos, pagos y eventos**. |
| T3 | acepto con condiciones | Falta de cuota → fallo operativo OPS-02, nunca abstención; adelantar corridas sólo con el mismo corte y paquete. |
| T4 | acepto | Sin cambios. |
| A1 | acepto con condiciones | Se añade: frecuencia por fuente congelada, medición de pérdidas entre capturas (anuncios que desaparecen) y revisión de permisos. |
| A2 | acepto con condiciones | `verified_original` no se concede por existir un campo de hora: exige evidencia de versión (captura con hash). Cobertura documental pendiente declarada. |
| **A3** | **rechazo** | **Retirado.** La autoridad sigue siendo la lista oficial, interpretada por clasificación de filas; XTAI coincide en 2026 y queda como contraste. |
| A4 | acepto con condiciones | `verified_benchmark_series` sigue bloqueado hasta probar continuidad, revisiones y equivalencia apertura-cierre. |
| A5 | acepto con condiciones | Prueba de equivalencia emparejada pendiente; ver R01-25. |
| A6 | acepto con condiciones | Se conserva la distinción reproducido/hipótesis; la tasa externa de alucinación no se usa como argumento sobre esta revisión. |
| A7 | acepto | Sin cambios. |
| A8 | acepto con condiciones | En esta ronda sólo se añadieron pruebas de cero y tres sesiones y el `CalendarStore`; las de una y dos sesiones y el procesamiento de pagos sin negociación (`advance_to`) llegaron en la ronda 2 (informe 04, R02-17 y R02-21). |
| **A9** | **rechazo** | **Retirado.** La petición a TEJ mantiene la muestra completa de INVESTIGACION §6.3; sólo se prioriza el orden (timestamps de publicación de ingresos primero). |
| A10 | acepto con condiciones | Implementado el modelo de recibo verificable; el verificador criptográfico real es la condición pendiente. |

## 3. Respuestas a las preguntas del revisor

1. **Congelamiento para la ronda 2.** El repositorio sigue sin commits porque el usuario no lo ha pedido; para dar una base verificable, `review/run_astra.ps1` genera `review/out/<ronda>_<hora>_baseline.sha256` con el hash de todos los archivos rastreables antes de la revisión y comprueba después que ninguno cambió. `test_catalog.py` apareció durante la ronda 1 porque se añadió en paralelo; no volverá a ocurrir: la ronda 2 arranca sobre el árbol congelado por ese manifiesto.
2. **Vínculo documento ↔ captura.** `Document.capture_id` referencia el `CaptureRecord`; en prospectivo el paquete rechaza documentos sin captura, con captura sintética o con `first_seen_at` distinto de `ingested_at`. Los recibos temporales viven en el `CaptureRecord` (`Receipt`) y sólo cuentan verificados.
3. **Calendario conocido vs. efectivo.** `CalendarStore.as_known_at(known_at)` devuelve la versión registrada en ese momento; `session_overrides` permite horarios por sesión. La versión 2026 de referencia lleva ahora el `recorded_at` real de la captura (02:04:32 del 10-09 Taipei) y, como dice Astra, no tiene recibo; se sella cuando exista el verificador.
4. **Política de acciones corporativas.** Derechos en `effective_at` (exigen posición abierta en esa fecha), pago en `pay_at` como cuenta a cobrar, fracciones de acción acumuladas en `unresolved_fraction` con bandera, dividendos en acciones (`stock_dividend`) soportados, retiradas sin precio terminal marcadas `delisted_unresolved`. Cualquier `kind` no soportado lanza error y el llamante debe marcar la simulación afectada como bloqueada.
5. **Evaluación con predicciones selladas.** `WeeklyObservation.sealed` y `require_sealed=True` en el bootstrap para la clase prospectiva; `IntervalReturn` fuerza exposición, moneda y costes. Falta el módulo de informe que cubra STA-02 (contaminación de reserva), STA-03 (registro de ensayos), STA-05/06/07: entra en la siguiente entrega, antes de cualquier resultado.
6. **Muestras de auditoría en el repositorio.** `data/audit/manifest_2026-09-09.jsonl` es el manifiesto de la primera corrida real de captura (37 endpoints, sha256, `ingested_at` del reloj del sistema); los bytes están en `data/raw/` fuera de git por tamaño y se verifican con `RawStore.verify()`. Las conclusiones del informe 02 que no se sostengan con ese manifiesto se marcaron como pendientes.

## 4. Lo que sigue abierto tras esta ronda

- Verificador criptográfico de recibos (OpenTimestamps / RFC 3161).
- Módulo de informe estadístico (STA-02, 03, 05, 06, 07).
- Adaptadores de ingestión reales sobre `RawStore` y prueba de equivalencia de unidades emparejada.
- Regla de semanas con 0/1/2 sesiones incorporada al protocolo antes del congelamiento (decisión del usuario).
