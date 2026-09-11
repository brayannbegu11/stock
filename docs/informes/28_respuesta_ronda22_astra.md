# Respuesta del constructor a la ronda 22 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda22_verificacion_20260911T153131Z.json`, árbol congelado e íntegro. Veredicto de Astra: **rechazado** (5 hallazgos nuevos: 4 altos, 1 medio). Verificó las nueve correcciones de la ronda 21 y las parciales R19-01/R19-02 (todas reproducidas), confirmó que el ciclo dominical completo distingue los cuatro estados en ensamblador y sitio, y encontró cuatro vías más para un falso «predicción»: predicciones inválidas o incoherentes, hash lógico del paquete no recalculado, corte tomado del JSON de resultados y símbolo/nombre mostrados sin contrastar. Todo se corrige aquí; las pruebas nuevas llevan el identificador del hallazgo en el nombre y usan un paquete real del contrato (`build_packet`/`packet_to_json`).

## 1. Correcciones por hallazgo

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R22-01 | alta | Contrato de la predicción archivada: sólo `selected` con `ranking` no vacío, entradas con `security_id` y sin repetidos, o `abstained` con `ranking` vacío, son decisiones válidas (`forecast_contract:<f>:<status>` en caso contrario); además los campos `rank` deben declarar exactamente el orden del array (1..n), porque ese orden es el que se muestra y el que compra el Runner (`forecast_contract:<f>:rank_order` si no, prueba `test_r22_rank_fields_must_declare_the_array_order`); el `forecast_status` del JSON debe coincidir con el archivado (`status_mismatch`); los `picks` deben coincidir con el ranking (para la abstención, vacíos). | `test_r22_01_invalid_or_incoherent_forecasts_are_not_predictions` |
| R22-02 | alta | `inputs_before_cutoff` deserializa el paquete archivado con `packet_from_json` y **recalcula** `packet_hash()`; debe coincidir con el de la semana, con el campo declarado en el archivo y con el `extra` del registro. Payloads fabricados, `source_sha256` alterados, `rejected` añadidos o `packet_id` ausente fallan por contrato o por hash. | `test_r22_02_logical_packet_hash_is_recomputed_from_the_contract` |
| R22-03 | alta | El corte que manda es el del paquete archivado (`pk.cutoff_at`), que debe coincidir con el `cutoff_at` de la semana (`cutoff_mismatch`); cada predicción archivada debe declarar ese mismo corte. | `test_r22_03_cutoff_comes_from_the_archived_packet_and_forecasts` |
| R22-04 | media | Tipos malformados (campos no textuales en el registro, `admitted` o `session_captures` con formas incorrectas) producen `ok=False` con motivo (`packet_incomplete_record:<campo>`, `packet_contract:<excepción>`, `empty_capture_manifest`), no una excepción. | `test_r22_04_malformed_records_and_packets_fail_closed` |
| R22-05 | alta | El símbolo mostrado debe ser el `ticker_as_of` archivado en la predicción (`symbol_mismatch`) y el nombre, el que el **paquete archivado** lleva para ese valor (`payload.name` de la serie de barras, que el Runner incluye desde esta ronda; `name_mismatch` si difiere o falta). La clasificación completa está en `export_site_data.classify_week`, compartida por exportador y ensamblador. | `test_r22_05_displayed_symbol_and_name_must_match_archive_and_master` |

Control positivo: `test_r22_real_packet_and_valid_contract_is_a_prediction` construye una semana con paquete real (nombres incluidos), fuentes antes del corte y predicciones válidas antes del plazo, y obtiene `prospective=True`. Los paquetes archivados antes de esta ronda no llevan `payload.name`, por lo que ninguna semana anterior puede clasificarse como predicción por esa vía (ya eran reconstrucciones); el ciclo semanal reconstruirá los paquetes con el campo nuevo (nuevo `packet_hash`) en su primera ejecución.

## 2. Cambios de plan evaluados por Astra

P1–P8 aceptados con las condiciones atendidas. **P9** (rechazado por Astra en tres rondas seguidas porque el código no acreditaba lo prometido): con R22-01..R22-05 el código exige todo lo enunciado en el informe 26 §2 y además el contrato de la predicción, el hash lógico recalculado, el corte del paquete archivado y la identidad visible. El paquete sigue construido en modo histórico y sin sello externo, y así se declara.

## 3. Efecto sobre lo publicado

Ninguna semana existente cambia de clase. El README deja de citar un número de ronda fijo.

## 4. Pendientes que siguen abiertos

Readmisión verificada en modo prospectivo (extractor multicaptura) y construcción del paquete en ese modo; sello externo de fecha; dividendos del universo completo; política de cierres sobrevenidos; adaptador oficial de lotes sueltos. Los bloqueantes que dependen del usuario no cambian (informe 21 §4).

## 5. Compatibilidad con la batería de la ronda 22 (`review/out/astra_scratch/test_r22.py`)

Ejecutada contra este código, la batería pasa entera salvo `test_forecast_contract[rank_order]`, y ese caso no es un fallo del clasificador: la mutación copia la entrada de A, le cambia sólo el `security_id` a B y deja `ticker_as_of = "A"`, mientras que la lista mostrada dice `B`; el clasificador responde `symbol_mismatch:Q0`, que es exactamente la comprobación R22-05 pedida en esa misma ronda. Con `ticker_as_of = "B"` el caso seguiría sin ser predicción por el contrato de rangos (`rank` 2 en la primera posición). Los otros dos casos que fallaban con el código enviado a la ronda 22 (`test_sunday_full_chain_four_states[prediction|late|unknown]`) sí eran errores del constructor y quedan corregidos: `classify_week` leía `forecast_status` y las semanas exportadas llevan `status` (ahora acepta ambas formas, `test_r22_classify_week_accepts_exported_and_raw_week_shapes`); `twlab` no era importable cuando el exportador se ejecuta como script, sólo bajo pytest (`test_r22_exporter_imports_twlab_outside_pytest`); y la frase del ensamblador para «procedencia sin acreditar» había cambiado (`test_r22_assembler_names_unverified_provenance`).

## 6. Fe de erratas (tras la ronda 23)

Dos garantías de este informe estaban formuladas con más alcance del que el código de entonces acreditaba, como señaló Astra en la ronda 23: (1) en R22-04, «tipos malformados producen `ok=False`, no una excepción» valía sólo para los cuatro casos enumerados; el cierre general ante cualquier excepción y las guardas para otros registros malformados llegan con R23-02 (informe 29); (2) en R22-02, la coincidencia del hash lógico «con el `extra` del registro» era opcional en el código (se aceptaba la ausencia); es obligatoria desde R23-04 (informe 29). Además, la identidad económica de cada valor (código y símbolo vigentes en el maestro) no se comprobaba: R23-01 (informe 29).

