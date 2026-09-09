# Respuesta del constructor a la ronda 11 de revisión (GPT-6 Astra)

**Entrada:** `review/out/ronda11_verificacion_20260909T222136Z.json` (sha256 `abd77e9f…7093`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Verificó las correcciones de la ronda 10 (R10-04 y R10-01 completas; R09-03, R09-12, R10-03, R10-05, R10-06, R10-07, R10-08, R10-09, R10-10 parciales; R10-02 con matiz de redacción) y produjo 5 hallazgos nuevos (R11-01..R11-05: 2 altos, 3 medios). Reprodujo el JSON de la muestra, el informe 14 y la demo; auditó 103 paquetes y 6.901 documentos sin barras posteriores al corte.

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada hallazgo tiene prueba nombrada. Las cifras de la muestra (informe 14) y de la demo (informe 11) no cambian con estas correcciones (la muestra no contiene dividendos duplicados ni anunciados después de su fecha ex).

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R09-03 (parcial) | alta | Plantillas de rechazo **cerradas**: sólo texto fijo e instantes ISO. `build_packet` ya no escribe nombres de extractor, clases de excepción, identidades ni hashes en los detalles; «extractor failed», «security_ids do not equal the extracted identities», etc. Un detalle con cualquier otro texto impide la readmisión. | `test_r09_03_rejection_details_must_be_build_packet_templates` |
| R09-12 (parcial) | alta | Un remuestreo en el que toda la muestra es fija (todos los tramos ≤ `block_length`) se declara **degenerado**: `BootstrapResult.degenerate = True`, límites NaN, media y recuentos válidos; nunca se publica como IC 95 %. Con parte fija se informa `n_fixed_observations` / `variability_limited`, y el informe markdown lo muestra. | `test_r09_12_degenerate_resampling_is_declared_not_published_as_an_interval` |
| R10-03 (parcial) | media | La clave de la caché incluye la versión del calendario (`source_id@version`) además de la versión de datos. | `test_r10_03_cache_is_keyed_by_calendar_version_too` |
| R10-05 (parcial) | alta | `load_market` valida también `listed`/`delisted`: símbolos repetidos, `security_id`/`market` declarados allí, `listing_date` de `delisted` frente a `listed`; todo lo declarado debe coincidir con lo reconstruido. | `test_r10_05_listed_and_delisted_declarations_are_checked_too` |
| R10-06 (parcial) | alta | Un `dividend_rows` positivo sin captura de dividendos es `ManifestInconsistent`. | `test_r10_06_dividend_captures_are_always_read_and_checked` |
| R10-07 (parcial) | alta | La rama `invalid:no_sessions` procesa eventos y valora sólo hasta el límite (mín(fin, último dato)); si empieza después del límite, sólo se registra. Los cierres de la sesión de salida no se consultan cuando la salida está pendiente. | `test_r10_07_invalid_week_beyond_the_bound_is_not_processed` |
| R10-08 (parcial) | media | El hash de las filas usa la representación exacta de coma flotante (sin redondeo): diferencias que cambian un rango cambian el identificador. | `test_r10_08_r10_09_…` (etiquetas 1e-12) |
| R10-09 (parcial) | alta | `weekly_label` encadena los derechos en orden (fecha ex; efectivo antes que acciones el mismo día, como el libro) sobre la cantidad vigente: acciones 1:1 y luego 10 TWD por acción → +20 %. | `test_r10_09_r11_01_r11_02_chained_rights_duplicates_and_announcement_availability` |
| R10-10 (parcial) | baja | Informe 11: la introducción dice 103 paquetes; informe 16: «cortes decrecientes». | — |
| R11-01 | alta | `DividendLike.known_at`: hora de anuncio si existe; fecha de anuncio sin hora → día siguiente 00:00 Taipei; sin anuncio → desconocido, y la etiqueta de esa semana no existe. `label_known_at` es el más tardío entre barras y derechos; una etiqueta con un derecho anunciado después del corte de entrenamiento no madura. | ídem |
| R11-02 | alta | `DividendLike.event_id` con la misma identidad que el libro (`{sec}:cash|stock:{ex}:{periodo}`); un evento repetido cuenta una sola vez. | ídem |
| R11-03 | media | `Runner` rechaza un pronosticador cuyo `par_value` difiera del de la configuración del libro. | `test_r11_03_r11_04_forecasters_must_share_market_and_par_value_with_the_runner` |
| R11-04 | media | `Runner` rechaza un pronosticador ligado a otro `MarketData` (identidad del objeto): una instancia de Q1 sirve a un recorrido sobre su mercado. | ídem |
| R11-05 | media | `markdown_report` conserva los estados de incertidumbre: patrimonio desconocido, exceso no estimable o degenerado, intervalo no medible por precio obsoleto frente a pendiente. | `test_r11_05_markdown_report_keeps_uncertainty_states` |

## 2. Posiciones de Astra sobre P1..P5

- **P1 (rechazo).** Aceptado: las plantillas transportaban identidades y nombres. Ahora los detalles son texto cerrado; el predictor no puede recibir contenido por esa vía.
- **P2 (acepto con condiciones).** Mantenido.
- **P3 (acepto).** Mantenido; la deduplicación de eventos ahora también rige en Q1 (R11-02) y el coordinador respeta el límite en la rama sin sesiones (R10-07).
- **P4 (rechazo).** Aceptado: la rama `invalid:no_sessions` rebasaba el límite y el coordinador consultaba cierres futuros al construir `close_prices`. Corregido y probado; la formulación de «nada posterior se consulta» se limita ahora a lo probado: precios, eventos y valoraciones se detienen en el límite de simulación.
- **P5 (rechazo).** Aceptado: la etiqueta de Q1 tiene ahora disponibilidad e identidad de derechos, encadenamiento correcto y el mismo valor nominal que el libro; la caché distingue calendario; el identificador de entrenamiento no redondea. Sigue siendo un modelo modesto sin evidencia de rentabilidad.

## 3. Respuestas a las preguntas del revisor

1. **Identidad, versión y disponibilidad de cada acción corporativa.** Identidad = `event_id` del libro (`{security}:{cash|stock}:{fecha ex}:{periodo}`); disponibilidad = instante de anuncio (hora si existe, fecha + 1 día si no, desconocido si falta); versión = la captura de FinMind de la que procede (parte de `MarketData.data_version`, que a su vez versiona la caché de Q1). Libro, etiquetas y caché consumen la misma lista `dividend_events`.
2. **Bootstrap sin variabilidad.** Se declara como incertidumbre no estimable: `degenerate=True`, límites NaN, media y recuentos válidos; el informe lo muestra como «incertidumbre no estimable: remuestreo degenerado». No es un error de diseño del evaluador sino un diseño experimental insuficiente, y así se comunica.

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161; registro de producción vacío.
- Catálogo de extractores reales; pronosticadores con LLM (L1/L2).
- Política de cierres sobrevenidos y su fuente oficial; versiones históricas del calendario.
- Adaptador de lotes menores; maestro histórico completo; emisor con TEJ.
- Fuente oficial por fecha para el histórico de todo el universo (FinMind gratuito limita a ~300 peticiones/hora): endpoints heredados `MI_INDEX` (TWSE) y `dailyQuotes` (TPEx) en evaluación.
- Congelamiento del protocolo (costes y rotación, dimensionado, tolerancia de exposición, `block_length`, liquidez, tablero de innovación). Decisión del usuario.
