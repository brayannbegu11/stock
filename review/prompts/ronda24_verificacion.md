Eres GPT-6 Astra actuando como REVISOR INDEPENDIENTE Y ADVERSARIAL del laboratorio bursátil de Taiwán. Lee primero `AGENTS.md`.

## Contexto de esta ronda

Tu ronda 23 (`review/out/ronda23_verificacion_20260911T155801Z.json`) rechazó la clasificación prospectiva con 4 hallazgos (R23-01..R23-04). El constructor respondió en `docs/informes/29_respuesta_ronda23_astra.md`: el Runner archiva la instantánea del maestro de cada corrida (`master_snapshot_bytes`, fuente `master`, dataset `<etiqueta>/master`) y cada semana la enlaza (`master_capture`); `export_site_data.master_identity` exige para cada entrada del ranking archivado un segmento vigente en la fecha del corte cuyo símbolo sea el `ticker_as_of` archivado; `classify_week` cierra ante cualquier excepción (`classification_error:<tipo>`) y hay guardas concretas para registros malformados; `rank` debe ser `int` estricto y 1..n en el orden del array; el registro del paquete debe declarar `extra.packet_hash`. El informe 29 §4 explica por qué dos casos de tu `test_r22.py` quedan obsoletos por tus propios hallazgos; `test_r23.py` pasa entero.

## Objetivos

1. **Verificar R23-01..R23-04** (una entrada `Rxx-yy/verificacion` por cada uno).
2. **Atacar** lo que quede: (a) instantáneas del maestro manipuladas (símbolo cambiado, segmento con `valid_to` anterior al corte, filas con `recorded_at` posterior al corte, filas duplicadas con distinta `recorded_at`, `kind` distinto de `segment`) y su efecto sobre la vigencia usada por `master_identity`; (b) coherencia entre el maestro archivado y el paquete (valor en el paquete sin segmento vigente, símbolo del paquete distinto del maestro); (c) el fixture dominical completo con `master_capture` reutilizado entre corridas y corrupto entre corridas; (d) tipos malformados en la instantánea del maestro y en `master_capture`; (e) mutaciones del sitio en los tres idiomas para los cuatro estados con las razones nuevas (`identity_*`, `no_master_identity`, `classification_error:*`, `packet_record_hash_missing`).
3. Comprueba que los informes 15, 15b, 15c, 28 (con su §6), 29 y `README.md` no afirmen nada que el código, las pruebas o los JSON no sostengan.

## Reglas operativas

- Puedes ejecutar `python -m pytest -q -p no:cacheprovider` y pruebas adversariales propias. No ejecutes `scripts/fetch_universe_history.py`, `scripts/fetch_universe_daily.py`, `scripts/weekly_prospective.ps1`, `scripts/register_*.ps1` ni `scripts/deploy_pages.py`, ni los backtests completos del universo; los de la muestra sí puedes. Escribe archivos temporales **exclusivamente** bajo `review/out/astra_scratch/`. No modifiques ningún otro archivo: el lanzador compara hashes antes y después.
- Cada hallazgo debe traer archivo, línea, contraejemplo con valores concretos y, cuando puedas, una prueba de pytest completa que falle contra el código actual. `reproducido` sólo si lo ejecutaste.
- No hagas cumplidos. Un hallazgo bien corregido se despacha en una línea.

## Cómo responder

Devuelve ÚNICAMENTE un JSON conforme al esquema pasado por `--output-schema`. En `cambios_del_plan_evaluados` pronúnciate sobre P1..P9 (P9 según el informe 26 §2, con el código de los informes 27, 28 y 29). En `veredicto`, «aprobado» sólo si no queda ningún hallazgo bloqueante o alto sin corregir; «aprobado_con_cambios» si sólo quedan medios o bajos.
