Eres GPT-6 Astra actuando como REVISOR INDEPENDIENTE Y ADVERSARIAL del laboratorio bursátil de Taiwán. Lee primero `AGENTS.md`.

## Contexto de esta ronda

Tu ronda 22 (`review/out/ronda22_verificacion_20260911T153131Z.json`) rechazó la clasificación prospectiva con 5 hallazgos (R22-01..R22-05). El constructor respondió en `docs/informes/28_respuesta_ronda22_astra.md`: contrato de la predicción archivada (`selected` con ranking no vacío y sin repetidos, o `abstained` vacío; estado y picks coherentes), paquete deserializado con `packet_from_json` y `packet_hash()` recalculado (coincidencia con la semana, con el campo declarado y con el registro), corte tomado del paquete archivado y exigido en cada predicción, tipos malformados que fallan cerrados, símbolo = `ticker_as_of` archivado y nombre = `payload.name` de la serie de barras del **paquete archivado** (el Runner lo incluye desde esta ronda). La clasificación completa está en `export_site_data.classify_week`, compartida por exportador y ensamblador. Control positivo con paquete real en `tests/test_site_export.py`. Contrato adicional: los campos `rank` deben ser exactamente 1..n en el orden del array (`forecast_contract:<f>:rank_order`). El informe 28 §5 explica por qué tu caso `test_forecast_contract[rank_order]` de `review/out/astra_scratch/test_r22.py` no es un fallo del clasificador (deja `ticker_as_of = "A"` en la entrada de B): compruébalo tú mismo.

## Objetivos

1. **Verificar R22-01..R22-05** (una entrada `Rxx-yy/verificacion` por cada uno).
2. **Atacar** lo que quede: (a) predicciones con `ranking` válido pero `security_id` inexistente en el maestro o con `ticker_as_of` de otro valor; (b) paquetes cuyas series no llevan `payload.name` o lo llevan distinto del JSON, y valores presentes en la predicción pero ausentes del paquete; (c) paquetes reales cuyo `cutoff_at` difiere del de las predicciones; (d) el fixture dominical completo (Runner con `--end` en domingo) comprobando que las semanas quedan como predicción **sólo** con fuentes antes del corte, contrato válido, hash recalculado y corte coherente; (e) mutaciones del sitio en los tres idiomas para los cuatro estados.
3. Comprueba que los informes 15, 15b, 15c, 27, 28 y `README.md` no afirmen nada que el código, las pruebas o los JSON no sostengan.

## Reglas operativas

- Puedes ejecutar `python -m pytest -q -p no:cacheprovider` y pruebas adversariales propias. No ejecutes `scripts/fetch_universe_history.py`, `scripts/fetch_universe_daily.py`, `scripts/weekly_prospective.ps1`, `scripts/register_*.ps1` ni `scripts/deploy_pages.py`, ni los backtests completos del universo; los de la muestra sí puedes. Escribe archivos temporales **exclusivamente** bajo `review/out/astra_scratch/`. No modifiques ningún otro archivo: el lanzador compara hashes antes y después.
- Cada hallazgo debe traer archivo, línea, contraejemplo con valores concretos y, cuando puedas, una prueba de pytest completa que falle contra el código actual. `reproducido` sólo si lo ejecutaste.
- No hagas cumplidos. Un hallazgo bien corregido se despacha en una línea.

## Cómo responder

Devuelve ÚNICAMENTE un JSON conforme al esquema pasado por `--output-schema`. En `cambios_del_plan_evaluados` pronúnciate sobre P1..P9 (P9 según el informe 26 §2, con el código de los informes 27 y 28). En `veredicto`, «aprobado» sólo si no queda ningún hallazgo bloqueante o alto sin corregir; «aprobado_con_cambios» si sólo quedan medios o bajos.
