# Respuesta del constructor a la ronda 10 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda10_verificacion_20260909T215820Z.json` (sha256 `4b77cfc1…c54f`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Verificó las 13 correcciones de la ronda 9 (tres parciales: R09-03, R09-06, R09-12) y produjo 10 hallazgos sobre Q1 y el motor de backtest (R10-01..R10-10: 5 altos, 4 medios, 1 bajo). Reprodujo el JSON de Q0/Q1/A1 y el informe 14; auditó 103 paquetes y 6.901 documentos sin barras posteriores al corte; comprobó que añadir un pronosticador no cambia A1.

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada hallazgo tiene prueba nombrada; demo (informe 11) y backtest de la muestra (informe 14) regenerados con las correcciones.

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba / verificación |
|---|---|---|---|
| R09-03 (parcial) | media | El detalle de un rechazo sólo puede ser una de las plantillas que emite `build_packet` (`rejection_detail_is_canonical`, expresiones regulares por motivo); la excepción de un extractor se reduce a su clase, nunca a su mensaje. Cualquier texto libre en un rechazo recuperado impide la readmisión. | `test_r09_03_rejection_details_must_be_build_packet_templates` |
| R09-06 (parcial) | alta | Límite de simulación = mín(fin del periodo, último dato): la entrada se ejecuta si su sesión está dentro del límite aunque la salida no lo esté; la salida fuera del límite no se intenta y las posiciones quedan en seguimiento. Ya no desaparece una entrada ocurrida porque falte el viernes. | `test_r10_07_r09_06_period_end_is_respected_and_entries_before_the_bound_are_executed` |
| R09-12 (parcial) | media | Remuestreo **estratificado por tramo**: cada tramo aporta exactamente su longitud en observaciones (bloques uniformes dentro del tramo, truncados a esa longitud). Los pesos son exactos por construcción y ningún bloque cruza un hueco; con un solo tramo es el bootstrap por bloques móviles clásico. | `test_r09_12_segment_weights_are_preserved_when_segments_are_shorter_than_the_block` (igualdad exacta), `test_r08_11_…` |
| R10-01 | alta | `weekly_label` devuelve como instante de conocimiento el `available_at` más tardío de la apertura y del cierre; una apertura publicada después del corte impide etiquetar. | `test_r10_01_label_is_known_only_when_open_and_close_are_both_available` |
| R10-02 | alta | `TabularForecaster.maybe_train` rechaza cortes **decrecientes** (`ValueError`; un corte igual al anterior se admite): una instancia sirve a un solo recorrido cronológico. | `test_r10_02_tabular_forecaster_rejects_non_increasing_cutoffs` |
| R10-03 | media | La caché de filas sólo guarda filas completas (una fila sin desenlace se reintenta en cada llamada) y su clave incluye `data_version`, derivada de las capturas que alimentan el mercado. | `test_r10_03_cache_retries_missing_outcomes_and_is_keyed_by_data_version` |
| R10-04 | media | `_rank01` asigna rango medio a los empates: una señal constante vale 0,5 para todos y no cancela al componente informativo; se aplica igual a etiquetas y predicciones. | `test_r10_04_ties_get_average_ranks_so_a_flat_component_cannot_cancel_signal` |
| R10-05 | alta | `load_market` exige coherencia del manifiesto (`security_id` y `listing_date` declarados frente a lo reconstruido; recuento de barras) y descarta las barras anteriores a la fecha de alta (`bars_before_listing_dropped`): un emisor nuevo no hereda barras de otro. | `test_r10_05_manifest_identity_and_listing_are_enforced_and_pre_listing_bars_dropped` |
| R10-06 | alta | Los dividendos se leen siempre que exista captura; la captura debe ser de FinMind y del símbolo; un recuento del manifiesto que no coincida con las filas leídas es un error, no un silencio. | `test_r10_06_dividend_captures_are_always_read_and_checked` |
| R10-07 | alta | El recorrido respeta `cfg.end`: nada posterior al límite se ejecuta ni se consulta; tener más datos archivados que el periodo pedido produce el mismo resultado. La valoración final se hace en el límite. | ídem R09-06 |
| R10-08 | media | `training_manifest_id` incluye el hash de las filas (corte, valor, características, etiqueta) y el hash de la configuración (características, α de la ridge, parámetros de LightGBM, semilla, objetivo), y nombra las semanas de etiqueta como semanas objetivo (`2024-W02` para el corte del 7-01-2024). | `test_r10_08_r10_09_training_manifest_identifies_rows_and_config_and_label_is_total_return` |
| R10-09 | media | La etiqueta de Q1 es el **retorno total** apertura→cierre: derechos con fecha ex en (entrada, salida], efectivo por acción y acciones nuevas por acción (valor nominal declarado), como exige el protocolo. `MODEL_ID` pasa a `…_v2`. | ídem |
| R10-10 | baja | Informe 11: 104 cortes, 103 paquetes, semana 2026-W01 pendiente con entrada ejecutada; informe 13 §3.2: el reintento ocurre en la siguiente salida semanal, no en la primera sesión con cierre. | informes 11 y 13 |

## 2. Posiciones de Astra sobre P1..P5

- **P1 (acepto con condiciones).** Condición cumplida: los rechazos recuperados ya no pueden transportar contenido arbitrario (R09-03).
- **P2 (acepto con condiciones).** Mantenido: registro de producción vacío y de sólo lectura; nada prospectivo hasta verificadores criptográficos.
- **P3 (acepto).** Las garantías acotadas del libro se mantienen y no se extienden al coordinador; las ramas `pending_outcome` y límite del periodo tienen ahora prueba propia.
- **P4 (rechazo).** Aceptado: la reserva de puestos y la entrada ocurren siempre que la sesión de entrada esté dentro del límite, y el final del periodo se respeta (R09-06, R10-07). La demo regenerada lo refleja (informe 11).
- **P5 (rechazo).** Aceptado. Formulación vigente: Q1 es un modelo de precios/volumen deliberadamente modesto; su contrato temporal (características con barras disponibles al corte; etiquetas con apertura y cierre disponibles al corte; cortes crecientes; caché versionada) está probado con contraejemplos; la etiqueta es el retorno total del protocolo; el identificador del entrenamiento identifica filas y configuración. Sus resultados sobre la muestra (informe 14) no distinguen de cero y no se presentan como evidencia de rentabilidad.

## 3. Respuestas a las preguntas del revisor

1. **Cortes decrecientes y caché.** Un corte anterior al último visto se rechaza (R10-02; uno igual se admite) y la caché está versionada por datos (R10-03); una instancia de `TabularForecaster` no se reutiliza entre recorridos.
2. **Objetivo de retorno total.** Se conserva el de la especificación: Q1 v2 etiqueta con retorno total (R10-09); no se registra ninguna versión con retorno de precio.
3. **Semanas pendientes y `end`.** Regla: límite = mín(`end`, último dato); entrada dentro del límite → se ejecuta y las posiciones quedan en seguimiento; salida fuera del límite → no se intenta; nada posterior al límite se consulta (R09-06, R10-07).

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161; registro de producción vacío.
- Catálogo de extractores reales (sin él, ningún documento prospectivo con contenido se readmite).
- Política de cierres sobrevenidos y su fuente oficial; versiones históricas del calendario con fecha de publicación.
- Adaptador de lotes menores (零股) y resolución en efectivo de fracciones.
- Maestro histórico completo; emisor con TEJ.
- Pronosticadores con LLM (L1/L2) y extractores de noticias; módulo de informe estadístico.
- Congelamiento del protocolo (costes y rotación, dimensionado, tolerancia de exposición, `block_length`, liquidez, tablero de innovación, redondeo de efectivo, plazo de registro de semanas sin sesiones). Decisión del usuario.
