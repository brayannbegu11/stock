# Respuesta del constructor a la ronda 28 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda28_verificacion_20260911T180142Z.json`, árbol congelado e íntegro (el primer intento de la ronda, `review/out/ronda28_launcher_intento1_bloqueado.log`, no produjo veredicto: el proveedor bloqueó la salida de Astra al redactar variantes de rutas de escape; el prompt se reformuló para que verificara R27-04 ejecutando las pruebas existentes). Veredicto de Astra: **rechazado** (9 hallazgos nuevos: 3 altos, 6 medios; todos reproducidos). Verificó las ocho correcciones de la ronda 27 (R27-01..R27-08, todas reproducidas), que los 11.803 registros del índice real cumplen el tipado nuevo, que la exportación conserva las 54 semanas y cifras publicadas, y que la objeción del informe 33 §4 es válida. Encontró que una clasificación anidada liberaba el fijado del índice, que el libro no llegaba al cierre en semanas fallidas sin cestas, que la contención abarcaba también la evaluación, que la lectura inicial del índice y la forma de la semana quedaban fuera de la contención, que aún escapaban excepciones de `run_week` con estructuras malformadas, que el exportador no aplicaba el tipado del almacén, que un fallo histórico podía quedarse como semana en curso, que las causas de fallos históricos se perdían en tabla e informe, y que la cabecera 15 abortaba sin estadísticas. Todo se corrige aquí; las pruebas nuevas llevan el identificador del hallazgo en el nombre.

## 1. Correcciones por hallazgo

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R28-01 | alta | `classify_week` guarda el fijado exterior y lo **restaura** al salir: una clasificación anidada hereda la generación exterior y no la libera. | `test_r28_01_a_nested_classification_keeps_the_outer_generation` |
| R28-02 | alta | `_carry_inherited` (y la semana válida, por simetría) avanza el reloj del libro hasta el cierre de la semana (`advance_to(exit_at)`) antes de valorar: los derechos pagaderos en la semana se liquidan aunque no queden cestas. | `test_r28_02_consecutive_failed_weeks_settle_rights_and_reach_the_close` |
| R28-03 | media | La lectura inicial del índice y la forma de la semana están contenidas: índice ilegible (p. ej. un directorio) o semana que no es un objeto cierran con `classification_error:<tipo>` y liberan el fijado. | `test_r28_03_the_initial_read_and_the_week_shape_are_contained` (3 casos) |
| R28-04 | media | `RawStore._read_manifest` convierte bytes no UTF-8 o un índice ilegible en `ManifestCorrupt`; `_check_market` (calendario, estructuras, maestro y sus filas) se comprueba **antes de planificar** y deja la semana `invalid:archive`; un pronosticador que lanza o devuelve algo que no es una predicción queda como predicción `invalid` con motivo `forecast_error:<…>`, archivada como las demás, sin abortar la semana. | `test_r28_04_malformed_structures_do_not_escape_run_week` (6 casos) |
| R28-05 | alta | Emisión y evaluación separadas (`_emit_week` / `_evaluate_week`): la contención cubre sólo la emisión; un fallo en la evaluación **no** es del archivo, no marca `invalid:archive` ni intenta retroceder libros ya operados: se propaga. | `test_r28_05_an_evaluation_failure_is_not_an_archive_failure` |
| R28-06 | media | El exportador aplica el contrato tipado del almacén (`CaptureRecord.from_manifest_line`) en `_record_ok` y en la elección de la primera copia íntegra: lo que `RawStore` rechaza como corrupto tampoco es evidencia (`malformed_record`). | `test_r28_06_the_exporter_applies_the_store_record_contract` (12 casos) |
| R28-07 | media | Semana en curso = la última si está pendiente o no se emitió; si no, la última pendiente; si no, la última. Un fallo histórico seguido de semanas válidas no es la semana en curso (exportador, ensamblador y sitio). | `test_r28_07_a_historical_failure_is_not_the_current_week` |
| R28-08 | media | Las causas concretas se conservan en todas partes: tabla del sitio (chip con `archive_error`), informe Markdown (`archive_error` junto a la nota) y cabeceras (nota de semanas no emitidas con su causa, `failed_weeks_note`). | `test_r28_08_markdown_report_and_site_table_keep_every_failure_cause` |
| R28-09 | media | `header_15` sin semanas operadas: las medias ausentes se tratan como «todavía no hay medias que leer»; sin división ni índice sobre listas vacías. | `test_r28_09_header_15_survives_a_first_failed_week_without_statistics` |

Control positivo: la semana real de `_real_week_fixture` sigue siendo predicción; el fixture dominical de Astra también; el índice real (11.803 registros) cumple el contrato tipado.

## 2. Cambios de plan evaluados por Astra

P1, P3, P6 y P9 rechazados por R28-01, R28-02, R28-05, R28-06 y las garantías de presentación: corregidos arriba. P2, P4 y P5 con condiciones, atendidas (trayectoria contable de semanas fallidas consecutivas; emisión y evaluación distinguidas; estructuras malformadas contenidas). Las garantías del README y de los informes 32 §6 y 33 se acotan en el informe 33 §6. El paquete sigue construido en modo histórico y sin sello externo, y así se declara.

## 3. Efecto sobre lo publicado

Ninguna semana existente cambia de clase ni de cifras (ninguna corrida publicada contiene semanas `invalid:archive`; el `advance_to(exit_at)` añadido a la semana válida no altera valoraciones ya publicadas porque el reloj ya alcanzaba el cierre con cestas). La semana en curso del sitio pasa a ser siempre la última de la corrida.

## 4. Compatibilidad con las baterías de Astra

Con este código pasan enteras `review/out/astra_scratch/test_r27.py` (salvo los cuatro casos de `test_archive_failure_does_not_mutate_books`, informe 33 §4) y `test_r28.py`; de `test_r28_extension.py` queda `test_failure_during_second_ledger_does_not_escape`, que exige marcar `invalid:archive` una semana cuyo fallo ocurre **durante la evaluación**: por R28-05 se ha decidido lo contrario, y a propósito: un error al valorar no es un fallo del archivo, la semana no se etiqueta como no emitida y el error se propaga sin intentar retroceder libros ya operados.

## 5. Sobre las rondas siguientes

Las rondas 20 a 28 han encontrado, cada una, entre cuatro y nueve vías nuevas, cada vez más internas (índices reescritos entre lecturas, maestro cambiado a mitad de emisión, fallos inyectados en la evaluación). Todas están corregidas y probadas. A partir de aquí las rondas se lanzarán cuando existan semanas prospectivas reales que revisar (primera: corte del 13-09-2026), salvo indicación del autor. El prompt de la ronda 29 queda preparado en `review/prompts/ronda29_verificacion.md`.

## 6. Pendientes que siguen abiertos

Readmisión verificada en modo prospectivo (extractor multicaptura) y construcción del paquete en ese modo; sello externo de fecha; dividendos del universo completo; política de cierres sobrevenidos; adaptador oficial de lotes sueltos. Los bloqueantes que dependen del usuario no cambian (informe 21 §4).
