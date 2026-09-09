# Respuesta del constructor a la ronda 9 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda9_verificacion_20260909T212952Z.json` (sha256 `eeb2e393…78a0`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Confirmó las 13 correcciones de la ronda 8 (R08-01..R08-13, cuatro de ellas con límites que se convirtieron en hallazgos nuevos) y produjo 13 hallazgos (R09-01..R09-13: 5 altos, 7 medios, 1 bajo). Reprodujo byte a byte el maestro, el informe 10 y el JSON de la demo; verificó los 102 paquetes y la ausencia de barras posteriores al corte bajo la política de 24 h.

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada R09 tiene prueba nombrada o corrección verificable en la demo regenerada (informe 11).

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba / verificación |
|---|---|---|---|
| R09-01 | alta | `readmission_problems` lee los bytes archivados (`RawStore.read` verifica el sha256; un archivo sustituido conservando el manifiesto falla por integridad) y re-deriva el *payload* y las identidades con el extractor registrado; sin extractor registrado el documento **no se readmite**. El evaluador acepta `extractors=` y lo pasa. | `test_r09_01_r09_02_r09_03_readmission_requires_the_archive_checks_bytes_and_rederives_payloads` |
| R09-02 | media | En modo prospectivo el archivo es obligatorio: sin `store` la readmisión falla cerrada (`archive_required_for_prospective_readmission`). | ídem |
| R09-03 | media | Los rechazos recuperados deben ser únicos, con motivo del catálogo de admisión (`KNOWN_REJECTION_REASONS`) y sin colisión con los admitidos. | ídem |
| R09-04 | alta | El clasificador del calendario en inglés ya no usa subcadenas: sólo acepta frases completas del catálogo observado (23 de cierre, 5 de sesión) o combinaciones de frases de cierre separadas por «/» o «&», tras normalizar mayúsculas, apóstrofos, puntos finales y sufijos de año. «Not a Holiday», «Typhoon warning: trading continues», «Market Open is not confirmed», «Holiday schedule; Market Open» y cualquier redacción nueva (incluidos cierres por tifón) son `unknown` y detienen la carga. Las 29 descripciones reales siguen clasificándose (1.462 sesiones). | `test_r08_02_r09_04_classify_holiday_row_en_only_accepts_catalogued_phrases` (29 casos), `test_reference_calendar_2021_2026_…` |
| R09-05 | media | `resolve_delistings`: «emisor anterior» sólo si la retirada es anterior al alta de **todos** los segmentos del símbolo; alta y baja el mismo día o retirada posterior a un segmento cerrado quedan en `unresolved` para inspección, sin inventar otro emisor. El censo informa el recuento (hoy 0). | `test_r09_05_delisting_without_covering_segment_is_unresolved_unless_an_earlier_issuer_is_implied` |
| R09-06 | alta | La demo ya no comprueba antes del paquete si el viernes tendrá negociación: el paquete, la predicción y la reserva de puestos se producen siempre; un cierre sobrevenido se descubre al llegar a la sesión (entrada fallida por falta de apertura, salida bloqueada por falta de cierre, reintentos de cestas anteriores incluidos) y la semana se etiqueta **después** de ocurrir. | demo regenerada (informe 11 §2) |
| R09-07 | media | Formulación corregida en 11, 12 y en el propio script: el calendario de planificación son las listas anuales oficiales **capturadas el 9-09-2026**; el supuesto declarado es que cada lista estaba publicada antes de los cortes de su año; no hay versiones históricas ni revisiones archivadas y por tanto no se afirma «conocido al corte». | informes 11 §1, 12 §2 |
| R09-08 | alta | `final_equity` es la valoración del libro al cierre del periodo (`final_valuation`: instante, sesión de precios, efectivo, cobros pendientes, valor de posiciones, no resueltas y marcas), después de procesar todos los eventos; las semanas sin sesiones también valoran la curva. | demo regenerada (`summary.<libro>.final_valuation`) |
| R09-09 | media | El cursor de eventos procesa hasta `end` inclusive aunque no quepa otra semana; `events_processed_through` lo declara. | demo regenerada |
| R09-10 | media | Un intervalo con precio «stale» en la apertura o en el cierre no es admisible para emparejar (`unpaired_reason = stale_price_in_interval`); la curva semana a semana se conserva con la marca. | demo regenerada |
| R09-11 | alta | La exposición usa la misma valoración contable que el patrimonio (`Valuation.positions_value` tras la entrada): una posición retirada sin precio terminal vale cero en ambos. | demo regenerada |
| R09-12 | media | El tramo se elige con probabilidad proporcional a `longitud / min(bloque, longitud)`, de modo que su fracción esperada en la muestra remuestreada es exactamente `longitud / n` aunque las extracciones tengan longitudes distintas; `resample_mean` lo verifica (tramos 1 y 8 → 1/9; 2 y 8 → 0,2). | `test_r09_12_segment_weights_are_preserved_when_segments_are_shorter_than_the_block`; `test_r08_11_…` |
| R09-13 | baja | Informe 10: la columna se rotula «acciones ordinarias vigentes del tablero principal»; informe 09 §3 aclara que 1.973 era el recuento anterior a R08-13 (hoy 1.937). | informes 09, 10 |

## 2. Posiciones de Astra sobre P1..P4

- **P1 (rechazo).** Aceptado. La frase «mismo filtro de `build_packet`» era falsa. Ahora la readmisión prospectiva exige archivo, verifica los bytes y re-deriva el *payload* con el extractor registrado; sin registro, no readmite. Sigue pendiente el catálogo de extractores reales, lo que significa que hoy ningún documento prospectivo con contenido se readmite: es la posición segura hasta que exista.
- **P2 (acepto con condiciones).** Condiciones aceptadas y mantenidas: registro de producción vacío y de sólo lectura; nada prospectivo hasta verificadores criptográficos y readmisión completa.
- **P3 (acepto).** Las tres garantías del motor se mantienen. El coordinador corrige ahora la rama de cierre sobrevenido (R09-06), la cola del periodo (R09-09) y la valoración agregada (R09-08); no se reclama ninguna garantía general sobre él.
- **P4 (rechazo).** Aceptado. Formulación vigente en informe 11: la demo ejecuta el recorrido semanal sobre datos reales archivados con las listas anuales oficiales capturadas en 2026 (supuesto declarado sobre su publicación), no usa datos posteriores al corte para decidir nada (el paquete y la reserva de puestos se producen antes de saber si la sesión de salida existió), mide intervalos apertura→cierre sobre el patrimonio contable y valora el libro al final del periodo. No demuestra la gestión de cierres sobrevenidos (no hubo ninguno en sesiones de entrada o salida) ni acredita disponibilidad histórica verificada.

## 3. Respuestas a las preguntas del revisor

1. **Archivo obligatorio e integridad de bytes.** Sí, ya (R09-01/02): sin archivo la readmisión prospectiva falla; con archivo se leen los bytes (sha256 verificado) y se re-deriva el *payload*; sin extractor registrado no hay readmisión. No depende del catálogo pendiente: el catálogo sólo ampliará lo que puede readmitirse.
2. **Cierre sobrevenido conocido después de operar.** El paquete y el plan sellados no se tocan (conservan `calendar_version`); las posiciones siguen en el libro y la salida bloqueada se reintenta en la siguiente sesión con cierre (R09-06). Lo que falta es la regla del protocolo para la medición de esa semana (diferir la salida, anular la semana o liquidar al último cierre): decisión del usuario, informe 11 §4.
3. **Qué instante es `final_equity`.** La valoración del libro a las 23:59 Taipei del último día del periodo con los cierres de la última sesión oficial, tras procesar todos los eventos; el resumen separa efectivo, cobros pendientes, valor de posiciones, posiciones no resueltas (riesgo terminal sin precio) y marcas de valoración provisional (`fractional_shares_unresolved`, `stale_price`).
4. **Regla de remuestreo con tramos cortos.** Probabilidad del tramo ∝ `longitud / min(bloque, longitud)` (R09-12); 2025-W04 pesa 1/n en esperanza. El efecto de borde dentro de un tramo (las semanas extremas caen en menos bloques) es el inherente al bootstrap por bloques móviles y se declara; una variante circular uniría el final de un tramo con su principio, que es justo lo que R02-08 prohíbe.

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161; registro de producción vacío.
- Catálogo de extractores reales (sin él, ningún documento prospectivo con contenido se readmite).
- Política de cierres sobrevenidos y su fuente oficial; versiones históricas del calendario con fecha de publicación.
- Adaptador de lotes menores (零股) y resolución en efectivo de fracciones.
- Maestro histórico completo (263 retiradas TWSE sin fecha de alta; emisor con TEJ).
- Módulo de informe estadístico STA-02/03/05/06/07.
- Congelamiento del protocolo (costes y rotación, dimensionado, tolerancia de exposición, `block_length`, liquidez, tablero de innovación, redondeo de efectivo, plazo de registro de semanas sin sesiones). Decisión del usuario.
