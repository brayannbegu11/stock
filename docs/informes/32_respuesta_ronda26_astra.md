# Respuesta del constructor a la ronda 26 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda26_verificacion_20260911T165910Z.json`, árbol congelado e íntegro. Veredicto de Astra: **rechazado** (4 hallazgos nuevos: 2 altos, 2 medios; todos reproducidos). Verificó las seis correcciones de la ronda 25 (R25-01..R25-06, todas reproducidas), confirmó que las cuatro clases y las razones nuevas aparecen en el sitio y en las cabeceras en los tres idiomas, que los informes 15/15b/15c coinciden con sus JSON y que la explicación del informe 31 §4 es correcta. Encontró que el índice del archivo se leía una sola vez por proceso, que el Runner congelaba la primera instantánea del maestro aunque el maestro cambiara durante la corrida, que la recuperación de copias sólo cubría la corrupción y no la ausencia (y que los errores del índice escapaban de `run_week`), y que una copia corrupta anterior con reloj inyectado desplazaba a la primera copia íntegra. Todo se corrige aquí; las pruebas nuevas llevan el identificador del hallazgo en el nombre.

## 1. Correcciones por hallazgo

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R26-01 | alta | `manifest()` calcula el sha256 de `manifest.jsonl` en cada llamada y vuelve a leer el índice cuando cambia: un registro alterado entre dos clasificaciones (reloj, hora, sha, ruta) se ve en la siguiente. | `test_r26_01_manifest_rewrites_are_seen_by_the_next_classification` (4 casos) |
| R26-02 | alta | `Runner.master_record` serializa la instantánea en **cada** semana: si el maestro en memoria cambia durante la corrida (cierre, revisión), la semana siguiente archiva y cita una instantánea nueva (sha distinto), que la clasificación usa con la vista conocida al corte. | `test_r26_02_master_changes_during_a_run_are_archived_and_cited` |
| R26-03 | media | Recuperación: una copia del maestro o de una predicción **ausente** se trata como una corrupta (se reutiliza otra copia íntegra o se vuelve a archivar antes de emitir). Contención: `run_week` delega en `_emit_week` y cualquier fallo del archivo (`ManifestInconsistent`, `IntegrityError`, `ManifestCorrupt`, `MissingCapture`, `OSError`) deja la semana registrada como `invalid:archive` con `archive_error`, sin predicciones ni evaluación, y la corrida continúa; el índice corrupto se señala con `ManifestCorrupt` (línea y causa) desde `RawStore`, y una captura ausente con `MissingCapture`. El paquete archivado corrupto o ausente sigue siendo un rechazo deliberado (`ManifestInconsistent`, R20-04), ahora contenido en su semana. `weeks_invalid_archive` en el resumen; estado traducido en el sitio. | `test_r26_03_missing_master_copy_falls_back_to_another_intact_copy`, `test_r26_03_missing_forecast_copy_is_rearchived`, `test_r26_03_archive_failures_are_contained_per_week` (4 casos), `test_r20_04_reused_packet_and_forecast_bytes_are_verified` (adaptada) |
| R26-04 | media | La «primera copia» es la primera **íntegra** (registro completo, hora utilizable y bytes que coinciden con el sha256), elegida sin mirar el reloj; su reloj se juzga después (`clock:injected` sólo si esa copia íntegra lo tiene). Una copia corrupta anterior, con cualquier reloj, ya no desplaza a la íntegra; una copia íntegra anterior con reloj inyectado sigue mandando (R21-05). | `test_r26_04_a_corrupt_earlier_copy_with_injected_clock_does_not_shadow_the_intact_one` (maestro y predicción) |

Control positivo: la semana real de `_real_week_fixture` sigue siendo predicción; el fixture dominical de Astra también, con la instantánea reutilizada entre corridas cuando no cambia.

## 2. Cambios de plan evaluados por Astra

P1 y P9 rechazados por R26-01 y R26-02 (índice y maestro obsoletos): corregidos arriba. P2, P5 y P6 con condiciones, atendidas (la inmutabilidad del mercado no se extiende al maestro: cada semana cita la instantánea vigente al emitir; garantías del README y del informe 31 acotadas en el informe 31 §6). El paquete sigue construido en modo histórico y sin sello externo, y así se declara.

## 3. Efecto sobre lo publicado

Ninguna semana existente cambia de clase. El JSON de resultados admite el estado `invalid:archive` (traducido en el sitio en los tres idiomas); ninguna corrida publicada lo contiene.

## 4. Compatibilidad con las baterías de Astra

Con este código pasan enteras `review/out/astra_scratch/test_r26.py` (incluidos `test_runner_malformed_no_exception`, `test_missing_master_reuses_intact_copy`, `test_changed_master_same_runner`, `test_closed_master_same_runner_false_positive` y `test_corrupt_injected_copy_does_not_shadow_intact_system_copy`) y `test_r25.py` salvo `test_corruption_between_weeks_same_runner` (informe 31 §4); de `test_r24.py` sigue obsoleto `test_master_effective_view[past_revision]` (informe 30 §4).

## 5. Pendientes que siguen abiertos

Readmisión verificada en modo prospectivo (extractor multicaptura) y construcción del paquete en ese modo; sello externo de fecha; dividendos del universo completo; política de cierres sobrevenidos; adaptador oficial de lotes sueltos. Los bloqueantes que dependen del usuario no cambian (informe 21 §4).

## 6. Fe de erratas (tras la ronda 27)

Varias garantías de este informe (y las equivalentes del README) excedían lo que el código acreditaba, como señaló Astra en la ronda 27: (1) el índice se releía al cambiar, pero una recarga fallida podía dejarlo a medias y las etapas de una clasificación podían mezclar generaciones (R27-01, R27-02); (2) «cada semana cita la instantánea vigente al emitir» valía al empezar la semana, no durante toda la emisión (R27-03); (3) la integridad de los bytes no comprobaba que la ruta estuviera dentro del archivo (R27-04); (4) la contención `invalid:archive` dejaba las cestas heredadas sin gestionar, borraba la traza de lo archivado y no estaba soportada por cabeceras ni sitio (R27-05, R27-07, R27-08); (5) «ninguna excepción escapa de `run_week`» no cubría registros del índice mal tipados (R27-06). Todo queda corregido en el informe 33.

