# Respuesta del constructor a la ronda 13 de revisión (GPT-6 Astra)

> **Vigencia.** Las recetas de cantidades exactas (§1 R13-07, §3.2) y de persistencia de la ambigüedad (§1 R13-05) fueron ampliadas en los informes 20 y 21 (racionales exactos en todas las operaciones del libro; reclamación permanente por evento y fecha). Úsese como historial.

**Entrada:** `review/out/ronda13_verificacion_20260909T230327Z.json` (sha256 `d54e71d8…a47e`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Verificó las correcciones de la ronda 12 (R10-05, R10-10, R11-01, R12-03, R12-04 completas; R09-03, R12-01, R12-02 parciales) y produjo 8 hallazgos nuevos (R13-01..R13-08: 7 altos, 1 medio).

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada hallazgo tiene prueba nombrada. Las cifras de la muestra y de la demo no cambian (la muestra no contiene derechos contradictorios; sus cocientes por valor nominal ya eran exactos).

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R13-01 | alta | Todos los metadatos que ve el predictor son **catálogo o identificador**: `packet_id` identificador; `mode`, `evidence_class`, `week_status` de catálogos cerrados; `week_id` ISO; `calendar_version` `<fuente>@<versión>` con caracteres de identificador; en `Document`, `kind` de un catálogo cerrado, `supersedes`, `source_id` y `derivation` identificadores. Se comprueba al construir el objeto (también al recuperarlo con `packet_from_json`), así que un paquete forjado no llega a existir. Lo único con contenido es el `payload` de los documentos admitidos, que es el contenido legítimo. | `test_r13_01_packet_metadata_are_catalogued_or_identifiers_never_free_text` |
| R13-02 | alta | Las filas se agrupan por (tipo, fecha ex) **antes** de filtrar importes: cero junto a positivo es contradicción, no «el positivo». | `test_r13_02_to_05_contradictory_rights_become_ambiguous_and_invalidate_labels_and_intervals` |
| R13-03 | alta | Importes no finitos o negativos invalidan el derecho para libro y etiquetas a la vez. | ídem |
| R13-04 | alta | El periodo no forma parte de la agrupación: dos filas del mismo (tipo, fecha ex) con periodos distintos o vacíos son un solo derecho contradictorio, nunca dos cobros. Un periodo vacío con importe positivo es fila inválida. | ídem |
| R13-05 | alta | Un derecho contradictorio o inválido no desaparece: se conserva como **derecho ambiguo** (`DividendLike.ambiguous=True`, en `Security.events`). Consecuencias: (i) `weekly_label` devuelve `None` para cualquier semana que lo contenga (no hay etiqueta, ni con ni sin dividendo); (ii) el libro no lo aplica, la posición queda marcada (`ambiguous_right`) mientras se mantenga y el intervalo de la semana en que ocurre no es medible aunque la posición se venda; (iii) `market.warnings` y el informe markdown («Límites») lo declaran. | ídem |
| R13-06 | alta | Una posición retirada sin precio terminal marca `unresolved_terminal` en toda valoración: el intervalo no es medible y no entra en el exceso emparejado. | `test_r13_06_unresolved_delisting_makes_the_interval_unmeasurable` |
| R13-07 | alta | Los dividendos en acciones se representan de forma exacta (`stock_per_share` y `par_value`): el libro calcula cantidad × (nominal + reparto) / nominal multiplicando antes de dividir (3.000 × (3+1)/3 = 4.000 exactas) y Q1 usa la misma forma; `stock_ratio` queda sólo como valor informativo. | `test_r13_07_exact_par_ratio_keeps_whole_lots_sellable`, `test_r13_07_stock_dividend_uses_the_exact_par_ratio_end_to_end` |
| R13-08 | media | Informe 11 §5 declara la falta de versiones históricas de derechos; el informe markdown de los backtests (14 y siguientes) lleva una sección «Límites» con esa advertencia y el recuento de derechos ambiguos; el informe 17 lleva una nota de vigencia. | — |
| R09-03 (parcial) | alta | Absorbido por R13-01 (todas las vías de metadatos cerradas). | ídem R13-01 |
| R12-01 (parcial) | alta | Absorbido por R13-02..05 (validación y descartes correctos, con estado ambiguo). | ídem |
| R12-02 (parcial) | alta | Absorbido por R13-06. | ídem |

## 2. Posiciones de Astra sobre P1..P5

- **P1 (rechazo).** Aceptado: `packet_id`, `evidence_class`, `calendar_version`, `kind` y `supersedes` eran vías. Cerradas por catálogo o identificador (R13-01).
- **P2 (acepto con condiciones).** Mantenido.
- **P3 (rechazo).** Aceptado: colisiones ocultas (R13-02/04), eventos aceptados que el libro rechaza (R13-03), incertidumbre terminal en intervalos (R13-06) y lotes inmovilizados por redondeo (R13-07) están corregidos con prueba.
- **P4 (acepto con condiciones).** Condición atendida: las retiradas sin resolución quedan fuera de los intervalos medibles (R13-06).
- **P5 (rechazo).** Aceptado: la lista compartida rechaza infinitos, no duplica identidades por periodo y convierte las colisiones en un estado ambiguo que invalida etiquetas; la advertencia sobre revisiones llegó a los informes de resultados (R13-08).

## 3. Respuestas a las preguntas del revisor

1. **Estado de derecho ambiguo.** Sí: un derecho contradictorio o inválido se conserva como `ambiguous=True` en la lista compartida; invalida la etiqueta de su semana, marca la posición mientras se mantenga y hace no medible el intervalo de la semana en que ocurre. Nunca se convierte en «sin dividendo».
2. **Representación exacta de derechos.** Reparto en TWD de valor nominal por acción más el valor nominal (`stock_per_share`, `par_value`); las cantidades se calculan como cantidad × (nominal + reparto) / nominal, multiplicando antes de dividir, en el libro y en las etiquetas. Un cociente periódico sólo aparece cuando la cantidad resultante es realmente fraccionaria.

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161; registro de producción vacío.
- Catálogo de extractores reales; pronosticadores con LLM (L1/L2).
- Política de cierres sobrevenidos y su fuente oficial; versiones históricas del calendario y de los derechos.
- Adaptador de lotes menores; maestro histórico completo; emisor con TEJ.
- Fuente oficial por fecha para precios del universo (`MI_INDEX`, `dailyQuotes`): descarga en curso; sin dividendos históricos por esa vía.
- Congelamiento del protocolo (costes y rotación, dimensionado, tolerancia de exposición, `block_length`, liquidez, tablero de innovación). Decisión del usuario.
