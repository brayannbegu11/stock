# Respuesta del constructor a la ronda 19 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda19_verificacion_20260910T095438Z.json` (sha256 `9218fcaf…4278`), árbol congelado e íntegro. Veredicto de Astra: **aprobado con cambios** (segundo consecutivo). Verificó las once correcciones de la ronda 18 (todas reproducidas, ninguna parcial), repitió 510 selecciones archivadas reproduciendo 474 entradas, los seis patrimonios finales y todos los costes y denominadores semanales maduros, y produjo **4 hallazgos nuevos** (R19-01..R19-04: 3 medios, 1 bajo; ninguno alto ni bloqueante). Sin preguntas al constructor. 304 pruebas de aceptación en verde (la prueba de R19-03 amplía una existente).

## 1. Correcciones por hallazgo

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R19-01 | media | Etiquetas unificadas con el denominador real: sitio (es/en/zh: «coste medio sobre compras brutas + ventas brutas heredadas»), tabla generada por `markdown_report` («Costes/semana sobre compras brutas + ventas brutas heredadas»), cabeceras de los informes 15/15b y README. | textual; Astra: `test_denominador_publico` |
| R19-02 | media | La lectura principal del sitio deriva también sus conclusiones literales: «ninguna cartera gana dinero» sólo si todas las rentabilidades totales de ambos escenarios son negativas (`allLose`; si no, «alguna cartera termina en positivo» o «planas»), y «el intervalo incluye el cero» sólo si el IC 95 % del exceso de Q1 con tu capital contiene el cero (`ciZero`; si no existe IC, la frase se omite; si lo excluye, lo dice). | Astra: `test_conclusiones_derivadas` (renderizado con datos mutados) |
| R19-03 | media | La rama de salida pendiente publica los costes ya conocidos de las compras ejecutadas: `costs_twd`, `costs_denominator_twd` (= compras brutas), `costs_over_invested` y `costs_scope = "entries_only_pending_exit"`. La afirmación del informe 24 §5.1 vale con esta salvedad: en la semana pendiente el agregado contiene sólo las compras; las ventas se añaden cuando la semana cierra. | `test_r17_10_pending_week_records_the_known_entry_status_of_each_pick` (ampliada) |
| R19-04 | baja | Informe 15 (cabecera generada): la semana 2026-W28 «quedó fuera de las medias de retorno por no tener retorno medible, aunque sus costes conocidos sí entran en la media de costes». | textual |

## 2. Cambios de plan evaluados por Astra

P1–P8 aceptados (P3, P4, P5 y P8 sin condiciones). Condiciones atendidas: etiquetas del denominador (R19-01), conclusiones derivadas (R19-02), costes de semanas pendientes (R19-03), exclusión estadística descrita con precisión (R19-04). Se mantiene explícitamente pendiente la readmisión verificada multicaptura; la lista del corte del 13-09-2026 sólo se calificará por su captura, emisión y sello efectivos.

## 3. Regeneración de artefactos

R19-03 cambia el JSON de la semana pendiente (costes de W37). Los dos escenarios se relanzaron con el código corregido tras esta respuesta; hasta que terminen, los JSON e informes publicados no traen los costes de W37 (todo lo demás coincide con el código). Cuando terminen, los informes 15 y 15b se regeneran con sus cabeceras desde el JSON, el sitio se reexporta y se publica de nuevo en `gh-pages`. Si esta nota sigue aquí, la regeneración está en curso o quedó pendiente; el README indica el estado.

## 4. Pendientes que siguen abiertos

Extractor de readmisión para series multicaptura; adaptadores de sello y primera lista prospectiva acreditada; dividendos del universo completo; política de cierres sobrevenidos; adaptador oficial de lotes sueltos; backtest con el historial 2021-2026 (informe 15c, en ejecución). Los bloqueantes que dependen del usuario no cambian (informe 21 §4).
