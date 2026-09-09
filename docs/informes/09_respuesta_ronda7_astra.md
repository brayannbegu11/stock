# Respuesta del constructor a la ronda 7 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda7_verificacion_20260909T195202Z.json` (sha256 `3ef981c1…4a28`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Confirmó las 10 correcciones de la ronda 6 (R06-01..R06-10, con matices que se convirtieron en hallazgos nuevos) y produjo 10 hallazgos (R07-01..R07-10: 6 altos, 4 medios). Su batería nueva (`review/out/astra_scratch/test_ronda7_*.py`) produjo 21 fallos y 2 controles positivos.

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada R07 tiene prueba nombrada. Además, después de la ronda se construyó la primera capa de datos reales (informes 10 y 11), que no formaba parte de la ronda y queda para la ronda 8.

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R07-01 | alta | El evaluador ya no valida sólo el esquema: `_archived_forecast` reconstruye el candidato archivado y ejecuta `validate_prediction` completo, incluida la ventana temporal (`cutoff < issued_at ≤ deadline`) y el rechazo de una selección cuyo plazo coincide con el corte. | `test_r06_02_r06_03_r06_04_r07_01_r07_02_r07_03_evaluator_validates_the_archived_forecast_completely` |
| R07-02 | alta | Las reglas semánticas (`semantic_problems`: experimento registrado, selecciones y rangos únicos, rangos contiguos, calibradores conocidos) se aplican también en la evaluación, con `known_calibrators` y `experiment_ids` pasados por el evaluador. | ídem |
| R07-03 | alta | La evaluación prospectiva exige un **registro de paquetes** (`packets: Mapping[packet_hash, Packet]`); el paquete recuperado debe reproducir el `packet_hash` del sobre y coincidir en `packet_id`. Para poder archivarlo existen `packet_to_json`/`packet_from_json` (el segundo falla si el hash no se reproduce). `block_bootstrap_mean` sin `store`, `packets` o `calendar` no evalúa la clase prospectiva. | ídem; `test_packet_archive_round_trip_preserves_hash` |
| R07-04 | alta | El calendario es **obligatorio** para verificar el plan del paquete: sin calendario `validate_prediction` devuelve `calendar_required_to_verify_packet_plan`; con calendario, el plazo/entrada/salida deben ser exactamente los que `plan_week` deriva del corte (`packet_plan_does_not_match_calendar`). Ya no basta con «dentro de la semana». | `test_r07_04_calendar_is_required_to_verify_a_packet_plan`, `test_r07_04_shifted_deadline_within_the_week_is_rejected_because_the_calendar_is_mandatory` |
| R07-05 | media | Una semana `invalid:no_sessions` exige `deadline_at`, `entry_at` y `exit_at` nulos en el paquete (`packet_no_sessions_week_cannot_have_deadline_entry_or_exit`). | `test_r07_05_no_sessions_packet_must_have_null_deadline` |
| R07-06 | alta | Un reintento bloqueado de un puesto `exited` pasa a `exit_blocked` y refresca cantidades, dividendos y ventas de referencia desde el libro; el informe lo cuenta como salida bloqueada. | `test_r07_06_blocked_retry_of_an_exited_slot_is_reported_blocked_with_fresh_figures` |
| R07-07 | alta | `exit_basket` empieza con `ledger.advance_to(at)`: una salida fechada antes del último evento del libro levanta `OutOfOrderEvent` aunque no venda nada. Ninguna salida puede incorporar flujos futuros. | `test_r07_07_exits_respect_the_ledger_clock` |
| R07-08 | media | El precio de cierre usado para vender o valorar residuos pasa por `_positive_decimal`: negativo, cero o NaN levantan `LedgerError`. | `test_r07_08_residual_valuation_rejects_invalid_prices` |
| R07-09 | media | La venta FIFO consume sólo acciones enteras de cada lote; las fracciones pendientes de cada propietario se conservan y `available` cuenta sólo enteras. | `test_r07_09_fifo_sale_never_consumes_fractional_rights` |
| R07-10 | media | Documentación: 08 §2 reescrito como restricciones estructurales sobre un plazo declarado (lo que había entonces) con remisión a este informe; nota de alcance en la fila R06-09 de 08; árbol de módulos y recuento de 01 §6-7 actualizados; el recuento de pruebas vive sólo en `README.md` y `AGENTS.md` remite a él. | criterios documentales de R07-03/04 (pruebas anteriores) |

## 2. Posiciones de Astra sobre P1, P2 y P3

- **P1 (acepto con condiciones).** Aceptada la condición: la garantía de re-derivación documental no se extendía al evaluador. Con R07-03 el evaluador recupera el paquete del registro y lo re-valida por completo; los extractores reales y la prueba original/corrección sobre capturas siguen pendientes y así consta en §4.
- **P2 (acepto con condiciones).** Coincidimos: la formulación de 08 §3 es exacta bajo sus premisas y no certifica la corrección semántica del evaluador. R07-01..04 quedan corregidos; el archivo del paquete acreditado existe (`packet_to_json`, usado por la demo del informe 11, que archiva cada paquete en el `RawStore` bajo `packet/Q0/<semana>`); los adaptadores criptográficos siguen pendientes y el registro de producción permanece vacío.
- **P3 (rechazo).** Aceptado el rechazo. La garantía general sobre reintentos y resultados se sustituye por tres garantías acotadas y probadas: (i) toda salida respeta el reloj del libro (R07-07); (ii) todo reintento, vendido o bloqueado, refresca las cifras del puesto desde el libro (R07-06); (iii) la venta FIFO nunca consume derechos fraccionarios (R07-09). Lo que no cubre: lotes menores (零股) y resolución en efectivo de fracciones, que siguen sin adaptador.

## 3. Lo construido después de la ronda (para la ronda 8)

No formaba parte de la ronda 7 y no ha sido revisado por Astra:

- `twlab/sources/twse.py` y `twlab/sources/finmind.py`: lectura tipada de censos, retiradas, catálogo, barras nominales y dividendos desde el archivo.
- `twlab/calendar.py`: `classify_holiday_row_en`, `from_twse_legacy_rows` y `load_twse_reference_calendar` (calendario oficial 2021-2026 desde el endpoint heredado en inglés, capturas en `data/reference/`). Discrepancias documentadas frente a `exchange_calendars` XTAI: cierres extraordinarios por tifón ausentes de la lista anual oficial (2023-08-03, 2024-07-24/25, 2024-10-02/03) y días de sólo liquidación que la lista oficial marca como cierre (2021-02-05, 2022-02-04, 2023-01-18).
- `scripts/build_master.py` → `docs/informes/10_censo_2026-09-09.md` y `data/store/master_2026-09-09.jsonl` (2.348 segmentos; universo simulable por defecto 1.973). Un símbolo reutilizado detectado en datos reales (`TWSE:2432`, retirada 2008 de un emisor anterior, alta vigente 2023): no se cierra el segmento vigente, se informa.
- `scripts/fetch_history_sample.py`: muestra estratificada (2 valores por industria, cotizados antes de 2020-06-30, más 3 retiradas 2024-2025) con barras 2021-2025 y dividendos 2020-2025 archivados con `ingested_at` real.
- `scripts/run_q0_demo.py` → `docs/informes/11_demo_q0_2024-2025.md`: recorrido semanal completo (paquete por corte, predicción Q0 validada, archivo del paquete y del sobre, cesta de cinco puestos, comparador aleatorio emparejado, referencia equiponderada, bootstrap por bloques) con todas sus salvedades declaradas.
- Dos cambios del motor que la demo hizo necesarios, numerados para la ronda 8:
  - **C-08-01** (`evaluation.py`): el bootstrap por bloques muestrea dentro de tramos de semanas consecutivas y ningún bloque cruza una semana inválida o ausente. Antes, cualquier hueco (la semana de Año Nuevo Lunar, `invalid:no_sessions`, aparece todos los años) impedía evaluar con `block_length > 1`; ahora el principio de R02-08 («los bloques no unen semanas no consecutivas») se conserva y el resultado informa `n_segments`. Sin huecos el muestreo es idéntico al anterior con la misma semilla. Pruebas: `test_r02_08_daily_rows_are_not_weeks_and_blocks_do_not_bridge_gaps` (actualizada), `test_c08_01_blocks_are_sampled_inside_contiguous_segments_only`.
  - **C-08-02** (`evaluation.py`): `paired_excess(..., exposure_tolerance=0)` admite una tolerancia de exposición **declarada** (por defecto cero, igualdad exacta). El redondeo a lotes enteros hace que dos carteras del mismo tamaño nunca tengan exactamente la misma exposición (en la demo, mediana de la diferencia 2,5 puntos, máximo 12); sin tolerancia SIM-12 no empareja casi ninguna semana. La tolerancia es un valor del protocolo por congelar. Prueba: `test_c08_02_paired_excess_exposure_tolerance_is_declared_not_inferred`.

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161 (`twlab/seals.py`); el registro de producción sigue vacío.
- Catálogo de extractores reales y prueba original/corrección sobre capturas (noticias, anuncios MOPS).
- Adaptador de lotes menores (零股) y resolución en efectivo de fracciones.
- Maestro histórico completo: 263 retiradas TWSE sin fecha de alta (TEJ o histórico de FinMind).
- Módulo de informe estadístico STA-02/03/05/06/07.
- Congelamiento del protocolo: regla de dimensionado de puestos (fijo con colchón de efectivo o proporcional), regla de liquidez/capacidad, `block_length`, deslizamiento central, redondeo de efectivo, plazo de registro de semanas sin sesiones. Decisión del usuario; la demo usa valores declarados como provisionales.
