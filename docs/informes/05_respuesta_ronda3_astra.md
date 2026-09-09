# Respuesta del constructor a la ronda 3 de revisión (GPT-6 Astra)

> **Nota de vigencia (R05-12):** las descripciones de API y garantías de este informe corresponden a la ronda en que se escribió y fueron sustituidas o precisadas por rondas posteriores (`WeeklyObservation.sealed` → `seal_capture_id` + `store`; `sealed_receipts` → sello recalculado desde `RawStore` con registro fijo en `twlab.seals`; atribución proporcional → lotes con propietario). El estado vigente es el del informe de respuesta más reciente.

**Entrada:** `review/out/ronda3_verificacion_20260909T184924Z.json` (sha256 `74a66bc6…c8053`), esfuerzo `high`, árbol congelado e íntegro durante la ronda. Veredicto de Astra: **rechazado**. Verificó las 21 correcciones de la ronda 2 (14 completas, 7 parciales) y produjo 17 hallazgos nuevos (R03-01..R03-17), todos reproducidos. Rechazó mi respuesta P2 y aceptó con condiciones P1 y P3.

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada R03 tiene prueba nombrada. Además, la nueva prueba de sello ligado a la predicción destapó un defecto que Astra no había señalado: `plan_week` ponía el plazo en la primera sesión de la semana aunque ya hubiera pasado para un corte a mitad de semana; corregido con prueba (`test_midweek_cutoff_never_gets_a_deadline_in_the_past`).

## 1. Hallazgos y acción tomada

| Id | Sev. | Qué estaba mal | Corrección | Prueba |
|---|---|---|---|---|
| R03-01 | bloq. | Fuente y hash declarados no ligaban el contenido a los bytes; `verified_version` sin extractor. | Registro de extractores (`derivation`). En prospectivo el paquete relee los bytes archivados, comprueba su sha256, aplica el extractor registrado y exige que el resultado sea **idéntico** al `payload`. Sin extractor registrado, sin documento. | `test_r03_01_payload_must_be_reproducible_from_archived_bytes` |
| R03-02 | bloq. | El plazo seguía siendo un argumento libre del paquete; sin paquete no había comprobación. | `build_packet` ya no acepta `deadline_at`: recibe el calendario y deriva `week_id`, `week_status`, `deadline_at`, `entry_at`, `exit_at` con `weekly.plan_week`. Una predicción `selected` sin paquete es inválida (`packet_required_for_selected_forecast`). | `test_r02_06_r03_02_*`, `test_r01_18_r02_06_r03_02_*` |
| R03-03 | alta | `weekly_deadline` saltaba a la semana siguiente si la semana objetivo no tenía sesiones. | `plan_week` devuelve `invalid:no_sessions` con plazo, entrada y salida nulos; `weekly_deadline` lanza `NoSessionsInWeek`; el validador sólo admite `status=invalid` para esa semana. | `test_r03_03_*` (weekly y schema) |
| R03-04 | bloq. | Un identificador de recibo cualquiera del archivo validaba cualquier predicción. | `RawStore.seals()` devuelve `SealInfo` (digest, captura, instante, `packet_hash` de la captura, autoridad). El validador exige `raw_response_hash == seal.digest`, `capture_extra.packet_hash == packet.packet_hash()` y captura archivada antes del plazo. | `test_r02_07_r03_04_*` |
| R03-05 | alta | `is_sealed` no comprobaba los bytes archivados. | `seal_info` exige `intact(rec)` (relectura y sha256). | `test_r03_05_*` |
| R03-06 | alta | `not_after` no limitaba la fecha de archivo. | `not_after` aplica a `attested_at` **y** a `ingested_at`. | `test_r03_06_*` |
| R03-07 | alta | Solapes posibles en vistas históricas intermedias. | `_check_no_overlap` recorre todas las vistas en las que la fila nueva es visible (cada instante de registro del emisor desde `recorded_at` de la fila nueva, y la actual). | `test_r03_07_*` |
| R03-08 | alta | `set_payment_date` fechaba el asiento en la declaración. | Nuevo parámetro `at` (instante en que se conoció la fecha); avanza el reloj y se asienta entonces. | `test_r03_08_*` |
| R03-09 | alta | `valuation` aceptaba fechas anteriores al reloj del libro. | Se rechaza (`LedgerError`): una valoración histórica exige reproducir el libro hasta ese instante. | `test_r03_09_*` |
| R03-10 | alta | Residuo de semanas anteriores atribuido a la entrada nueva. | `Slot.pre_entry_quantity`; la parte atribuible al puesto es la proporción de su entrada sobre la cantidad total al entrar; `gross_pick_return` se calcula sobre esa parte. | `test_r03_10_*`, `test_r02_04_*` |
| R03-11 | media | Horarios por sesión con alias mutables. | Se normalizan a tuplas de `time` validadas y se guardan en `MappingProxyType`. | `test_r03_11_*` |
| R03-12 | alta | Negaciones incompletas (取消放假). | Cualquier marcador precedido de 不/未/取消/非/無, o «取消» en el texto → `unknown`. | `test_row_classification` |
| R03-13 | media | `experiment_id` no string interrumpía el validador. | Comprobación de tipo. | `test_experiment_registry_*`, `test_r02_20_r03_13_*` |
| R03-14 | media | Valores no finitos en el bootstrap. | `ObservationError` para NaN, ±inf, bool o no numérico. | `test_r03_14_*` |
| R03-15 | media | Cobro vencido en el mismo instante no se abonaba. | `_settle` tras registrar el cobro. | `test_r03_15_*` |
| R03-16 | alta | `change_segment` prolongaba un segmento ya cerrado. | Sólo opera sobre segmento abierto o que cierra exactamente donde empieza el nuevo; tras un hueco se usa `add()`. | `test_r03_16_*` |
| R03-17 | media | `CalibratorRecord` sin validación. | Tipos validados en `__post_init__`; registro con objetos que no sean `CalibratorRecord` → problema. | `test_r01_22_r02_09_r03_17_*` |
| R02-21 (parcial) | media | Afirmaciones documentales excesivas. | `derivation` ahora es obligatorio en prospectivo; el plazo es derivado; existe `plan_week` con `invalid:no_sessions` probado; los recuentos se toman del recolector de pytest; «vistas históricas» y «sólo el archivo produce los sellos» corregidos en 03/04. | — |

## 2. Posiciones sobre P1, P2, P3

- **P1 (acepto con condiciones):** cumplida la condición: sin extractor registrado no hay documento prospectivo y el payload debe reproducirse desde los bytes. Lo que sigue pendiente es el catálogo de extractores reales para TWSE/TPEx/FinMind; hasta entonces el único extractor registrado en pruebas es `json.loads`.
- **P2 (rechazo de Astra, aceptado):** la vía prospectiva queda **bloqueada de fábrica**: `RawStore.seals()` sólo devuelve sellos de autoridades de producción (`opentimestamps`, `rfc3161`) y no existe verificador registrado para ellas en el repositorio; el validador exige ese sello ligado a `raw_response_hash` y al `packet_hash`. Hasta que exista el adaptador criptográfico, ninguna predicción puede ser `prospective_registered`. Las pruebas usan un verificador de prueba registrado bajo una autoridad de producción para ejercitar la cadena, y una autoridad de prueba para demostrar la exclusión.
- **P3 (acepto con condiciones):** fecha de conocimiento del pago (`at`), coherencia efectivo/valoración (R03-09/15), residuos separados por selección (R03-10) y flujo semanal `invalid:no_sessions` probado en `test_weekly.py` y `test_r03_03_*`.

## 3. Abierto tras esta ronda

- Adaptadores criptográficos OpenTimestamps / RFC 3161 (condición de A10 y P2).
- Catálogo de extractores reales y prueba original/corrección sobre capturas.
- Adaptador de lotes menores (零股) para resolver residuos y fracciones.
- Módulo de informe estadístico STA-02/03/05/06/07.
- Congelamiento de T2 y demás valores del protocolo (decisión del usuario).
