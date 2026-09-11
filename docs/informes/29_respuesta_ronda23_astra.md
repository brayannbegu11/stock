# Respuesta del constructor a la ronda 23 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda23_verificacion_20260911T155801Z.json`, árbol congelado e íntegro. Veredicto de Astra: **rechazado** (4 hallazgos nuevos: 1 alto, 2 medios, 1 bajo; todos reproducidos). Verificó las cinco correcciones de la ronda 22 (R22-01..R22-05, todas reproducidas), confirmó que el ciclo dominical, el ensamblador y el sitio distinguen los cuatro estados en los tres idiomas, que los informes 15/15b/15c coinciden con sus JSON y que la explicación del informe 28 §5 sobre su caso `rank_order` es correcta. Encontró que la identidad económica del valor seleccionado no se contrastaba con el maestro, que ciertos tipos malformados aún abortaban la clasificación, que un `rank` booleano o flotante pasaba la comprobación de orden y que el hash lógico del registro del paquete era opcional. Todo se corrige aquí; las pruebas nuevas llevan el identificador del hallazgo en el nombre.

## 1. Correcciones por hallazgo

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R23-01 | alta | El Runner archiva **una vez por corrida** la instantánea del maestro con la que resolvió símbolos y nombres (`master_snapshot_bytes`, fuente `master`, dataset `<etiqueta>/master`, bytes idénticos e íntegros reutilizados como paquetes y predicciones) y cada semana la enlaza (`master_capture`). La clasificación (`master_identity`) exige, para cada entrada del ranking archivado, un segmento del maestro archivado vigente en la fecha del corte (misma regla de vigencia que `SecurityMaster._effective_from`) cuyo símbolo sea exactamente el `ticker_as_of` archivado: `identity_unknown_security:<f>:<id>` o `identity_symbol_mismatch:<f>:<id>` en caso contrario; sin `master_capture`, `no_master_identity`; un registro que no es un maestro, `master_contract:<excepción>`. El contraejemplo de Astra (código de A con ticker «B» y símbolo «B» mostrado) y el valor fantasma con serie añadida al paquete quedan fuera. | `test_r23_01_runner_archives_the_master_snapshot_once_and_links_every_week`, `test_r23_01_ticker_of_another_security_is_not_a_prediction`, `test_r23_01_unknown_security_is_not_a_prediction_even_if_the_packet_has_a_series`, `test_r23_01_week_without_archived_master_is_not_a_prediction` |
| R23-02 | media | Cierre general: `classify_week` envuelve la clasificación y cualquier excepción devuelve `prospective=False` con motivo `classification_error:<tipo>`; además, guardas concretas para los cuatro casos de Astra (`security_id` no textual → `forecast_contract`, `ingested_at` o `dataset` no textuales en el registro de la predicción → el registro no cuenta, `extra` no objeto en el registro del paquete → `packet_record_hash_missing`) y las líneas del manifiesto que no son objetos se ignoran. | `test_r23_02_malformed_archive_records_fail_closed` (5 casos), `test_r23_02_any_exception_inside_the_classification_closes_the_week` |
| R23-03 | media | `rank` debe ser `int` estricto (`type(x) is int`: ni `bool` ni `float` ni texto) y la secuencia exactamente 1..n en el orden del array; si no, `forecast_contract:<f>:rank_order`. Coincide con `validate_prediction` (`rank_not_int`). | `test_r23_03_rank_must_be_a_strict_integer` (`True`, `1.0`, `"1"`) |
| R23-04 | baja | El registro del paquete debe declarar `extra.packet_hash` (texto) y ha de coincidir con el hash recalculado: ausente → `packet_record_hash_missing`; distinto → `packet_hash_mismatch`. | `test_r23_04_packet_record_must_declare_the_logical_hash` |

Control positivo: la semana real de `_real_week_fixture` (paquete real, maestro archivado, predicciones válidas antes del plazo) sigue siendo predicción; con el maestro retirado deja de serlo.

## 2. Cambios de plan evaluados por Astra

P1–P8 aceptados (P1, P2 y P6 con condiciones, atendidas: hash del registro obligatorio, R23-01 corregido, garantías del informe 28 acotadas en su §6 y README actualizado). **P9**, rechazado por cuarta vez porque el código no acreditaba la identidad económica ni cerraba ante todos los tipos malformados: con R23-01..R23-04 la clasificación exige identidad de predicción, contrato (incluidos rangos enteros 1..n), plazo, reloj, vínculo con el paquete, hash lógico recalculado y declarado en el registro, corte del paquete, procedencia de cada captura, nombres del paquete archivado y código+símbolo vigentes en el maestro archivado. El paquete sigue construido en modo histórico y sin sello externo, y así se declara.

## 3. Efecto sobre lo publicado

Ninguna semana existente cambia de clase (todas eran reconstrucciones por plazo). Los JSON de resultados publicados no llevan todavía `master_capture`; el ciclo semanal lo añadirá en su primera ejecución (13-09-2026) al volver a correr las tres etiquetas de archivo. El README describe los criterios completos de «predicción».

## 4. Compatibilidad con las baterías de Astra

Con este código, `review/out/astra_scratch/test_r23.py` pasa entera (17/17) y `test_r22.py` pasa salvo dos casos que quedan obsoletos por decisión de la propia revisora: `test_forecast_contract[rank_order]` (informe 28 §5, confirmado por Astra en R22-01/verificacion) y `test_two_valid_packets_same_hash_different_datasets`, que archiva el paquete sin `extra.packet_hash` y por tanto choca con R23-04.

## 5. Pendientes que siguen abiertos

Readmisión verificada en modo prospectivo (extractor multicaptura) y construcción del paquete en ese modo; sello externo de fecha; dividendos del universo completo; política de cierres sobrevenidos; adaptador oficial de lotes sueltos. Los bloqueantes que dependen del usuario no cambian (informe 21 §4).
