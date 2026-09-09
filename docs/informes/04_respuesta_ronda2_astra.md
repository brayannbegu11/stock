# Respuesta del constructor a la ronda 2 de revisión (GPT-6 Astra)

> **Nota de vigencia (R05-12):** las descripciones de API y garantías de este informe corresponden a la ronda en que se escribió y fueron sustituidas o precisadas por rondas posteriores (`WeeklyObservation.sealed` → `seal_capture_id` + `store`; `sealed_receipts` → sello recalculado desde `RawStore` con registro fijo en `twlab.seals`; atribución proporcional → lotes con propietario). El estado vigente es el del informe de respuesta más reciente.

**Entrada:** `review/out/ronda2_correcciones_20260909T182736Z.json` (sha256 `30c56e73…f716b`), esfuerzo `high`, sandbox `workspace-write` con comprobación de integridad (49 archivos congelados; ninguno cambió durante la ronda). Veredicto de Astra: **rechazado**. 37 entradas: 16 verificaciones de hallazgos de la ronda 1 cerrados correctamente (R01-01/03/05/07/08/10/11/13/14/15/16/17/19/23/24/25) y 21 hallazgos nuevos o parciales (R02-01..R02-21), todos reproducidos por Astra con pruebas propias conservadas en `review/out/astra_scratch/`.

**Salida:** todas las pruebas en verde al cierre de la ronda (el recuento vigente está en `README.md`); cada R02 tiene una prueba nombrada que fallaba antes y pasa después. La ronda 3 encontró siete de estas correcciones parciales; ver informe 05.

Astra tenía razón en todos los casos. Cuatro eran regresiones introducidas por mis correcciones de la ronda 1 (R02-10, R02-11, R02-13, R02-15): corregir sin volver a leer el archivo real y sin probar los caminos combinados fue el error de método.

## 1. Hallazgos y acción tomada

| Id | Sev. | Qué estaba mal | Corrección | Prueba |
|---|---|---|---|---|
| R02-01 | bloq. | `capture_id` sólo seleccionaba un registro: cualquier captura real «acreditaba» cualquier documento. | `Document.source_sha256` obligatorio en prospectivo; el paquete exige `rec.source_id == doc.source_id` y `doc.source_sha256 == rec.sha256`; si no, `provenance_mismatch`. | `test_r02_01_capture_from_other_source_cannot_attest_document` |
| R02-02 | bloq. | Dos documentos con el mismo `doc_id` colapsaban en el manifiesto y el hash. | `build_packet` rechaza `doc_id` repetidos; el manifiesto es una lista ordenada. | `test_r02_02_duplicate_doc_ids_are_an_error_not_a_hash_collision` |
| R02-03 | alta | El solape se comprobaba sólo contra la vista actual. | `_check_no_overlap` comprueba la vista actual **y** la vista conocida en el `recorded_at` de la fila nueva. | `test_r02_03_no_overlap_in_historical_views_either` |
| R02-04 | alta | Residuo de lote tras un split aparecía como pérdida. | `gross_pick_return` valora toda la cantidad final (vendida + residuo + fracción) al precio de salida; `Slot.exit_residual_quantity` registrado. | `test_r02_04_partial_lot_exit_after_split_is_not_a_loss` |
| R02-05 | alta | Dividendo sin fecha de pago se abonaba de inmediato. | Sin `pay_at` → cobro pendiente **no disponible**; `set_payment_date` lo fija y `advance_to`/cualquier evento lo abona al vencer. | `test_r02_05_missing_payment_date_never_creates_spendable_cash` |
| R02-06 | bloq. | El plazo lo traía la predicción; `issued_at == cutoff` pasaba. | `Packet.deadline_at` derivado del protocolo (`weekly_deadline(cutoff, calendar)` = 08:30 de la siguiente sesión); la predicción debe reproducirlo; `issued_at` estrictamente posterior al corte. | `test_r01_18_r02_06_temporal_order_and_deadline_come_from_packet`, `test_r02_06_deadline_is_carried_by_the_packet`, `test_weekly_deadline_derives_from_protocol_and_calendar` |
| R02-07 | bloq. | `status="verified"` era una declaración; recibos inventados validaban; prospectivas sin sello se evaluaban. | El sello **no se lee de ningún campo**: `RawStore.is_sealed` lo recalcula ejecutando el verificador registrado por autoridad, con digest, instante acreditado válido y opcionalmente `not_after`. `validate_prediction` exige un recibo del archivo y paquete prospectivo (en la ronda 3 se demostró que un identificador suelto no bastaba: ahora el sello debe ligar digest, captura y paquete; ver informe 05, R03-04). El bootstrap exige sello para la clase prospectiva siempre. | `test_r01_20_r02_07_seal_is_recomputed_never_read`, `test_r02_07_fabricated_verified_receipt_does_not_seal`, `test_r02_07_prospective_requires_sealed_receipt_and_prospective_packet`, `test_sta01_*` |
| R02-08 | alta | `week_id` sin formato; bloques que saltaban semanas inválidas. | `week_id` ISO `AAAA-Wnn` validado con `date.fromisocalendar`; con `block_length > 1` las semanas válidas deben ser consecutivas. | `test_r02_08_daily_rows_are_not_weeks_and_blocks_do_not_bridge_gaps` |
| R02-09 | media | Cualquier nombre en la lista permitida valía como calibrador. | Registro `CalibratorRecord(trained_until, evaluated_out_of_sample)`; se exige ventana cerrada antes del corte y evaluación fuera de muestra; un conjunto sin metadatos se rechaza. | `test_r01_22_r02_09_calibrator_needs_registry_with_temporal_evidence` |
| R02-10 | alta | `replace()` sobre un payload ya congelado fallaba (regresión). | `__post_init__` descongela antes de copiar y volver a congelar. | `test_r02_10_prospective_nested_payload_survives_replace` |
| R02-11 | alta | El manifiesto real (formato de la primera corrida) ya no se podía leer (regresión). | `CaptureRecord.from_manifest_line` ignora campos desconocidos y traduce los campos heredados; prueba sobre `data/audit/manifest_2026-09-09.jsonl` y sobre `data/raw` cuando existe. | `test_r02_11_*` (3) |
| R02-12 | alta | `change_segment` cerraba antes de validar. | Validación completa de la fila nueva y del cierre, comprobación de solapes con la fila cerrada simulada, y sólo entonces se anexan ambas. | `test_r02_12_change_segment_is_atomic` |
| R02-13 | alta | Contrasplit creaba acciones (regresión). | Cantidad total = cantidad × ratio; parte entera a `shares`, resto a `unresolved_fraction`; nada se crea ni se descarta. | `test_r02_13_reverse_split_preserves_quantity` |
| R02-14 | alta | Vender las enteras cerraba una posición con fracción pendiente. | La posición sólo se cierra con cantidad total cero; la fracción se valora y se marca. | `test_r02_14_fraction_remains_pending_after_selling_whole_shares` |
| R02-15 | bloq. | `valuation` escribía `last_price` (precio futuro en valoración pasada). | `valuation` es pura: no muta estado ni reloj; `last_price` sólo cambia con ejecuciones y splits. | `test_r02_15_valuation_is_pure_and_cannot_rewrite_past_prices` |
| R02-16 | media | Cobros abonados en orden de declaración. | Orden de fecha de pago. | `test_r02_16_receivables_settle_in_payment_order` |
| R02-17 | media | Cobro vencido seguía pendiente sin operar. | `valuation` refleja los cobros vencidos a la fecha (sin abonarlos); `advance_to(at)` público procesa pagos en semanas sin negociación. | `test_r02_17_due_receivable_is_reflected_and_advance_to_pays_without_trading` |
| R02-18 | alta | Calendario mutable dentro de `CalendarStore`. | `TradingCalendar.__setattr__/__delattr__` bloqueados tras la construcción; el almacén sólo acepta esa clase. | `test_r02_18_calendar_is_immutable` |
| R02-19 | alta | Filas contradictorias o con negación clasificadas. | Negaciones (不休市, 不放假, 未休市, 取消休市) y coincidencia simultánea de marcadores → `unknown` → carga detenida. | `test_row_classification`, `test_unclassified_or_contradictory_rows_refuse_to_guess` |
| R02-20 | media | Tipos inválidos lanzaban excepción en el validador. | Comprobación de tipos por campo; todo problema se devuelve en la lista. | `test_r02_20_malformed_responses_yield_problems_not_exceptions` |
| R02-21 | media | Informes con afirmaciones no respaldadas (0/1/2 sesiones, A2, A6, «todos corregidos», «atómico»). | Informes 01 y 03 corregidos; pruebas de una y dos sesiones añadidas; pagos sin negociación cubiertos por `advance_to`. | `test_sim10_weeks_with_one_and_two_sessions_synthetic`, R02-17 |

## 2. Respuestas a las preguntas del revisor

1. **Vínculo versión documental ↔ bytes ↔ transformación.** Cada `Document` prospectivo lleva `capture_id`, `source_sha256` y `derivation` (identificador del extractor). El paquete rechaza cualquier documento cuyo `source_sha256` o `source_id` no coincida con el `CaptureRecord`. Lo que aún **no** existe es el extractor que produzca documentos desde los bytes y registre su `derivation`: llegará con los adaptadores de ingestión, y su salida se probará contra capturas reales (original y corrección) antes de admitir la clase `verified_version`.
2. **Registro verificable de predicción.** Cadena propuesta e implementada en parte: (a) el paquete lleva `packet_hash` (contenido + corte + plazo derivado del protocolo); (b) la predicción debe citar `packet_id`, reproducir corte y plazo, y sólo puede ser `selected` si `issued_at` cae en `(cutoff, deadline]`; (c) en prospectivo, la predicción archivada como captura del `RawStore` recibe un recibo y sólo está sellada si `RawStore.is_sealed` lo recalcula con un verificador registrado y `not_after = deadline`; (d) `validate_prediction` exige ese recibo en `sealed_receipts`. Falta el verificador criptográfico real y la función que encadene `raw_response_hash` con el hash del paquete; ambos entran antes del primer pronóstico prospectivo.
3. **Política de fracciones, pagos sin fecha y semanas sin operaciones.** Fracciones: se conservan en `unresolved_fraction`, se valoran al último precio de ejecución con bandera y nunca se venden en la sesión ordinaria; su resolución (efectivo en lugar de fracción, 零股) requiere el adaptador de lotes menores, pendiente. Pagos sin fecha: cobro pendiente no disponible hasta `set_payment_date`. Semanas sin operaciones: `advance_to(at)` procesa pagos y mantiene el orden del diario; la corrida semanal se registra `invalid:no_sessions`.

## 3. Posiciones finales tras la evaluación de Astra

Acepto todas las condiciones de la ronda 2. Cambios documentales aplicados: A2 (no se promueve `verified_original` por existir un campo de hora; las noticias no se califican de «copias»), A6 (el fundamento es el invariante de reproducibilidad, no una tasa externa), §8 del informe 01 y las frases «atómicamente» y «0/1/2 sesiones» del informe 03.

## 4. Abierto tras esta ronda

- Verificador criptográfico de recibos (OpenTimestamps / RFC 3161) y encadenado `raw_response_hash` ↔ `packet_hash`.
- Extractores con `derivation` y prueba original/corrección sobre capturas reales.
- Adaptador de lotes menores (零股) para resolver fracciones y residuos.
- Módulo de informe estadístico STA-02/03/05/06/07.
- Congelamiento de T2 y demás valores del protocolo (decisión del usuario).
