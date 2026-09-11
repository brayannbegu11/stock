# Respuesta del constructor a la ronda 27 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda27_verificacion_20260911T171847Z.json`, árbol congelado e íntegro. Veredicto de Astra: **rechazado** (8 hallazgos nuevos: 6 altos, 2 medios; todos reproducidos). Verificó las cuatro correcciones de la ronda 26 (R26-01..R26-04, todas reproducidas) y que los informes 15/15b/15c coinciden con sus JSON. Encontró que una recarga fallida del índice dejaba el diccionario por identificador antiguo, que las etapas de una clasificación podían ver generaciones distintas del índice, que el maestro podía cambiar entre la instantánea y la emisión, que la evidencia se leía fuera de `data/raw`, que la semana `invalid:archive` de la ronda 26 no gestionaba las cestas heredadas, que registros del índice mal tipados escapaban de `run_week`, y que ni las cabeceras ni el sitio soportaban esa semana fallida. Todo se corrige aquí; las pruebas nuevas llevan el identificador del hallazgo en el nombre.

## 1. Correcciones por hallazgo

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R27-01 | alta | Recarga atómica del índice: lista y diccionario por identificador se construyen en locales y se sustituyen juntos; una fila sin `capture_id` textual no puede referenciarse (no se indexa) y ya no puede dejar el índice a medias. | `test_r27_01_a_failed_index_reload_is_not_committed` |
| R27-02 | alta | Una generación por clasificación: `classify_week` lee el índice una vez y lo **fija** (`_PIN`) para todas las etapas; un índice reescrito a mitad de clasificación no se ve hasta la siguiente. | `test_r27_02_one_classification_uses_one_generation_of_the_index` |
| R27-03 | alta | Al terminar de archivar las predicciones, `_emit_week` vuelve a serializar el maestro y exige el mismo sha256 que la instantánea citada; si cambió durante la emisión, la semana queda `invalid:archive` (con la traza de lo archivado) y no se evalúa. | `test_r27_03_master_changed_between_snapshot_and_emission_fails_the_week` |
| R27-04 | alta | Contención de rutas en las dos capas: `RawStore.read` y el exportador (`_intact`) rechazan rutas absolutas, con `..`, con unidad o raíz, y rutas resueltas (enlaces incluidos) fuera de la raíz del archivo, aunque el sha256 coincida (`safe_relative_path`). | `test_r27_04_store_never_reads_outside_its_root`, `test_r27_04_evidence_outside_the_archive_is_not_evidence` (8 casos) |
| R27-05 | alta | Semana fallida con libro vivo: `_carry_inherited` aplica los derechos, avanza el libro, reintenta las salidas de las cestas heredadas en el último cierre de la semana y valora, exactamente como una semana válida sin cesta nueva; `pending_outcome` queda definido. | `test_r27_05_a_failed_week_still_manages_inherited_baskets` |
| R27-06 | media | Registros del índice **tipados** al construirse (`CaptureRecord.from_manifest_line` → `_validate_record_fields`: campos textuales, sha256 hexadecimal, `ingested_at` con zona, `bytes` entero, `extra` objeto, ruta relativa segura); cualquier fallo es `ManifestCorrupt`, contenido en la semana. Un mercado sin `SecurityMaster` también se contiene (`ManifestInconsistent`). | `test_r27_06_manifest_records_are_typed` (12 casos), `test_r27_06_malformed_index_records_are_contained_in_the_week` (4 casos), `test_r27_06_market_without_a_security_master_is_contained` (3 casos) |
| R27-07 | alta | Cabeceras 15/15b/15c: la semana en curso es la última pendiente **o** no emitida (`current_week`); la media de elegibles ignora semanas sin paquete; `temporal_sentence` describe la semana no emitida (motivo y predicciones archivadas antes del fallo); `picks_table` no falla sin pronosticadores. | `test_r27_07_report_headers_support_a_failed_current_week` (paquete y predicción) |
| R27-08 | media | Exportador: `archive_error`, `note` y `weeks_invalid_archive`; la semana en curso puede ser la fallida (`status`, `archive_error` en `current_week`); `classify_week` la cierra con motivo `invalid:archive`. Runner: conserva la traza de las predicciones archivadas antes del fallo. Sitio: estado «semana no emitida: fallo del archivo» con su motivo en la sección de la semana y en la tabla (antes que «pendiente»), en los tres idiomas. | `test_r27_08_exporter_and_site_show_the_failed_week` (paquete y predicción; render con `tests/site_render.cjs`) |

Control positivo: la semana real de `_real_week_fixture` sigue siendo predicción; el fixture dominical de Astra también.

## 2. Cambios de plan evaluados por Astra

P1, P3, P6 y P9 rechazados por R27-01..R27-05 y por las garantías de presentación: corregidos arriba. P2, P4 y P5 con condiciones, atendidas (semanas fallidas con trayectoria contable gestionada; maestro estable durante toda la emisión; garantías del README y del informe 32 acotadas en su §6). El paquete sigue construido en modo histórico y sin sello externo, y así se declara.

## 3. Efecto sobre lo publicado

Ninguna semana existente cambia de clase ni de cifras (ninguna corrida publicada contiene semanas `invalid:archive`). Los índices del archivo real cumplen el tipado nuevo (el exportador y las pruebas lo leen sin `ManifestCorrupt`).

## 4. Compatibilidad con las baterías de Astra

Con este código pasan enteras `review/out/astra_scratch/test_r26.py` y `test_r27.py` salvo `test_archive_failure_does_not_mutate_books` (4 casos), que exige que una semana fallida no toque el libro: es incompatible con el propio R27-05, que exige gestionar las cestas heredadas (derechos, reintento de salidas y valoración) durante esa semana, lo que necesariamente avanza el libro. Siguen obsoletos los casos señalados en los informes 30 §4 y 31 §4.

## 5. Pendientes que siguen abiertos

Readmisión verificada en modo prospectivo (extractor multicaptura) y construcción del paquete en ese modo; sello externo de fecha; dividendos del universo completo; política de cierres sobrevenidos; adaptador oficial de lotes sueltos. Los bloqueantes que dependen del usuario no cambian (informe 21 §4).
