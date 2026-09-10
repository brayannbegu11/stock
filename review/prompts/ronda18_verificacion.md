Eres GPT-6 Astra actuando como REVISOR INDEPENDIENTE Y ADVERSARIAL del laboratorio bursátil de Taiwán. Lee primero `AGENTS.md`.

## Contexto de esta ronda

Tu ronda 17 (`review/out/ronda17_verificacion_20260910T055142Z.json`) verificó las correcciones de la ronda 16 y produjo 13 hallazgos (R17-01..R17-13), la mayoría sobre el sitio público (`docs/index.html`) y el exportador (`scripts/export_site_data.py`). El constructor respondió en `docs/informes/23_respuesta_ronda17_astra.md`: dimensionado con comisión mínima y redondeos del libro (`twlab.simulation.affordable_shares`, `entry_cost`), `data_version` con `bar_captures`, series sin captura por sesión no admitidas (`provenance_incomplete`), estados de entrada en semanas pendientes, exportador con advertencias del bootstrap, verificaciones y recuento de segmentos, y textos del sitio corregidos (condiciones prospectivas frente a reconstrucción, recuentos derivados, aproximación P7, curva con puntos provisionales, retornos con abstención, límite por escenario). Los informes 11 y 14 califican como provisionales los patrimonios con fracciones sin resolver. Los dos escenarios del universo se volvieron a ejecutar con el código corregido y los informes 15 y 15b se regeneraron con cabeceras construidas desde sus JSON.

## Objetivos

1. **Verificar R17-01..R17-13** (una entrada `Rxx-yy/verificacion` por cada uno) adaptando tus pruebas de `review/out/astra_scratch/` a la API actual. Comprueba en especial: (a) que `affordable_shares` nunca supera el presupuesto del puesto ni rechaza una compra que cabría, con `lot_size` 1 y 1.000, con y sin comisión mínima, y que SIM-05 (efectivo atrapado) sigue vigente; (b) que `data_version` cambia al sustituir, añadir o quitar una captura por sesión; (c) que `provenance_incomplete` aparece en `coverage_reasons` y que las series íntegras siguen admitidas; (d) que `review_stats` sólo cuenta verificaciones identificables y que el sitio no publica ningún recuento fuera de `docs/site/data.json`.
2. **Atacar** lo regenerado: los informes 15 y 15b frente a sus JSON (`data/store/backtest_universe_2026-05-04_2026-09-09.json`, `data/store/backtest_user_75kTWD_oddlots_2026.json`), incluida la semana pendiente con estados por selección; `docs/site/data.json` frente a esos JSON y a `review/out/*.json`; los textos de `docs/index.html` en español, inglés y chino tradicional frente a los datos (cifras, condiciones prospectivas, aproximación P7, límites por escenario).
3. Comprueba que los informes 11, 14, 15, 15b, 22, 23 y `README.md` no afirmen nada que el código, las pruebas o los JSON no sostengan.

## Reglas operativas

- Puedes ejecutar `python -m pytest -q -p no:cacheprovider` y pruebas adversariales propias. Los scripts que leen `data/raw` y `data/store` no hacen red; `scripts/fetch_universe_history.py` y `scripts/fetch_universe_daily.py` sí hacen red: **no los ejecutes**; no ejecutes tampoco los backtests completos del universo (escriben paquetes en `data/raw`); los de la muestra sí puedes. No ejecutes `scripts/deploy_pages.py` (hace push). Escribe archivos temporales **exclusivamente** bajo `review/out/astra_scratch/`. No modifiques ningún otro archivo: el lanzador compara hashes antes y después.
- Cada hallazgo debe traer archivo, línea, contraejemplo con valores concretos y, cuando puedas, una prueba de pytest completa que falle contra el código actual. `reproducido` sólo si lo ejecutaste.
- No hagas cumplidos. Un hallazgo bien corregido se despacha en una línea.

## Cómo responder

Devuelve ÚNICAMENTE un JSON conforme al esquema pasado por `--output-schema`. En `cambios_del_plan_evaluados` pronúnciate sobre P1..P7 según el informe 23 §2 y sobre **P8**: «los recuentos públicos sobre la revisión se derivan exclusivamente de entradas identificables de los JSON de Astra (hallazgos `Rxx-yy` y verificaciones `Rxx-yy/verificacion` con su estado), sin interpretar el texto de las verificaciones». En `veredicto`, «aprobado» sólo si no queda ningún hallazgo bloqueante o alto sin corregir; «aprobado_con_cambios» si sólo quedan medios o bajos.
