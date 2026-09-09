# Respuesta del constructor a la ronda 4 de revisión (GPT-6 Astra)

> **Nota de vigencia (R05-12):** las descripciones de API y garantías de este informe corresponden a la ronda en que se escribió y fueron sustituidas o precisadas por rondas posteriores (`WeeklyObservation.sealed` → `seal_capture_id` + `store`; `sealed_receipts` → sello recalculado desde `RawStore` con registro fijo en `twlab.seals`; atribución proporcional → lotes con propietario). El estado vigente es el del informe de respuesta más reciente.

**Entrada:** `review/out/ronda4_verificacion_20260909T190848Z.json` (sha256 `18a39240…650a3`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Verificó las 17 correcciones de la ronda 3 (13 completas, 4 parciales: R03-04, R03-06, R03-08, R03-10) y produjo 14 hallazgos nuevos (R04-01..R04-14). Rechazó de nuevo P2: el bloqueo prospectivo dependía de booleanos y objetos que el llamante podía fabricar.

**Salida:** todas las pruebas en verde (recuento en `README.md`). Tres cambios de diseño, no parches:

1. **Contabilidad por lotes con propietario** (R04-09/10/11, cierra también R03-10): cada compra crea un `Lot(owner, quantity, cost)`; las acciones corporativas escalan cada lote; una venta con `owner` consume sólo sus lotes; los dividendos se declaran lote a lote. Una cesta vende exactamente lo que compró, su residuo es el suyo y su rentabilidad bruta incluye sus dividendos declarados.
2. **Sello sobre la serialización canónica de la predicción más el hash del paquete** (R04-01/02/03/04): `sealed_forecast_bytes(obj, packet)` es lo que se archiva y sella; el validador ya no acepta `seals` del llamante, recibe el `RawStore`, recalcula el sello con `not_after = deadline` y exige que el digest sea exactamente el de la predicción que está validando con ese paquete. La evaluación hace lo mismo: `WeeklyObservation.seal_capture_id` + `store`, sin booleanos.
3. **Corte semanal estricto** (R04-05/06): `plan_week` exige domingo 18:00 Asia/Taipei (`ProtocolViolation` en cualquier otro caso); la entrada es la primera apertura estrictamente posterior al plazo; una semana sin sesiones se registra `invalid` con `deadline_at == cutoff_at` (ventana nula), sin plazo ficticio (R04-13).

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R04-01 | bloq. | Sin parámetro `seals`; sólo `store: RawStore` (comprobado con `isinstance`); el sello se recalcula. En evaluación, `seal_capture_id` + `store`. | `test_r04_01_seals_cannot_be_supplied_by_the_caller`, `test_r04_01_prospective_evaluation_recomputes_seals_from_the_archive` |
| R04-02 | bloq. | El digest sellado cubre toda la predicción (sin el campo del recibo); cambiar ranking o `forecast_id` invalida. | `test_r02_07_r03_04_r04_02_r04_03_seal_covers_forecast_and_packet` |
| R04-03 | bloq. | `packet_hash` va dentro de los bytes sellados, no en metadatos mutables. | ídem |
| R04-04 | alta | `store.seals(not_after=deadline)` siempre: acreditación o archivo posteriores al plazo → no sellado. | `test_r04_04_attestation_after_deadline_is_rejected` |
| R04-05 | alta | Corte distinto de domingo 18:00 Taipei → `ProtocolViolation`; el comparador diario tendrá su propio plan cuando se registre. | `test_r04_05_*` (weekly y packet) |
| R04-06 | alta | Entrada = primera apertura estrictamente posterior al plazo; sin ninguna → `invalid:no_sessions`. | `test_r04_06_entry_is_the_first_open_after_the_deadline` |
| R04-07 | media | Comparación por bytes canónicos JSON (`true` ≠ `1`). | `test_r04_07_json_identity_distinguishes_true_from_1` |
| R04-08 | alta | Un vencimiento conocido tarde se abona en el instante del conocimiento; la fecha contractual queda en el detalle. | `test_r04_08_late_known_payment_date_never_backdates_cash` |
| R04-09 | alta | Reintento de una cesta vende sólo sus lotes. | `test_r04_09_blocked_basket_retry_sells_only_its_own_lots` |
| R04-10 | media | Residuo = cantidad del propietario tras vender. | `test_r04_10_residual_follows_the_owner_not_a_proportion` |
| R04-11 | alta | `Slot.dividends_declared` (por propietario) en la rentabilidad bruta de la selección. | `test_r04_11_cash_dividends_belong_to_the_gross_total_pick_return` |
| R04-12 | alta | Misma clave `(security_id, valid_from, recorded_at)` con contenido distinto → error; una revisión exige `recorded_at` posterior. | `test_r04_12_same_key_cannot_rewrite_known_history` |
| R04-13 | media | Semana inválida: `deadline_at == cutoff_at`, sin plazo inventado; el esquema del contrato no se modifica. Candidato a enmienda de protocolo (T2). | `test_r03_03_r04_13_week_without_sessions_records_invalid_with_null_window` |
| R04-14 | alta | El extractor devuelve `payload` **y** `security_ids`; ambos deben coincidir con el documento. | `test_r04_14_security_identity_must_come_from_the_extraction` |

## 2. Respuestas a las preguntas del revisor

1. **Sobre canónico acreditado.** `sealed_forecast_bytes` = JSON canónico de `{"forecast": <predicción sin el campo del recibo>, "packet_hash": <hash del paquete>}`; el hash del paquete cubre corte, plan semanal, versión del calendario y manifiesto documental. Un `SealInfo` fabricado no tiene entrada: el validador y la evaluación sólo aceptan un `RawStore` real.
2. **Corte intermedio.** Rechazado por el experimento semanal (`ProtocolViolation`). Un comparador diario será otro experimento, con su propio plan y versión de protocolo, y no sustituirá semanas perdidas.
3. **Registro de cantidades y flujos por selección.** Lotes con propietario en el libro (`Position.lots`, `owner_quantity`, `declared_dividends`), consumidos FIFO dentro del propietario; las ventas parciales reducen la base del lote proporcionalmente; los dividendos se declaran por lote y se cobran por lote.

## 3. Sobre P2

La vía prospectiva sigue bloqueada de fábrica y ahora también para los consumidores: sin `RawStore` con verificador de producción registrado no hay sello; sin sello cuyo digest sea el de la predicción validada con su paquete, no hay evidencia prospectiva; sin sello recalculado desde el archivo, no hay evaluación prospectiva. Las pruebas ejercitan la cadena con un verificador de prueba registrado bajo una autoridad de producción y un calendario sintético de 2030 para que el plazo quede en el futuro con reloj real; el adaptador criptográfico real sigue pendiente y así lo dicen los informes.

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161.
- Catálogo de extractores reales (payload + identidades) y prueba original/corrección sobre capturas.
- Adaptador de lotes menores (零股).
- Módulo de informe estadístico STA-02/03/05/06/07.
- Congelamiento del protocolo (T2 y valores pendientes): decisión del usuario.
