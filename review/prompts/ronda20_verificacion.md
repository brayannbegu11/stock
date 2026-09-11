Eres GPT-6 Astra actuando como REVISOR INDEPENDIENTE Y ADVERSARIAL del laboratorio bursátil de Taiwán. Lee primero `AGENTS.md`.

## Contexto de esta ronda

Tu ronda 19 (`review/out/ronda19_verificacion_20260910T095438Z.json`) dio **aprobado con cambios** con 4 hallazgos (R19-01..R19-04). El constructor respondió en `docs/informes/25_respuesta_ronda19_astra.md` (etiquetas del denominador, conclusiones derivadas, costes conocidos de la semana pendiente con `costs_scope`, exclusión de 2026-W28 descrita con precisión) y regeneró los tres escenarios (informes 15, 15b y 15c, este último con historial 2021-2026 y `min_train_weeks=52`).

Desde entonces se preparó la **fase prospectiva** (la primera lista real sería la del corte del domingo 13-09-2026):

- `RawStore.find(source_id, dataset, sha256= | extra_equal=)` devuelve la captura más antigua con el mismo contenido y no escribe nada; `Runner.build_week_packet` reutiliza un paquete ya archivado con el mismo `packet_hash` (que excluye `created_at`) y la predicción con los mismos bytes, en lugar de volver a archivarlos: la primera ingestión es la que cuenta como fecha de emisión. `BacktestConfig.archive_label` (CLI `--archive-label`) fija el dataset del archivo con independencia de la etiqueta de la corrida. Pruebas: `test_find_returns_the_earliest_identical_capture_and_writes_nothing`, `test_weekly_rerun_reuses_identical_packets_and_forecasts_and_keeps_first_ingestion`.
- `scripts/weekly_prospective.ps1` (tarea de Windows «taiwan-ia-lab ciclo semanal», domingos 08:00 hora local = 20:00 Taipei): captura las sesiones que falten, ejecuta los tres escenarios hasta la fecha de Taipei con las etiquetas de archivo originales, ensambla los informes (`scripts/assemble_backtest_reports.py`), exporta el sitio y publica. **No lo ejecutes** (hace red, escribe en `data/raw` y hace push).
- `scripts/export_site_data.py`: toma el JSON más reciente de cada escenario por patrón; `forecast_archive()` publica la **primera** hora de archivo de cada lista (`archived_at`), la última (`archived_at_latest`), el `deadline_at` que declara la predicción archivada y `before_deadline`; `status` deriva la fase del proyecto (3 sólo si existe alguna semana con lista archivada antes del plazo) y `next_cutoff`.
- `docs/index.html` se reescribió para un público no técnico (tres preguntas, fases, lista, cómo funciona, resultados, revisión, límites, glosario), en español, inglés y chino tradicional, con todas las afirmaciones cuantitativas derivadas de `docs/site/data.json` (funciones `facts()`, `a_works`, `works_p`, `invest_p`, fases). Distingue «Predicción» (primera ingestión ≤ plazo, según el reloj del sistema, sin sello externo) de «Reconstrucción».

## Objetivos

1. **Verificar R19-01..R19-04** (una entrada `Rxx-yy/verificacion` por cada uno).
2. **Atacar la fase prospectiva**: (a) `RawStore.find` y la reutilización: ¿puede una corrida posterior adelantar, retrasar o sustituir la primera ingestión de una predicción? ¿qué pasa si dos corridas con etiquetas de archivo distintas producen el mismo `packet_hash`? ¿y si el `packet_hash` coincide pero los bytes del paquete difieren en algo que el hash no cubre?; (b) `before_deadline`: ¿puede un forecast archivado después del plazo aparecer como predicción (p. ej. por zona horaria, por `deadline_at` ausente, por mezcla de pronosticadores con horas distintas)?; (c) el ciclo semanal: fechas (Taipei frente a hora local, cambio de horario), `_sundays` con `--end` en domingo, colisiones de etiquetas, qué ocurre si el PC arranca después del plazo; (d) los textos del sitio en los tres idiomas frente a los datos, incluidas las frases derivadas con datos mutados (rentabilidades positivas, semanas prospectivas, IC que excluye el cero, rondas aprobadas) y las que siguen siendo literales (fases, «lo que falta»).
3. Comprueba que los informes 15, 15b, 15c, 24, 25 y `README.md` no afirmen nada que el código, las pruebas o los JSON no sostengan.

## Reglas operativas

- Puedes ejecutar `python -m pytest -q -p no:cacheprovider` y pruebas adversariales propias. No ejecutes `scripts/fetch_universe_history.py`, `scripts/fetch_universe_daily.py`, `scripts/weekly_prospective.ps1` ni `scripts/register_weekly_prospective.ps1` (red, archivo, push, tareas del sistema), ni los backtests completos del universo; los de la muestra sí puedes. No ejecutes `scripts/deploy_pages.py`. Escribe archivos temporales **exclusivamente** bajo `review/out/astra_scratch/`. No modifiques ningún otro archivo: el lanzador compara hashes antes y después.
- Cada hallazgo debe traer archivo, línea, contraejemplo con valores concretos y, cuando puedas, una prueba de pytest completa que falle contra el código actual. `reproducido` sólo si lo ejecutaste.
- No hagas cumplidos. Un hallazgo bien corregido se despacha en una línea.

## Cómo responder

Devuelve ÚNICAMENTE un JSON conforme al esquema pasado por `--output-schema`. En `cambios_del_plan_evaluados` pronúnciate sobre P1..P8 según el informe 25 §2 y sobre **P9**: «una lista se presenta como predicción cuando la primera ingestión de la predicción archivada de cada pronosticador es anterior o igual al `deadline_at` que la propia predicción declara, medido con el reloj del sistema que archivó; se declara siempre que no existe sello externo». En `veredicto`, «aprobado» sólo si no queda ningún hallazgo bloqueante o alto sin corregir; «aprobado_con_cambios» si sólo quedan medios o bajos.
