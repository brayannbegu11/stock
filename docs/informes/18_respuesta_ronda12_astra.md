# Respuesta del constructor a la ronda 12 de revisión (GPT-6 Astra)

> **Vigencia.** La receta «un derecho con filas contradictorias se descarta entero» (R12-01) fue sustituida en el informe 19 por el estado **ambiguo** (el derecho se conserva e invalida etiquetas e intervalos), y la lista de campos cerrados de R09-03 se completó en los informes 19 y 20. Úsese como historial.

**Entrada:** `review/out/ronda12_verificacion_20260909T224311Z.json` (sha256 `06bee0f2…bc87`), árbol congelado e íntegro. Veredicto de Astra: **rechazado**. Verificó las correcciones de la ronda 11 (completas salvo R09-03, R10-05, R10-10 y R11-01, parciales) y produjo 4 hallazgos nuevos (R12-01..R12-04: 2 altos, 2 medios). Reprodujo el JSON de la muestra, el informe 14 y la demo; auditó 103 paquetes y 6.901 documentos.

**Salida:** todas las pruebas en verde (recuento en `README.md`); cada hallazgo tiene prueba nombrada. Las cifras de la muestra y de la demo no cambian.

## 1. Hallazgos y acción tomada

| Id | Sev. | Corrección | Prueba |
|---|---|---|---|
| R09-03 (parcial) | alta | Dos capas: (i) `PredictorView.packet()` entrega los rechazos **sin su `doc_id`** (`rejected-0`, `rejected-1`, …; motivo y detalle cerrados se conservan): el texto libre de un rechazo ya no llega al predictor; (ii) todo `doc_id`, admitido o rechazado, debe ser un identificador corto (`[A-Za-z0-9][A-Za-z0-9_:.@/-]{0,200}`): `Document` lo exige al construirse y la readmisión lo exige en los rechazos. El sello sigue cubriendo el paquete original completo (la vista del predictor no es el paquete sellado). | `test_r09_03_rejection_doc_ids_never_reach_the_predictor_and_must_be_identifiers` |
| R10-05 (parcial) | alta | `captures.delisting_date` se incorpora (y no puede contradecir `delisted`). | `test_r10_05_delisting_date_declared_in_captures_is_used` |
| R10-10 (parcial) | baja | Informe 16 §3.1: «cortes decrecientes» (un corte igual se admite), coherente con la tabla. | — |
| R11-01 (parcial) | media | La disponibilidad de una fecha de anuncio sin hora sigue ahora la política del protocolo (`derive_available_at`: apertura de la primera sesión posterior, `conservative_inference`), no «fecha + 1 día». Con hora publicada: ese instante, calificado como anuncio (`verified_original` respecto del anuncio; sin garantía de versiones, véase §3.1). `DividendLike.known_quality` lo declara. | `test_r12_01_…` (caso R11-01) |
| R12-01 | alta | **Una sola lista validada** de derechos por valor (`validated_dividend_events`, calculada al cargar el mercado y guardada en `Security.events`): la consumen el libro (`Runner.apply_actions`) y las etiquetas de Q1 (`TabularForecaster.dividends`). Un `event_id` con filas de valores distintos, o con una fila que el libro rechazaría (pago anterior a la fecha ex), se **descarta entero** y se informa en `market.warnings`; las filas idénticas repetidas cuentan una vez. El valor nominal queda fijado en el mercado (`MarketData.par_value`) y `Runner` exige que coincida con el del libro. | `test_r12_01_conflicting_rights_are_discarded_for_ledger_and_labels_alike` |
| R12-02 | alta | `marks` añade `price_predates_right:{valor}:{fecha ex}` cuando el último precio conocido es anterior a un derecho aplicado hasta la fecha de valoración; la marca se propaga a la valoración final y hace no medible el intervalo. | `test_r12_02_valuation_after_a_right_without_a_later_price_is_flagged` |
| R12-03 | media | Un bootstrap degenerado se publica con `ci95: null` (nunca NaN); los scripts serializan con `allow_nan=False`. | `test_r12_03_degenerate_bootstrap_serialises_without_nan` |
| R12-04 | media | Informe 11: el intervalo declara la observación fija (1 de 100: la semana aislada 2025-W04). | — |

## 2. Posiciones de Astra sobre P1..P5

- **P1 (rechazo).** Aceptado: `doc_id` era una vía. Cerrada por las dos capas anteriores. Queda, como contenido legítimo, lo que llevan los documentos admitidos (que es lo que el predictor debe ver).
- **P2 (acepto con condiciones).** Mantenido.
- **P3 (acepto con condiciones).** Condiciones atendidas: colisiones de derechos (R12-01) y valoración posterior a derechos con precios anteriores (R12-02).
- **P4 (acepto con condiciones).** Condición atendida: la incertidumbre por derechos procesados hasta el límite sin precio posterior se declara (R12-02).
- **P5 (rechazo).** Aceptado: Q1 y el libro consumen ahora literalmente la misma lista validada; la política de fechas sin hora es la del protocolo; la disponibilidad de revisiones de FinMind no está acreditada y se declara (§3.1).

## 3. Respuestas a las preguntas del revisor

1. **Evidencia de disponibilidad por versión en FinMind.** No la hay. `AnnouncementDate`/`AnnouncementTime` documentan el anuncio, no las revisiones posteriores de importes o fechas ex; el archivo histórico de FinMind es una instantánea actual sin versiones. Por eso los derechos se califican como disponibilidad de **anuncio** (`known_quality`), no de versión; las etiquetas que los usan son inferencia conservadora, y el archivo diario propio (desde el 9-09-2026) es el que irá acumulando versiones con `ingested_at` real. Se añade a la lista de límites de los informes 11 y 14.
2. **Política de fechas sin hora.** Se mantiene la del protocolo (`derive_available_at`: siguiente sesión); la regla «fecha + 1 día» queda retirada. No se registra un experimento distinto.
3. **Retiradas en `captures`.** Se incorporan explícitamente (R10-05) y deben coincidir con `delisted` si ambas existen.

## 4. Abierto

- Adaptadores criptográficos OpenTimestamps / RFC 3161; registro de producción vacío.
- Catálogo de extractores reales; pronosticadores con LLM (L1/L2).
- Política de cierres sobrevenidos y su fuente oficial; versiones históricas del calendario.
- Adaptador de lotes menores; maestro histórico completo; emisor con TEJ.
- Fuente oficial por fecha para precios del universo (`MI_INDEX`, `dailyQuotes`): descarga en curso; sin dividendos históricos por esa vía (FinMind gratuito limitado; alternativa oficial de derechos pendiente).
- Congelamiento del protocolo (costes y rotación, dimensionado, tolerancia de exposición, `block_length`, liquidez, tablero de innovación). Decisión del usuario.
