# Contratos de datos y aislamiento temporal

**Estado:** diseño de tablas e invariantes. No se han creado tablas financieras ni verificado datos de mercado. La versión de cada contrato debe incluirse en los manifiestos de entrenamiento e inferencia.

## 1. Tablas propuestas

| Tabla | Clave lógica | Campos mínimos y propósito |
|---|---|---|
| `security_master_version` | security_id + valid_from + recorded_at | issuer_id, símbolo, nombre original, alias, clase, bolsa, tablero, moneda, valid_to, source_id. La identidad no es el símbolo. |
| `market_session_version` | market + session_date + recorded_at | apertura/cierre con zona, estado, anuncio del calendario, motivo de cambio. Conserva el calendario conocido y el efectivo. |
| `source_contract` | source_id + contract_version | licencia, permisos, límites, campos, unidades, cobertura, esquema, responsable y fecha de auditoría. |
| `raw_document_version` | document_id + version_id | hash, localización autorizada, idioma, fuente, publicación, actualización, first_seen_at, ingested_at, available_at, evidencia de disponibilidad. |
| `filing_fact_version` | filing_id + fact_id + version_id | empresa, concepto, valor, unidad, moneda, período, publicación y revisión; distinguir consolidado/individual. |
| `price_bar_version` | security_id + session_id + bar_type + recorded_at | OHLC, volumen, importe, unidad, fuente, ajuste, fecha de disponibilidad, condición de negociación. |
| `corporate_action_version` | event_id + version_id | split/dividendo/reducción/fusión/retirada, anuncio, fecha efectiva, derechos, pago, ratios y cantidades. |
| `entity_relationship_version` | relation_id + version_id | empresa origen/destino, relación, exposición conocida o no cuantificada, documentos de respaldo y vigencias. |
| `event_extraction` | document_version + extractor_version + event_index | entidades, tipo de hecho, cifras, fechas, texto de soporte permitido, contradicciones, estado de revisión humana. |
| `feature_snapshot` | security_id + cutoff_at + feature_set_version | variables, masks de ausencia, fuentes, versiones auxiliares y máxima disponibilidad de entradas. |
| `training_manifest` | training_run_id | ventanas, hash de filas/columnas, etiquetas maduras, transformaciones, semillas, características contaminadas o limpias, versión de código. |
| `information_packet` | packet_id | corte, archivos permitidos, universo, características, datos faltantes, hashes y clase de evidencia temporal. |
| `prediction_registry` | forecast_id | contrato adjunto, salida original, parámetros, modelos solicitado/devuelto, hora de emisión, sello externo y estado. No contiene resultados. |
| `paper_ledger_event` | ledger_id + event_sequence | entrada/salida simulada, coste, impuesto, efectivo, posición, derechos y eventos pendientes. |
| `outcome_label` | security_id + forecast_horizon + label_version | extremos de tiempo, retornos, madurez, precios usados, evento terminal y calidad. Acceso separado del predictor. |
| `evaluation_run` | evaluation_id | predicciones cerradas, versión del libro, referencias, métricas, intervalos, exclusiones y registro de todos los ensayos. |

## 2. Invariantes temporales

`period_end` expresa a qué período pertenece el dato; nunca establece cuándo fue conocido. Una versión corregida no borra la anterior. El registro conserva cuándo el sistema supo algo y cuándo la fuente lo hizo público.

Para una reconstrucción histórica, el paquete exige evidencia de disponibilidad pública antes del corte; una fecha de descarga reciente sigue siendo reciente. Para una predicción prospectiva, la observación debe además haber llegado al sistema antes del corte. Una previsión emitida antes del resultado pero alimentada con un dato recibido después del corte incumple el protocolo.

Todas las operaciones de tiempo usan zonas explícitas; las fechas de sesión no reemplazan timestamps. Un dato de otro país con el mismo día del calendario puede corresponder al futuro respecto de la apertura taiwanesa. No se utiliza automáticamente su cierre «del mismo día».

Si se dispone sólo de fecha, la política conservadora queda registrada. La ausencia de hora no se transforma en una hora inventada favorable. Se conserva `availability_quality` y la justificación.

El calendario de eventos futuros se versiona: se puede conocer la fecha anunciada de un resultado, no su valor posterior. Las cancelaciones o aplazamientos tienen su propia disponibilidad.

## 3. Invariantes de lenguaje y cifras

Guardar unidad y moneda por campo, no solamente por tabla. Conservar fragmento original autorizado para verificar cantidades. Las conversiones se prueban con positivos, negativos, porcentajes, cantidades en miles/millones y abreviaturas locales. Los nombres similares requieren resolver emisor y clase, no coincidencia aproximada sin control.

Un documento puede respaldar que ocurrió un anuncio, pero no necesariamente que favorecerá la cotización. Separar `factual_claim` de `impact_hypothesis`. El primero requiere referencia verificable; el segundo se etiqueta como inferencia y después se evalúa.

No rellenar porcentajes de exposición empresarial por analogía. No tratar copias de una noticia como corroboraciones independientes. Una corrección contradictoria es información nueva, no permiso para sustituir el registro antiguo.

## 4. Invariantes de entrenamiento

Cualquier traductor, extractor, embedding o grafo aprendido es parte de la cadena de modelos. Su fecha y entrenamiento deben figurar en la clasificación de evidencia. La rama numérica histórica «limpia» no puede usar una etiqueta textual generada con conocimiento posterior y mantener esa etiqueta de limpieza.

Los conjuntos de entrenamiento, validación y prueba se separan por tiempo antes de ajustar transformaciones. Las etiquetas que terminan después del corte del entrenamiento no están maduras. Purga y separación consideran el final real del horizonte, incluidos eventos no resueltos.

El identificador de la empresa puede actuar como una pista de memoria; se registra su uso y se ensaya una variante sin identidad como diagnóstico. Un resultado de anonimización no garantiza por sí mismo ausencia de memoria.

## 5. Invariantes contables

Los dividendos y acciones corporativas se aplican exactamente una vez. Los niveles de precios nominales y ajustados nunca se mezclan en un mismo cálculo sin transformación explícita. Los costes recaen sobre el importe y sentido del evento simulado.

Las posiciones suspendidas permanecen abiertas hasta su resolución bajo la política del experimento. No se reutiliza efectivo inmovilizado. Una retirada no autoriza a borrar el emisor de la muestra. Los resultados no resueltos llevan banderas y límites de valoración declarados.

La vista de señal con fracciones ideales no afirma capacidad de ejecución. La vista con importes concretos necesita reglas de lotes, participación, efectivo, liquidación y gastos mínimos. Comparadores deben usar el mismo modelo cuando se evalúa selección.

## 6. Seguridad y límites de acceso

El predictor sólo lee `information_packet` y sus objetos autorizados. No tiene herramientas para inspeccionar `outcome_label`, carpetas de resultados o datos posteriores. El evaluador no puede editar predicciones selladas. Los procesos no ejecutan instrucciones incluidas en documentos ajenos.

Se guardan respuestas y argumentos disponibles, no se exige exponer razonamiento privado. Un hash asegura integridad relativa; el sello temporal debe venir de una fuente independiente del campo editable de la predicción.

## 7. Cálculos de evaluación

Para cada semana, H1 y Q1 se comparan con período y exposición emparejados. La trayectoria completa se calcula desde el libro de posiciones y efectivo. La media de rendimientos de nombres seleccionados se muestra como otra estadística, no se confunde con la cartera cuando existen huecos o entradas fallidas.

El Formosa total return al cierre permite comparación de patrimonio diaria, sujeto a validación del conjunto. El período apertura–cierre necesita datos equivalentes o un comparador propio con esos mismos extremos. No sustituir la apertura por el cierre previo para mejorar resultados.

Las corridas inválidas permanecen en el registro de cobertura; el panel debe mostrar qué cambia al condicionarse a corridas válidas. Los resultados de miles de trayectorias aleatorias son simulaciones condicionadas al archivo existente, no observaciones independientes del mercado.
