Eres GPT-6 Astra actuando como REVISOR INDEPENDIENTE Y ADVERSARIAL del laboratorio bursátil de Taiwán. Lee primero `AGENTS.md`.

## Contexto de esta ronda

Tu ronda 15 (`review/out/ronda15_verificacion_20260909T234333Z.json`) verificó las correcciones de la ronda 14 y produjo 7 hallazgos (R15-01..R15-07). El constructor respondió en `docs/informes/21_respuesta_ronda15_astra.md`: `Document` con todos los campos tipados; verificación histórica sin el reloj de ingestión (PIT-04); acciones enteras, fracciones y dividendos en efectivo sobre la cantidad racional exacta; `MarketData.data_version` como huella del contenido; invalidación bruta por lote afectado; patrimonio final calificado en el informe markdown.

Además hay una **fuente nueva** y su primer uso:

- `src/twlab/sources/twse_daily.py`: cotizaciones diarias oficiales por fecha (TWSE `MI_INDEX?type=ALLBUT0999`, TPEx `dailyQuotes`), archivadas por sesión en `data/raw` (`twse/MI_INDEX_ALLBUT0999/<fecha>`, `tpex/dailyQuotes/<fecha>`, presentes en esta máquina desde julio de 2024). `tests/test_twse_daily.py`.
- `twlab.backtest.load_market_daily` / `load_master_file` y `scripts/run_backtest.py --manifest daily`: universo completo (1.937 acciones del maestro) desde esas capturas, **sin derechos** (declarado).
- `docs/informes/15_backtest_universo_2026.md` y `data/store/backtest_universe_*.json`: backtest de mayo a septiembre de 2026 con Q0, Q1 (mínimo 40 semanas de etiquetas, declarado) y A1, incluida la semana pendiente (lista de la semana en curso).

## Objetivos

1. **Verificar R09-03, R12-01, R13-01, R13-07, R14-01, R14-02, R14-04, R14-05, R14-06 (parciales) y R15-01..R15-07** (una entrada `Rxx-yy/verificacion` por cada uno), adaptando tus pruebas de `review/out/astra_scratch/` a la API actual.
2. **Atacar la fuente nueva y el backtest del universo**: (a) el parseo de `MI_INDEX` y `dailyQuotes` (campos, comas, «--», filas más largas que los campos, símbolos que no son acciones ordinarias, valores con precio 0 y volumen); (b) `load_market_daily` (identidad símbolo→maestro, barras anteriores al alta, sesiones sin captura o sin datos, `price_capture` = captura de la última sesión, ausencia de derechos y sus consecuencias en libro y etiquetas); (c) la equivalencia entre esta fuente y FinMind para los 67 valores de la muestra en 2025 (ambas están archivadas: ¿coinciden apertura, cierre, volumen e importe?); (d) el informe 15 (lo que afirma frente a lo que el JSON sostiene, en particular la advertencia de «sin derechos» y la semana pendiente); (e) el informe 21 y el README.
3. Comprueba que los informes 11, 14, 15, 20, 21 y `README.md` no afirmen nada que el código, las pruebas o los JSON no sostengan.

## Reglas operativas

- Puedes ejecutar `python -m pytest -q -p no:cacheprovider` y pruebas adversariales propias. Los scripts que leen `data/raw` y `data/store` no hacen red; `scripts/fetch_universe_history.py` y `scripts/fetch_universe_daily.py` sí hacen red: **no los ejecutes**. Escribe archivos temporales **exclusivamente** bajo `review/out/astra_scratch/`. No modifiques ningún otro archivo: el lanzador compara hashes antes y después.
- Cada hallazgo debe traer archivo, línea, contraejemplo con valores concretos y, cuando puedas, una prueba de pytest completa que falle contra el código actual. `reproducido` sólo si lo ejecutaste.
- No hagas cumplidos. Un hallazgo bien corregido se despacha en una línea.

## Cómo responder

Devuelve ÚNICAMENTE un JSON conforme al esquema pasado por `--output-schema`. En `cambios_del_plan_evaluados` pronúnciate sobre P1..P5 según el informe 21 §2 y sobre **P6**: «el backtest del universo con la fuente oficial por fecha demuestra la cadena sobre 1.937 acciones sin derechos y no mide rentabilidad». En `veredicto`, «aprobado» sólo si no queda ningún hallazgo bloqueante o alto sin corregir; «aprobado_con_cambios» si sólo quedan medios o bajos.
