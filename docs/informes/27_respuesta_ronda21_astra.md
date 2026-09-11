# Respuesta del constructor a la ronda 21 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda21_verificacion_20260911T151404Z.json` (sha256 `eb06235f…b98e`), árbol congelado e íntegro. Veredicto de Astra: **rechazado** (9 hallazgos nuevos: 3 altos, 4 medios, 2 bajos). Verificó las nueve correcciones de la ronda 20 (todas reproducidas) y volvió a atacar la clasificación prospectiva, que seguía admitiendo identidades parciales, listas y paquetes no vinculados a los bytes archivados y entradas sin integridad ni reloj comprobados. Todo se corrige aquí; las pruebas nuevas llevan el identificador del hallazgo en el nombre.

## 1. Correcciones por hallazgo

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R21-01 | alta | El exportador construye `expected` con **todos** los pronosticadores de la semana; si a cualquiera le falta el sha (ausente o vacío) no hay predicción (`no_forecast_identity:<f>`). El ensamblador usa la misma construcción. | `test_r21_01_every_forecaster_needs_an_identity` |
| R21-02 | alta | Para cada pronosticador se exige que la lista mostrada coincida, en orden, con el `ranking` de la predicción archivada (`picks_mismatch`) y que la predicción declare el mismo `packet_hash` que la semana (`packet_link_mismatch`); `inputs_before_cutoff` exige además que el paquete archivado lleve ese mismo `packet_hash` (`packet_hash_mismatch`). | `test_r21_02_shown_picks_and_packet_must_match_the_archived_bytes` |
| R21-03 | alta | `inputs_before_cutoff` comprueba, para el paquete y para cada captura referenciada: registro completo, integridad sha256 de los bytes, `clock_source == "system"` e ingestión antes o en el corte; todo documento admitido debe tener `capture_id` y todo manifiesto `session_captures` no vacío. Sólo `late_inputs` significa «recibido tarde»; lo demás es `unverified_inputs` o un motivo del paquete. | `test_r21_03_inputs_need_integrity_system_clock_and_complete_provenance` |
| R21-04 | media | La caché se indexa por (paquete, corte, hash), no sólo por paquete. | `test_r21_04_cache_is_keyed_by_cutoff` |
| R21-05 | media | La primera ingestión se elige por instante (conversión a UTC), no por orden lexicográfico; es esa primera la que debe llevar reloj del sistema. | `test_r21_05_first_ingestion_is_chosen_by_instant_across_offsets` |
| R21-06 | media | Un registro sin `path`, `sha256`, `ingested_at` o `clock_source` produce `ok=False` con `incomplete_record:<campo>`, no una excepción. | `test_r21_06_incomplete_packet_record_fails_closed` |
| R21-07 | media | Sitio (tres idiomas) y ensamblador distinguen «archivada a tiempo, datos tardíos» (`late_inputs`) de «archivada a tiempo, procedencia sin acreditar» (cualquier otro motivo). | textual; estados mutados en los tres idiomas |
| R21-08 | baja | README actualizado (última ronda respondida y regla para localizar la respuesta vigente); la afirmación del informe 26 §3 sobre `test_r20.py` se corrige y acota. Además: `allLose`/`anyBeat` del sitio consideran **todos** los escenarios (incluido el de historial largo) y el denominador narrativo del 15b/15 usa «compras brutas más ventas brutas heredadas». | textual |
| R21-09 | baja | `register_daily_quotes_fetch.ps1` e informe 26: «06:45 Taipei en verano, 07:45 en invierno». | textual |
| R19-01 / R19-02 (parciales) | media | Denominador narrativo en ambas cabeceras generadas; `allLose` con todos los escenarios. | como arriba |

## 2. Cambios de plan evaluados por Astra

P1–P8 aceptados con las condiciones atendidas arriba. **P9** sigue rechazado por Astra porque el código no acreditaba lo que la reformulación prometía; con R21-01..R21-06 el código exige ahora exactamente eso: identidad de todos los pronosticadores, lista igual a los bytes archivados, vínculo predicción-paquete-semana por `packet_hash`, primera ingestión por instante con reloj del sistema, y entradas íntegras, con reloj del sistema e ingeridas antes del corte. La readmisión verificada en modo prospectivo sigue pendiente y así se declara.

## 3. Efecto sobre lo publicado

Ninguna semana existente cambia de clase (siguen siendo reconstrucciones). Las condiciones nuevas sólo pueden cumplirlas las corridas que produzca el ciclo semanal a partir del corte del 13-09-2026 con los JSON que registran la identidad de cada predicción.

## 4. Pendientes que siguen abiertos

Readmisión verificada en modo prospectivo (extractor multicaptura) y construcción del paquete en ese modo; sello externo de fecha; dividendos del universo completo; política de cierres sobrevenidos; adaptador oficial de lotes sueltos. Los bloqueantes que dependen del usuario no cambian (informe 21 §4).
