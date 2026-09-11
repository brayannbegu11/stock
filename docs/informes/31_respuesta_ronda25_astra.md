# Respuesta del constructor a la ronda 25 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda25_verificacion_20260911T164018Z.json`, árbol congelado e íntegro. Veredicto de Astra: **rechazado** (6 hallazgos nuevos: 1 alto, 4 medios, 1 bajo; todos reproducidos). Verificó las seis correcciones de la ronda 24 (R24-01..R24-06, todas reproducidas), confirmó que ninguna excepción escapa de `classify_week` en 42 casos malformados, que los informes 15/15b/15c coinciden con sus JSON y que la adaptación indicada en el informe 30 §4 es correcta. Encontró que la caché de veredictos del exportador podía acreditar un paquete o una captura corrompidos después de la primera clasificación, que el Runner no re-verificaba la instantánea del maestro entre semanas de una misma corrida, que no se acreditaba el orden maestro→predicciones prometido, que las filas con `kind` inválido se ignoraban, que sólo se comprobaba la primera identidad de cada serie y que el ensamblador ocultaba motivos simultáneos. Todo se corrige aquí; las pruebas nuevas llevan el identificador del hallazgo en el nombre.

## 1. Correcciones por hallazgo

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R25-01 | alta | Sin caché de veredictos: `inputs_before_cutoff` vuelve a comprobar en **cada** llamada la integridad del paquete (sha256 de los bytes leídos contra el registro) y de cada captura referenciada; sólo se conserva la deserialización del paquete, indexada por el sha256 de los bytes realmente leídos. El exportador completo tarda unos 3 s. | `test_r25_01_repeated_classification_rechecks_integrity` (paquete y captura fuente) |
| R25-02 | media | `Runner.master_record` verifica la integridad de la instantánea en cada semana: si la copia citada se corrompe a mitad de corrida, reutiliza la primera copia íntegra de los mismos bytes en el dataset del maestro o archiva una nueva **antes** de emitir las predicciones de esa semana, que la citan. | `test_r25_02_master_snapshot_corrupted_between_weeks_is_rearchived_before_use` |
| R25-03 | media | La primera ingestión íntegra del maestro debe ser anterior o igual a la primera ingestión íntegra de **cada** predicción (`master_after_forecast:<f>`), además de anterior o igual al plazo (`master_late:<f>`). | `test_r25_03_master_first_intact_copy_must_precede_every_forecast` |
| R25-04 | media | Toda fila de la instantánea debe ser un segmento bien formado: `kind` distinto de `"segment"` (nulo, lista, objeto, número, otra cadena) invalida la instantánea (`master_contract:ValueError`); ya no se omite nada. | `test_r25_04_master_rows_that_are_not_segments_invalidate_the_snapshot` (7 casos) |
| R25-05 | media | Cada serie de barras del paquete debe declarar exactamente una identidad (`packet_series_identity:<doc_id>` si no), y esa identidad se contrasta con el maestro conocido al corte. | `test_r25_05_every_identity_declared_by_a_series_is_checked` |
| R25-06 | baja | La frase del ensamblador para «datos tardíos» incluye la lista completa de motivos (por ejemplo `master_link_mismatch:Q0, late_inputs`). | `test_r25_06_assembler_keeps_every_reason_when_inputs_are_late` |

Control positivo: la semana real de `_real_week_fixture` sigue siendo predicción; clasificarla dos veces seguidas sigue dando el mismo veredicto mientras nada se corrompa.

## 2. Cambios de plan evaluados por Astra

P1 y P9 rechazados por R25-01 (integridad heredada de la caché) y por la reutilización del maestro dentro de una corrida y la coherencia de identidades: corregidos arriba. P2 y P6 con condiciones, atendidas (garantías de README y de los informes 29 §6 y 30 acotadas en el informe 30 §6; ensamblador corregido). El paquete sigue construido en modo histórico y sin sello externo, y así se declara.

## 3. Efecto sobre lo publicado

Ninguna semana existente cambia de clase (todas eran reconstrucciones por plazo). El exportador ya no cachea veredictos; `docs/site/data.json` se regenera en unos 3 s.

## 4. Compatibilidad con las baterías de Astra

Con este código pasan enteras `review/out/astra_scratch/test_r23.py` y `test_r25.py` salvo `test_corruption_between_weeks_same_runner`, cuyo comentario final admite dos salidas válidas («detenerse antes de emitir predicciones, o reparar y citar una instantánea íntegra») pero cuya aserción sólo contempla la antigua conducta (`master_corrupt`): el Runner ahora repara y cita una copia íntegra archivada antes de las predicciones de esa semana, de modo que 2024-W03 queda como predicción según el reloj del fixture; la última línea de esa prueba (`raw.read` de la copia citada) sí se cumple. De `test_r24.py` sigue obsoleto `test_master_effective_view[past_revision]` (informe 30 §4).

## 5. Pendientes que siguen abiertos

Readmisión verificada en modo prospectivo (extractor multicaptura) y construcción del paquete en ese modo; sello externo de fecha; dividendos del universo completo; política de cierres sobrevenidos; adaptador oficial de lotes sueltos. Los bloqueantes que dependen del usuario no cambian (informe 21 §4).

## 6. Fe de erratas (tras la ronda 26)

Tres afirmaciones de este informe (y las equivalentes del README) excedían lo que el código acreditaba, como señaló Astra en la ronda 26: (1) «la integridad se vuelve a comprobar en cada llamada» valía para los bytes, pero el índice del archivo (`manifest.jsonl`) se leía una sola vez por proceso (R26-01); (2) el Runner «archiva el maestro antes que las predicciones», pero congelaba la primera instantánea aunque el maestro cambiara durante la corrida (R26-02) y sólo recuperaba copias corruptas, no ausentes (R26-03); (3) la «primera copia íntegra» podía ser desplazada por una copia corrupta anterior con reloj inyectado (R26-04). Todo queda corregido en el informe 32.

