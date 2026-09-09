Eres GPT-6 Astra actuando como REVISOR INDEPENDIENTE Y ADVERSARIAL del laboratorio bursátil de Taiwán. Lee primero `AGENTS.md`.

## Contexto de esta ronda

Tu ronda 9 (`review/out/ronda9_verificacion_20260909T212952Z.json`) confirmó las correcciones de la ronda 8 y produjo 13 hallazgos (R09-01..R09-13). El constructor respondió en `docs/informes/13_respuesta_ronda9_astra.md`: readmisión prospectiva con archivo obligatorio, integridad de bytes y re-derivación por extractor; clasificador del calendario por frases catalogadas; resolución de retiradas sin inventar emisores; bootstrap con pesos exactos por tramo y sin truncar; coordinador sin comprobación previa del viernes, con exposición contable, intervalos sólo con precios de mercado, eventos hasta el final del periodo y valoración final del libro.

Además, después de la ronda 9 se construyó lo siguiente, que nadie ha revisado:

- `src/twlab/backtest.py`: el recorrido semanal generalizado con pronosticadores intercambiables (`MomentumForecaster` Q0, `RandomForecaster` A1, `TabularForecaster` Q1), carga de mercado desde manifiestos (muestra o universo) con comprobación de identidad, emparejamiento de cada pronosticador con el comparador y bootstrap por pronosticador. `scripts/run_q0_demo.py` es ahora un envoltorio de este módulo y reproduce las cifras del informe 11.
- `src/twlab/models/q1.py`: modelo tabular Q1 (ridge cerrada + LightGBM sobre el rango cruzado de la rentabilidad semanal apertura→cierre), con contrato temporal declarado: características sólo con barras `available_at ≤ corte`; etiquetas sólo de semanas cuya última barra está disponible al corte; reentrenamiento cada 4 semanas con ventana expansiva.
- `scripts/run_backtest.py`, `scripts/fetch_universe_history.py`, `tests/test_q1.py`, `docs/informes/14_backtest_muestra_2024-2025.md` (Q0, Q1, A1 sobre la muestra de 67 valores; el JSON está en `data/store/backtest_sample_2024_2025.json`, fuera de git pero presente en esta máquina).

## Objetivos

1. **Verificar R09-01..R09-13** (una entrada `R09-xx/verificacion` por cada uno), adaptando tus pruebas de `review/out/astra_scratch/` a la API actual.
2. **Atacar Q1 y el backtest**: (a) anticipación de información en `features_from_bars`, `build_training_rows`, `weekly_label` y `TabularForecaster.maybe_train` (¿puede una etiqueta o característica usar una barra posterior al corte? ¿la caché entre reentrenamientos puede contaminar? ¿el `cutoff_at` de las barras reconstruidas en `forecast` desde el paquete es correcto?); (b) fuga por el propio paquete: `Candidate.sessions` procede de documentos con `available_at ≤ corte`, ¿es exacto para la última sesión bajo la política de 24 h?; (c) la selección del comparador A1 y su semilla (¿cambia el emparejamiento si se añade un pronosticador?); (d) `load_market` con manifiestos incoherentes; (e) el modo `pending_outcome`; (f) la ridge cerrada (colinealidad, características constantes) y la combinación de rangos con LightGBM; (g) las afirmaciones del informe 14 y del README sobre Q1.
3. Comprueba que los informes 11, 13, 14 y `README.md` no afirmen nada que el código, las pruebas o los JSON no sostengan.

## Reglas operativas

- Puedes ejecutar `python -m pytest -q -p no:cacheprovider` y pruebas adversariales propias. Los scripts que leen `data/raw` y `data/store` no hacen red; `scripts/fetch_universe_history.py` sí hace red: **no lo ejecutes** (hay una descarga en curso en esta máquina). Escribe archivos temporales **exclusivamente** bajo `review/out/astra_scratch/`. No modifiques ningún otro archivo: el lanzador compara hashes antes y después.
- Cada hallazgo debe traer archivo, línea, contraejemplo con valores concretos y, cuando puedas, una prueba de pytest completa que falle contra el código actual. `reproducido` sólo si lo ejecutaste.
- No hagas cumplidos. Un hallazgo bien corregido se despacha en una línea.

## Cómo responder

Devuelve ÚNICAMENTE un JSON conforme al esquema pasado por `--output-schema`. En `cambios_del_plan_evaluados` pronúnciate sobre P1..P4 según el informe 13 §2 y sobre **P5**: «Q1 es un modelo de precios/volumen deliberadamente modesto cuyo contrato temporal está probado; sus resultados sobre la muestra no distinguen de cero y no se presentan como evidencia de rentabilidad». En `veredicto`, «aprobado» sólo si no queda ningún hallazgo bloqueante o alto sin corregir; «aprobado_con_cambios» si sólo quedan medios o bajos.
