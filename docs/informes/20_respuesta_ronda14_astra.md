# Respuesta del constructor a la ronda 14 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda14_verificacion_20260909T232124Z.json` (sha256 `31280681…4b8d`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Verificó las correcciones de la ronda 13 (R12-02, R13-02, R13-03, R13-04, R13-06, R13-08 completas; R09-03, R12-01, R13-01, R13-05, R13-07 parciales) y produjo 8 hallazgos nuevos (R14-01..R14-08: 5 altos, 3 medios).

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada hallazgo tiene prueba nombrada. Las cifras de la muestra y de la demo no cambian.

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R14-01 | alta | `Document` tipa todos sus campos: `version` entero positivo, `capture_id` identificador de captura, `source_sha256` 64 hexadecimales, `security_ids` identificadores (además de `kind`, `supersedes`, `source_id`, `derivation` de la ronda 13). Los tipos de documento «open», «close» y «adjusted» salen del catálogo (eran restos de pruebas, no contratos). Ya no queda ningún campo de texto libre fuera del `payload`. | `test_r14_01_r14_02_document_fields_are_typed_and_historical_payloads_are_verified_when_evidence_exists` |
| R14-02 | alta | En modo histórico, si el constructor (o la readmisión) recibe archivo y registro de extractores y el documento declara su derivación, el `payload` se re-deriva de los bytes fuente igual que en prospectivo; la discrepancia se rechaza. Sin registro, el documento histórico queda **declarado como no verificado** (el README lo dice así; la garantía general se limita al modo prospectivo). | ídem |
| R14-03 | alta | La incertidumbre de un derecho ambiguo es **permanente**: se registra como reclamación (`Runner.ambiguous_claims`) y marca toda valoración posterior del libro (`ambiguous_right:<evento>`), con o sin la posición, hasta el final del recorrido; los intervalos de las semanas siguientes no son medibles y la valoración final lo declara. | `test_r14_03_r14_05_r14_08_ambiguity_survives_liquidation_and_voids_gross_returns` |
| R14-04 | alta | Las cantidades de los lotes se llevan como **racionales exactos** (`Lot.exact`, `fractions.Fraction`); el Decimal se deriva de ellos y es entero exacto cuando la fracción lo es. Encadenar 4/3 y 18/3 sobre 1.000 acciones da 8.000 exactas y vendibles; una fracción real sigue siendo fracción. | `test_r14_04_chained_periodic_ratios_stay_exact` |
| R14-05 | alta | Una selección con derecho ambiguo no tiene rentabilidad bruta (`gross_return = null`) y la media bruta de esa cesta es `null`; la media del recorrido sólo agrega semanas limpias. | ídem R14-03 |
| R14-06 | media | `TabularForecaster` comprueba en cada corte que `MarketData.data_version` es el de su construcción; si el mercado cambió por debajo, `ValueError`: no se reutilizan filas de otra versión de datos. | `test_r14_06_forecaster_refuses_a_market_that_changed_underneath` |
| R14-07 | media | El hash de filas del `training_manifest_id` incluye `label_known_at`. | `test_r14_07_r14_08_manifest_covers_label_availability_and_exact_form_derives_the_ratio` |
| R14-08 | media | `DividendLike` deriva `stock_ratio` de la forma exacta (y rechaza un valor que la contradiga); `Runner` pasa al libro sólo la forma exacta cuando existe. Etiqueta y libro no pueden divergir por ese campo. | ídem; sin `action_errors` en el recorrido de R14-03 |
| R09-03 / R13-01 (parciales) | alta | Absorbidos por R14-01. | — |
| R12-01 / R13-05 / R13-07 (parciales) | alta | Absorbidos por R14-03, R14-04, R14-05 y R14-08. | — |

## 2. Posiciones de Astra sobre P1..P5

- **P1 (rechazo).** Aceptado: `version`, `capture_id`, `source_sha256` y `security_ids` eran vías, y el histórico no verificaba payloads aunque hubiera evidencia. Cerradas ambas (R14-01, R14-02).
- **P2 (acepto con condiciones).** Mantenido.
- **P3 (rechazo).** Aceptado: incertidumbre permanente (R14-03), medias brutas invalidadas (R14-05), racionales exactos (R14-04).
- **P4 (acepto con condiciones).** Condición atendida: los derechos ambiguos se conservan tras liquidar (R14-03).
- **P5 (rechazo).** Aceptado: mercado inmutable durante la vida del pronosticador (R14-06), disponibilidad en el manifiesto (R14-07), forma exacta coherente entre etiqueta y libro (R14-08).

## 3. Respuestas a las preguntas del revisor

1. **«open», «close», «adjusted».** No había contrato que los justificara: eran restos de pruebas. Retirados del catálogo.
2. **Inmutabilidad de `MarketData`.** Sí: un pronosticador está ligado a una versión de datos y rehúsa continuar si cambia (R14-06). No se reutilizan filas de otra captura.
3. **Nota de vigencia en el informe 18.** Añadida.

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161; registro de producción vacío.
- Catálogo de extractores reales (con él, el histórico también se verifica documento a documento); pronosticadores con LLM (L1/L2).
- Política de cierres sobrevenidos y su fuente oficial; versiones históricas del calendario y de los derechos.
- Adaptador de lotes menores; maestro histórico completo; emisor con TEJ.
- Fuente oficial por fecha para precios del universo (`MI_INDEX`, `dailyQuotes`): descarga en curso; sin dividendos históricos por esa vía.
- Congelamiento del protocolo (costes y rotación, dimensionado, tolerancia de exposición, `block_length`, liquidez, tablero de innovación). Decisión del usuario.
