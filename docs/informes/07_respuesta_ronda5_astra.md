# Respuesta del constructor a la ronda 5 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda5_verificacion_20260909T192520Z.json` (sha256 `912410bd…4fdfc`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Confirmó las 14 correcciones de la ronda 4 y produjo 12 hallazgos nuevos (R05-01..R05-12). Volvió a rechazar P2: la confianza dependía del `RawStore` que construye el llamante.

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada R05 tiene prueba nombrada.

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R05-01 | bloq. | La confianza ya no la configura el llamante: `twlab/seals.py` es el registro fijo de verificadores de producción (`opentimestamps`, `rfc3161`) y está **vacío** hasta que existan los adaptadores; `RawStore.register_verifier` rechaza esas autoridades (`UntrustedVerifier`); los verificadores inyectados sólo pueden ser de prueba y sus sellos sólo cuentan con `allow_test_authorities=True`, un parámetro explícito de prueba en el validador y en la evaluación. | `test_r05_01_production_verifiers_cannot_be_injected_and_registry_is_empty`, `test_r04_01_r05_01_*` |
| R05-02 | bloq. | La evaluación lee los bytes archivados de cada corrida válida (predicción canónica), recalcula el sello, y exige que `forecast_id`, la semana derivada del corte y la clase de evidencia coincidan con la observación; una captura no puede acreditar dos semanas. | `test_r04_01_r05_02_r05_03_r05_10_*` |
| R05-03 | alta | La evaluación recalcula el sello con `not_after` = plazo leído de la predicción archivada. | ídem |
| R05-04 | alta | `packet_hash` cubre también los rechazos (id, motivo, detalle); `created_at` queda fuera por ser metadato de construcción. | `test_r05_04_rejections_visible_to_the_predictor_are_inside_the_seal` |
| R05-05 | alta | Una cesta se entra una sola vez por libro: `enter_basket` rechaza propietarios ya vistos (`owners_seen`). | `test_r05_05_a_basket_is_entered_once_per_ledger` |
| R05-06 | alta | `owner_sale_gross` acumula el valor de referencia (precio × acciones, sin redondear) de todas las ventas del propietario; la rentabilidad bruta lo usa junto al residuo y los dividendos. | `test_r05_06_partial_sales_by_the_owner_count_in_the_pick_return` |
| R05-07 | media | `unresolved_fraction` suma las fracciones de cada lote; no se cancelan entre propietarios. | `test_r05_07_fractions_of_different_owners_do_not_cancel_out` |
| R05-08 | media | Dividendo calculado por propietario (suma de sus lotes), no por lote de adquisición. | `test_r05_08_dividend_cash_does_not_depend_on_how_the_purchase_was_split` |
| R05-09 | alta | `WeekPlan.registration_deadline_at`: plazo de emisión en semanas válidas; fin de la semana natural objetivo (domingo 24:00 Taipei) en semanas sin sesiones. El validador usa ese plazo para el sello. | `test_r05_09_invalid_week_prospective_run_can_be_registered_after_the_cutoff` |
| R05-10 | alta | Las corridas inválidas sin predicción se cuentan como excluidas sin exigirles sello. | `test_r04_01_r05_02_r05_03_r05_10_*` |
| R05-11 | alta | El validador comprueba el plan del paquete: corte de domingo 18:00 Taipei, `week_status` reconocido, plazo a las 08:30, entrada > plazo, salida > entrada; con `calendar` re-deriva el plan y exige igualdad. | `test_r05_11_validator_does_not_trust_a_caller_built_packet_plan` |
| R05-12 | media | Informes 03-06 llevan nota de vigencia; las afirmaciones sustituidas remiten al informe más reciente. Este informe no afirma bloqueo «efectivo» más allá de lo probado: sin adaptador criptográfico no hay sello de producción (registro vacío) y los sellos de prueba requieren la bandera explícita. | — |

## 2. Respuestas a las preguntas del revisor

1. **Configuración de confianza.** `twlab.seals.PRODUCTION_VERIFIERS`, en código versionado, vacío hasta implementar y probar OpenTimestamps y RFC 3161. Ningún `RawStore` puede registrar esas autoridades; las de prueba quedan fuera del protocolo salvo `allow_test_authorities=True`, que es una declaración explícita de modo de prueba.
2. **Resolución desde la predicción archivada.** Los bytes sellados son JSON canónico `{"forecast": …, "packet_hash": …}`; el evaluador los lee, obtiene `forecast_id`, `cutoff_at` (→ semana ISO) y `deadline_at` (→ `not_after`), y los compara con la observación. Las corridas inválidas sin predicción no tienen archivo y se cuentan como excluidas.
3. **Identidad de cesta y flujos por propietario.** `owner = "<week_id>:<rank>"`, único por libro (`owners_seen`); por propietario se acumulan cantidad (lotes), ventas brutas de referencia y dividendos declarados; los reintentos venden sólo los lotes propios; el redondeo a TWD no afecta a la atribución.

## 3. Estado de P1, P2, P3

- **P1:** cumplida la condición de tipos e identidades derivadas (R04-07/14) y contenido visible del paquete dentro del sello (R05-04). Pendiente: catálogo de extractores reales.
- **P2:** la afirmación exacta ahora es: *no existe ningún verificador de producción en el código; por tanto ningún registro puede sellarse para el protocolo y ninguna predicción puede ser `prospective_registered`; los sellos de prueba sólo entran con una bandera explícita de prueba*. No se afirma más que eso.
- **P3:** colisiones de propietario, ventas parciales, fracciones, redondeo y registro de semanas inválidas resueltos con prueba.

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161 (`twlab/seals.py`).
- Catálogo de extractores reales y prueba original/corrección sobre capturas.
- Adaptador de lotes menores (零股).
- Módulo de informe estadístico STA-02/03/05/06/07.
- Congelamiento del protocolo (T2, plazo de registro de semanas sin sesiones y valores pendientes): decisión del usuario.
