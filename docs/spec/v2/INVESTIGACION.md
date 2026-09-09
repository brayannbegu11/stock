# Inteligencia bursátil de Taiwán con IA
## Investigación y especificación de construcción — versión 2.0

**Fecha de revisión de fuentes: 9 de septiembre de 2026.**  
**Alcance confirmado:** todo el mercado de acciones ordinarias de TWSE y TPEx; información internacional como contexto y señales. PCB es solamente un ejemplo histórico de la conversación, no un filtro, una prioridad ni el punto de partida del sistema.  
**Estado:** investigación documental y diseño. No se ha descargado el universo financiero completo, entrenado un modelo, ejecutado un backtest, calculado una clasificación actual de acciones ni activado un servicio de actualización.  
**Uso inicial:** investigación privada, lectura y carteras simuladas, sin conexión a intermediarios ni órdenes reales.  
**Documento sucesor:** sustituye el alcance y las decisiones provisionales de `Investigacion_laboratorio_bursatil_IA.md`. No añade otro módulo de PCB al diseño anterior: cambia su planteamiento principal.

Las referencias `[Sxx]` remiten al registro de fuentes incluido al final y a `FUENTES.json`. Una especificación propuesta no es un resultado experimental. Los precios, políticas de proveedores y calendarios se deberán volver a comprobar al implementar.

---

## 1. Decisión ejecutiva

**Recomiendo construir un laboratorio vivo de inteligencia de mercado, con una arquitectura híbrida y una evaluación prospectiva desde su puesta en marcha.** No recomiendo empezar entrenando un modelo gigantesco ni preguntar a dos asistentes cuáles serán las cinco acciones ganadoras y aceptar su consenso como validación.

El sistema debe producir dos bienes diferentes. El primero es informativo: mantener un mapa de empresas, documentos, eventos y cambios de contexto. El segundo es experimental: comprobar si esas observaciones permiten ordenar mejor las acciones para un horizonte definido, frente a alternativas sencillas y después de costes.

La utilidad del primero se puede medir mediante cobertura, exactitud y ahorro de revisión. La rentabilidad del segundo no está demostrada para este proyecto. Construir un producto útil no exige inventar una ventaja predictiva; demostrar una ventaja exige algo más que un buen producto informativo.

**La vía recomendada:** datos temporales verificables → variables numéricas para todo el universo → extracción de eventos mediante IA → modelo tabular propio que combine señales → clasificación y explicación → cartera simulada y evaluación independiente.

Fable 5.1 y Astra son buenos candidatos para construir, revisar y analizar documentos. Su posición exacta dentro del pronosticador tiene que ganarse experimentalmente. No se presupone que el modelo con mejor capacidad general sea el mejor estimador de rendimientos taiwaneses.

## 2. Qué significa analizar «todo el mercado»

### 2.1 Universo y límites explícitos

La cobertura base incluirá las acciones ordinarias de **TWSE y TPEx**, de todos los sectores. Se identificarán tableros, emisores extranjeros de cotización primaria, clases de acciones y cambios de mercado. Los directorios oficiales de ambas bolsas y un maestro histórico serán la autoridad, no una lista manual de empresas conocidas. [S01–S02, S07–S08]

No se excluyen bancos, aseguradoras, comercio, transporte, construcción, alimentos, turismo, materiales o servicios por tener menos relación con la narrativa tecnológica. Las métricas que no sean económicamente comparables entre industrias se tratarán por separado; no se eliminará una industria entera para facilitar el modelo.

El mercado emergente **ESB/興櫃** se catalogará como cobertura adicional, pero su inclusión en la simulación requerirá un adaptador y pruebas propios. No se debe presentar un estudio de TWSE/TPEx como si certificara todos los instrumentos de todos los segmentos. Los fondos, warrants y derivados quedan fuera de la cartera inicial; no son acciones ordinarias intercambiables.

El número de emisores cambia con el tiempo. Este documento no afirma haber contado el censo actual ni propone un número fijo de 500 empresas. Cada fecha tendrá su propio universo elegible, incluyendo compañías posteriormente retiradas.

### 2.2 Cuatro coberturas distintas

| Capa | Qué significa | Qué debe mostrar la interfaz |
|---|---|---|
| Censo | Instrumentos identificados en cada fecha y segmento. | Total, nuevas altas, bajas, cambios de mercado. |
| Análisis numérico | Empresas para las que se pueden calcular las variables requeridas. | Porcentaje con datos completos y motivos de ausencia. |
| Análisis documental profundo | Empresas/eventos revisados con modelos de mayor coste. | Qué se revisó realmente, cuándo y con qué fuentes. |
| Elegibilidad de simulación | Empresas con datos y condiciones suficientes para una ejecución simulada defendible. | Exclusiones por historial, liquidez, suspensión u otros motivos. |

Una empresa puede estar en el censo y tener información útil, pero carecer de historial para el modelo principal. Una empresa ilíquida puede analizarse sin simular una entrada irreal. Una empresa sin noticia reciente no debe recibir automáticamente una puntuación negativa.

### 2.3 No convertir el coste computacional en un sesgo oculto

Se calculará la capa numérica para todas las empresas cubiertas. Se procesarán y deduplicarán los documentos nuevos autorizados, asignándolos a empresas y eventos. El análisis caro se priorizará por novedad, desacuerdo, relevancia y señales numéricas; incluirá una muestra de control de empresas menos conocidas y de distintos sectores.

La cola de revisión profunda es una asignación de recursos, no una redefinición secreta del universo. Se conservará una clasificación numérica de respaldo para empresas sin revisión profunda. El sistema indicará explícitamente cuándo una explicación es parcial.

No será obligatorio encontrar un «tema caliente» antes de examinar una empresa. Los temas surgirán como agrupaciones dinámicas del flujo de eventos. La estrategia temática original se conservará como un experimento separado.

## 3. ¿Es predecible? Estado de la evidencia y límites

### 3.1 Cuatro afirmaciones que no deben confundirse

**Comprensión:** el modelo identifica correctamente que una empresa anunció un dato nuevo. **Interpretación:** propone un mecanismo plausible de impacto. **Predicción:** esa información mejora el pronóstico frente a una referencia. **Ventaja económica:** la mejora sobrevive a precios realmente disponibles, costes y restricciones.

Una explicación precisa puede no aportar predicción. Un pronóstico acertado puede describir un movimiento que ocurrió antes de poder entrar. Una mejora estadística pequeña puede desaparecer al descontar costes. La aplicación debe medir los cuatro niveles, no saltar del primero al último.

### 3.2 Evidencia primaria pertinente

| Línea de investigación | Qué aporta | Qué no demuestra para este proyecto |
|---|---|---|
| Gu, Kelly y Xiu: aprendizaje automático en valoración de activos. [S27] | Justifica comparar métodos supervisados para rendimientos y relaciones no lineales. | Una ventaja semanal generalizable automáticamente a Taiwán. |
| Lopez-Lira y Tang: interpretación de titulares. [S23] | Muestra que el texto puede contener señales predictivas en la tarea estudiada. | Que cinco acciones elegidas por un asistente superen costes y mercado cada semana. |
| Liao y colaboradores, 2026: fusión de noticias y precios. [S28] | Modelo compartido entre empresas; muestra taiwanesa de seis acciones seleccionadas. | Cobertura de todo Taiwán o rentabilidad neta demostrada; reducir error de precio no equivale a ganar dinero. |
| Chen y Pu, 2026: pronósticos prospectivos estadounidenses. [S29] | Evidencia preliminar prometedora de predicciones registradas antes del resultado. | Validación independiente de nuestro horizonte, universo, fuentes y ejecución. |
| Crisostomo y Mykhalyuk, 2026. [S30] | Documenta problemas de razonamiento e información y la importancia de fuentes y supervisión. | Que un diálogo autónomo de agentes sea suficiente. |
| FinVerse, agosto de 2026. [S31] | Refuerza la necesidad de evaluar utilidad financiera y no sólo error convencional de series. | Que un modelo destacado en un benchmark sea una estrategia lista para usar. |

No se han reproducido aquí los experimentos de esos trabajos. Algunas referencias son prepublicaciones y sus conclusiones requieren la cautela correspondiente. No hay una prueba localizada que coincida exactamente con «todo TWSE y TPEx, noticias chinas e internacionales, cinco nombres semanales, modelos actuales, costes locales y pruebas prospectivas».

**Juicio:** existe fundamento suficiente para investigar, pero no para declarar una tasa de acierto o una rentabilidad esperada del sistema antes de medirlas.

### 3.3 Qué pedir al pronosticador

El objetivo principal será ordenar empresas por rendimiento relativo esperado durante un horizonte concreto. Las probabilidades se mostrarán sólo cuando exista un calibrador evaluado fuera de su muestra de ajuste. No se aceptará un «87% de confianza» escrito libremente por un asistente como probabilidad validada. [S37]

Se distinguirán `score_de_ranking`, `probabilidad_calibrada`, `fuerza_documental` y `riesgo_estimado`. Una fuente muy fiable puede comunicar un hecho cuyo efecto bursátil sea incierto. La interfaz no combinará esas dimensiones en un porcentaje ambiguo.

Como ejemplo matemático, acertar el 55% de las veces ganando 1% y perder el 45% restante perdiendo 2% da una media de −0,35% antes de costes. No es una observación del mercado: ilustra por qué el porcentaje de aciertos no basta.

## 4. Actualidad verificada al 9 de septiembre de 2026

La revisión incluyó fuentes y publicaciones de 2026, no solamente referencias históricas. Dos ejemplos permiten convertir la exigencia de actualidad en pruebas concretas.

**Publicación ya fechada hoy:** el Ministerio de Finanzas publicó el resumen de comercio exterior de agosto de 2026, con exportaciones de 82.400 millones de USD y crecimiento interanual del 41,0%. La página está fechada el 9 de septiembre. No se verificó su hora intradía; por ello, no es admisible asumir que el dato estaba disponible antes de la apertura de hoy. [S19]

**Evento futuro conocido, resultado aún no disponible en el corte de consulta:** el calendario de TSMC situaba la publicación de ingresos de agosto el 10 de septiembre de 2026. El sistema puede conocer el evento programado, pero no usar anticipadamente el ingreso que se publicará. La página también advierte que las fechas pueden cambiar. Es un ejemplo temporal, no una selección bursátil ni un foco sectorial del proyecto. [S20]

La política general será conservar el calendario conocido entonces y sus revisiones. Si un evento se aplaza, el sistema registrará la actualización; no corregirá el pasado para fingir que siempre supo la fecha final.

**Actualizado** significará que cada observación muestra su fecha y hora de disponibilidad, versión y retraso. No significará que el modelo lleva un nombre reciente, ni que navegar una vez al día garantiza que se han visto todas las noticias.

## 5. Mapa de datos y preguntas que deben responder

### 5.1 Base de mercado

El maestro de valores conservará un identificador interno estable, emisor, clase, símbolo, nombres en chino e inglés, bolsa, tablero, moneda y períodos de vigencia. Las altas, retiradas, fusiones y cambios de mercado no se resolverán concatenando símbolos actuales.

Las cotizaciones incluirán precios sin ajustar, volumen e importe con unidades explícitas, sesiones y estados de negociación. Los eventos corporativos se mantendrán en una tabla separada. El rendimiento total procederá de un libro contable o de una serie coherente verificada, sin contar dividendos dos veces.

Variables iniciales propuestas: rendimientos previos de 1, 5, 20, 60 y 120 sesiones; fuerza relativa; volatilidad; volumen e importe relativos; rotación; distancia a extremos anteriores y concentración sectorial. No se presupone que todas tengan capacidad predictiva. Los filtros y transformaciones se ajustarán sólo con datos de entrenamiento.

### 5.2 Información empresarial taiwanesa

Se priorizarán ingresos mensuales, estados financieros, anuncios materiales, ampliaciones de capital, recompras anunciadas, dividendos, cambios de dirección y calendarios de resultados. Cada hecho tendrá el momento de publicación, no solamente el mes o trimestre al que se refiere.

TEJ describe la divulgación ordinaria de ingresos mensuales hasta el día 10 y una excepción desde 2026 para aseguradoras y determinadas entidades con filiales de seguros, hasta el 15. Por ello, la regla de calendario no se debe aplicar ciegamente a todos los emisores. Su documentación también distingue el dato original de revisiones posteriores. [S15]

Para bancos y aseguradoras se diseñarán variables propias o normalizaciones sectoriales. Los ingresos industriales, el negocio financiero y sus cambios contables no se considerarán idénticos por compartir una columna llamada «revenue». Se registrará cualquier ruptura de comparabilidad antes de interpretar un salto como crecimiento.

Las sorpresas frente a expectativas necesitan un consenso o pronóstico que ya existiera antes del anuncio. Sin ese archivo, se hablará de comparación con el historial propio, no de «sorpresa frente al mercado».

### 5.3 Flujos y tenencias

Se evaluarán flujos agregados de extranjeros, fondos y operadores, cuando el conjunto y su publicación estén verificados. TWSE publica estadísticas de esas categorías. Las distribuciones de tenencias de TDCC pueden ampliar el contexto, sin tratar sus agregados como identidad o intención de inversores concretos. [S01, S16]

No se atribuirá automáticamente información privilegiada a una compra institucional ni se usará el dato del cierre antes de su publicación. El valor de estas variables se decidirá mediante una comparación con y sin ellas.

### 5.4 Noticias, lenguaje y eventos

La unidad preferida será el **evento deduplicado**, con documentos de soporte, no cada copia de un titular. Se extraerán empresa, tipo de hecho, cifras, unidades, dirección económica hipotética, fecha, novedad y contradicciones. Los rumores se marcarán y se mantendrán separados de divulgaciones confirmadas.

El procesamiento conservará el texto original en chino tradicional, cuando lo permita la licencia, junto a una traducción opcional. Los identificadores y cantidades se normalizarán mediante reglas comprobadas; se crearán pruebas para calendarios locales, nombres alternativos y unidades como 萬, 億, 張 y 股. La normalización nunca borrará el original.

No se equiparará atención a beneficio. Un tema puede crecer porque apareció un problema. El modelo debe distinguir proveedor, cliente, competidor y exposición indirecta; no inventar relaciones ni porcentajes de ingresos temáticos.

### 5.5 Información internacional

La primera extensión internacional será informativa: clientes y competidores extranjeros, anuncios sectoriales, demanda por región, divisas, tipos de interés, energía y materias primas. EDGAR y ALFRED son fuentes a evaluar para divulgaciones estadounidenses y versiones macroeconómicas. [S17–S18]

Cada relación internacional debe tener evidencia y vigencia. La dependencia de un cliente documentada en 2026 no puede introducirse automáticamente en una predicción de 2021. Un movimiento de otro mercado sólo estará disponible tras su hora real; un emparejamiento por fecha sin zonas horarias puede introducir el futuro.

No se mezclará inicialmente una acción estadounidense con una taiwanesa en una media sin moneda, horario y costes comunes. Cuando se añadan acciones extranjeras al portafolio simulado, tendrán un experimento y un libro propios, más una conversión de moneda explícita para una vista consolidada.

## 6. Fuentes recomendadas y estrategia de adquisición

### 6.1 Paquete oficial y de prototipo

TWSE, TPEx y MOPS forman la base de contraste oficial. Sus APIs y páginas deben probarse en muestras reales: un endpoint visible en un catálogo no garantiza que devuelva todas las versiones, que tenga la latencia necesaria ni que autorice cualquier redistribución. Algunas páginas consultadas dependen de carga dinámica o presentaron errores de acceso. [S07–S09]

FinMind es un candidato útil para acelerar la ingestión de cotizaciones y fundamentales. Su documentación distingue conjuntos y acceso a determinadas consultas masivas. Se verificará la profundidad real, la información de retiradas y la publicación original de cifras; no se deducirá seguridad temporal del nombre de una tabla. [S10–S12]

Una precaución concreta: FinMind documenta precios ajustados recalculados retrospectivamente. Por diseño, no usaremos el nivel de una serie ajustada descargada hoy como si fuera el precio nominal conocido años atrás. Esa distinción importa en filtros, eventos corporativos y comprobaciones de ejecución. [S10]

### 6.2 Candidato de datos históricos profesionales

Solicitaría a TEJ una muestra y cotización para **TWSE y TPEx**, con maestro histórico, retiradas, cotizaciones, eventos corporativos, ingresos mensuales y estados financieros con publicación y revisiones. Su documentación describe soluciones pertinentes, pero no se ha confirmado el paquete exacto, su precio ni los permisos que necesitará el proyecto. [S13–S14]

La cobertura de datos financieros no presupone un archivo periodístico completo. Hay que preguntar separadamente por originales de noticias, sus correcciones, cuerpos de texto, fechas y derechos para enviarlos a APIs externas.

TEJ API, Tool API y TQuant Lab pueden reducir trabajo de integración, pero tampoco sustituyen los casos de prueba del proyecto. Una biblioteca o backtester de un proveedor es una opción técnica, no un certificado de ausencia de sesgo. [S46]

### 6.3 Qué exigir antes de contratar

La muestra debe contener una empresa retirada, un cambio de mercado, una revisión de ingresos, un dividendo, una división de acciones, una suspensión, un festivo/cierre extraordinario y una noticia corregida. Se compararán campos y tiempos contra documentos primarios.

La licencia debe aclarar almacenamiento, uso privado compartido, entrenamiento, envío de textos a proveedores de IA, retención después de cancelar, distribución de resultados derivados y eventual uso comercial. No se eludirán barreras de acceso ni se asumirá que «público en la web» significa reutilizable sin condiciones.

La elección final se hará por cobertura temporal, integridad, coste total de trabajo y derechos; no solamente por la cuota mensual más baja. Hasta terminar esta auditoría, el estado del proveedor será `candidate`, no `validated`.

## 7. Control temporal: la parte no negociable

### 7.1 Tiempo del hecho, publicación y captura

Cada registro conservará al menos `event_at`, `period_end`, `published_at`, `version_available_at`, `first_seen_at`, `ingested_at` y `recorded_at`, con zona horaria cuando corresponda. `available_at` será un campo derivado de una política y una evidencia, no una fecha conveniente inventada.

En una reconstrucción histórica, una captura de 2026 puede contener una publicación antigua verificable; no se falsifica `ingested_at` para convertirla en una captura de 2021. En operación prospectiva, además de ser público antes del corte, el dato debe haber llegado al sistema antes de ese corte.

Las revisiones se guardarán como nuevas versiones. Consultar «qué podía saberse entonces» y consultar «qué creemos hoy que era correcto» serán dos operaciones distintas. Si sólo se conserva el artículo corregido posteriormente, no se tratará como su versión original.

Una fecha sin hora no se convertirá automáticamente en las 00:00. La política conservadora propuesta será admitirla desde la siguiente sesión o desde una hora posterior verificada, marcando esa inferencia y evaluando su sensibilidad por separado.

### 7.2 Separación de responsabilidades

El constructor de paquetes filtra los datos antes de entregarlos al predictor. El predictor histórico no tendrá navegación abierta ni permisos sobre precios futuros, resultados, etiquetas o experimentos posteriores. Cada fecha usará un contexto independiente.

El evaluador leerá resultados sólo después de guardar la predicción. El modelo no calculará su propia rentabilidad, no corregirá el motor y no podrá modificar una predicción sellada. Los documentos externos se tratarán como datos no confiables, nunca como instrucciones del agente.

Se conservarán contenido autorizado, identificadores, hashes, versiones de código y respuesta original. Una huella criptográfica detecta cambios respecto de un registro, pero no demuestra por sí sola la fecha de existencia: se necesita también un registro temporal independiente o almacenamiento de sólo anexado con garantías pertinentes.

### 7.3 La memoria interna no se resuelve con filtros

Los estudios sobre anticipación de información y memorización muestran que ocultar nombres o pedir «actúa como si fuera 2021» no garantiza eliminar conocimiento posterior. Eso afecta también a resúmenes, traducciones y representaciones de texto generadas por modelos nuevos. [S24–S25]

Las fichas consultadas sitúan el corte de Fable 5.1 en junio de 2026 y el de Astra el 30 de abril de 2026. Esos modelos pueden participar en reconstrucciones anteriores, pero sus resultados deberán etiquetarse como **exploratorios con posible contaminación del entrenamiento**. [S42–S43]

El ajuste posterior de un modelo actual con textos antiguos no certifica que haya olvidado el futuro. Para evidencia histórica más limpia proponemos dos alternativas: modelos numéricos entrenados únicamente con información temporal permitida, sin características textuales contaminadas; o componentes de lenguaje cuyo entrenamiento completo respete los cortes, como la línea investigada con modelos cronológicamente consistentes. [S26]

El registro prospectivo, iniciado después de congelar el protocolo, será la prueba principal de los modelos actuales. No se denominarán «prospectivas» predicciones sobre enero–agosto de 2026 generadas hoy.

## 8. Todas las familias de solución relevantes

| Ruta | Papel posible | Recomendación |
|---|---|---|
| Reglas transparentes y estudios de eventos | Establecer comparaciones y entender patrones. | Obligatoria desde el inicio. |
| Prompt directo a un LLM | Reproducir la idea original. | Comparador, no arquitectura principal. |
| LLM con documentos filtrados por fecha | Interpretar y justificar con fuentes. | Construir después de la capa de datos. |
| Modelo tabular propio | Aprender una clasificación común entre empresas. | Primera vía de entrenamiento recomendada. |
| Híbrido de variables numéricas y eventos | Medir contribución incremental del texto. | Arquitectura principal propuesta. |
| Adaptación de un encoder/LLM pequeño | Extraer hechos en chino tradicional de forma consistente y económica. | Tras crear un conjunto humano de evaluación. |
| Modelos de series temporales preentrenados | Comparador numérico adicional. | Ensayo acotado; auditar preentrenamiento y objetivos. |
| Modelos de grafos y cadenas de suministro | Compartir señales entre entidades relacionadas. | Posterior, sólo con relaciones temporales respaldadas. |
| Debate multiagente | Contrastar hipótesis o producir un tratamiento de consenso. | Opcional y con presupuesto igualado. |
| Ensambles y modelos de regímenes | Combinar modelos o adaptar pesos al contexto. | Después de comprobar estabilidad individual. |
| Aprendizaje por refuerzo o bandidos | Experimentos de asignación y decisiones secuenciales simuladas. | No prioritario; depende demasiado de un simulador fiable. |
| Preentrenamiento desde cero | Controlar corpus, objetivos y cronología. | Posible, pero no justificado para el producto inicial. |

Estas rutas no son intercambiables. Un extractor especializado no necesita aprender a pronosticar rendimientos; un modelo que ordena acciones no necesita generar prosa; un revisor de código no necesita decidir una cartera.

### 8.1 Primera opción: modelo tabular

Usaría un modelo lineal regularizado como control y LightGBM como candidato no lineal. LightGBM dispone de objetivos de regresión y clasificación/ordenamiento que deben elegirse según la etiqueta definida; no se escogerá la función que más favorezca el período reservado. [S36]

No propongo miles de modelos independientes, uno por acción. La primera prueba entrenará un modelo compartido, con una fila por empresa y corte, para aprender relaciones comunes. Se estudiará por separado si la identidad explícita del emisor mejora generalización o facilita memorizar nombres.

### 8.2 Adaptación de lenguaje, no «entrenar a Astra»

La ficha actual de Astra indica que **no admite fine-tuning**. Por tanto, entrenar modelos propios no significa modificar automáticamente sus pesos por API. Se puede mantener Astra como analista/revisor y entrenar otro componente compatible. [S43]

LoRA y QLoRA son rutas de adaptación eficiente para modelos adecuados. Su uso se orientaría primero a entidades, cifras, eventos, postura de las fuentes y contradicciones, no a enseñar al modelo a repetir listas de acciones que después subieron. La selección de checkpoint, permisos y memoria requiere una prueba real. [S38–S39]

Una propuesta de arranque es etiquetar manualmente entre 500 y 1.000 documentos representativos como conjunto de evaluación, incluyendo sectores no tecnológicos, errores y revisiones. Es un tamaño de planificación, no una garantía estadística. Sólo se ampliaría el entrenamiento a miles de ejemplos si los errores y costes lo justifican. La revisión requiere competencia en chino tradicional financiero; el juicio de otro LLM no sustituye esa referencia humana.

### 8.3 Series temporales y avances recientes

Chronos-2 y TimesFM-3 son candidatos para una comparación de series temporales. Google anunció TimesFM-3 el 31 de agosto de 2026 como modelo multivariante; no se adopta por ello como ganador financiero. [S40–S41]

Se verificará licencia, disponibilidad de pesos, corpus y período de preentrenamiento. Las covariables futuras sólo pueden contener hechos conocidos antes del corte —por ejemplo, un calendario ya anunciado—, nunca precios futuros, ingresos aún no publicados o macroeconomía revisada.

No se entrenará para minimizar el error del nivel de precios y luego se afirmará que eso demuestra mejores carteras. Se medirán rendimientos, ranking y utilidad neta, manteniendo también métricas de pronóstico como diagnóstico. [S31]

### 8.4 Agentes, grafos y modelos mayores

TradingAgents ofrece una referencia de arquitectura multiagente; FinGPT y Qlib aportan ideas de adaptación e infraestructura. Ninguno evita el trabajo de datos taiwaneses y validación temporal. [S33–S35]

Antes de añadir debate, se compararán dos pronósticos independientes con uno deliberativo bajo el mismo presupuesto. Antes de añadir un grafo, se comprobará si las relaciones añaden señal frente a industria y mercado. Antes de entrenar un modelo grande, se comprobará si uno pequeño deja una limitación demostrable.

El aprendizaje continuo no significará reescribir reglas después de cada semana negativa. Cualquier cambio que afecte a las predicciones abre una nueva versión, con una comparación en sombra antes de su promoción.

## 9. Diseño del entrenamiento propio

### 9.1 Etiquetas y tareas

Para la hipótesis semanal se generará una etiqueta de rendimiento total desde la primera apertura posterior al corte hasta el último cierre de esa semana bursátil. El objetivo de ranking será el rendimiento relativo frente a un universo comparable, no necesariamente su signo absoluto.

La cartera y sus costes se evaluarán en un motor separado: una etiqueta de retorno no demuestra que la operación fuera posible. Eventos no resueltos se mantendrán explícitos, con políticas de valoración conservadora y límites de sensibilidad; no se descartarán silenciosamente las empresas que desaparecen.

Una segunda tarea, independiente, puede pronosticar las siguientes cinco sesiones desde un corte diario. Una semana con festivos no es idéntica a cinco sesiones: las etiquetas, estadísticas y carteras no se mezclarán.

### 9.2 Variables y transformaciones

Se construirán variables de precios, fundamentales disponibles, flujos agregados, acontecimientos y contexto internacional. Las novedades textuales entrarán como tipos y magnitudes verificables, no como recomendaciones retrospectivas escritas por una IA.

Imputación, selección de variables, normalización, recorte de extremos, vocabularios y calibradores se ajustarán en las ventanas permitidas. Los rangos calculados entre empresas de una misma fecha son admisibles sólo si todas sus observaciones están disponibles antes del corte. Nunca se normalizará usando máximos y mínimos de toda la historia futura.

Cada conjunto de entrenamiento tendrá un manifiesto con filas, columnas, fechas de disponibilidad, etiquetas ya maduras, código y modelos auxiliares. Se comprobará que un cambio de esquema no convierta miles en unidades ni altere una moneda.

### 9.3 Partición temporal

La propuesta mínima conserva **2021–2025**, más datos anteriores para calentamiento. Para un modelo numérico propio conviene evaluar una historia más larga si se consigue cobertura comparable; no se añadirán años deficientes sólo para aumentar el tamaño.

Propuesta de partición: 2021–2023 desarrollo, 2024 validación y 2025 reserva. Sólo se puede llamar reserva a una muestra que no se haya usado para elegir reglas. Si ya fue inspeccionada durante iteraciones, se registra ese uso y se reserva otra evaluación o se depende más del registro prospectivo.

Dentro del desarrollo se aplicará validación que avanza cronológicamente, con ventanas de entrenamiento anteriores a cada validación. Las etiquetas que se solapen con el siguiente bloque se retirarán; la separación mínima depende del horizonte y de las fechas efectivas de eventos, no de una división aleatoria del 80/20.

Las filas de muchas empresas en una semana no son observaciones independientes. Se conservarán grupos por fecha; los errores e intervalos de cartera se calcularán respetando dependencia temporal y transversal.

### 9.4 Entrenamiento y promoción

Como punto de partida propongo revisar mensualmente los modelos tabulares usando sólo etiquetas cuyo horizonte ya terminó. Un candidato permanecerá en sombra, sin reemplazar al modelo vigente, hasta superar controles de calidad, coste y resultados previstos en el protocolo.

Se registrarán todos los ensayos, incluso los fallidos. No se eliminará un experimento porque quedó por debajo del mercado. Las diferencias por semilla, estabilidad de ranking y cambios de distribución se tratarán como resultados.

No se promete una máquina o GPU concreta. Primero se medirá tiempo y memoria sobre una muestra pequeña. La complejidad del corpus, no la popularidad del modelo, determinará si hacen falta recursos adicionales.

## 10. Protocolo comparativo y carteras simuladas

### 10.1 Experimento principal y comparaciones

La hipótesis principal pasa a ser: **el sistema híbrido mejora el rendimiento neto de una selección semanal frente al mismo modelo numérico sin las variables derivadas de texto, bajo universo, exposición y ejecución comparables.** Esto exige más que vencer una referencia débil.

| Experimento | Componente variable | Función |
|---|---|---|
| Q0 | Regla de rentabilidad previa de 20 sesiones. | Control transparente. |
| Q1 | Modelo numérico supervisado. | Referencia principal fuerte. |
| H1 | Q1 más eventos y contexto documental permitido. | Tratamiento principal. |
| L1 / L2 | Fable / Astra con el mismo paquete fechado. | Medir pronóstico directo de cada modelo. |
| T1 | Descubrir tema y después elegir empresas. | Reproducir la idea original sin fijar PCB. |
| N1 | Intensidad de noticias sin interpretación del LLM. | Separar atención de comprensión. |
| A1 | Selecciones aleatorias emparejadas. | Distribución de resultados por azar. |
| E1 | Consenso o debate, sólo después. | Evaluar si añade algo frente a independencia. |

La participación del texto se evaluará con y sin el componente, no atribuyendo todo el rendimiento del híbrido a la IA de lenguaje. Se informará el coste adicional por mejora, aunque la mejora sea pequeña o inconclusa.

### 10.2 Calendario congelado

Para la réplica semanal propongo corte informativo el domingo a las 18:00, zona `Asia/Taipei`; publicación antes de las 08:30 de la primera sesión de la semana; entrada de simulación en la apertura válida posterior; salida prevista en el último cierre de esa semana. Los cierres extraordinarios y festivos se toman del calendario efectivo. [S06]

La predicción diaria opcional tendrá corte a las 08:00 y publicación antes de las 08:30, con horizonte propio de cinco sesiones. No podrá sobrescribir la selección semanal cuando llegue una noticia nueva.

No se adjudicará al modelo una subida entre el viernes y la apertura del lunes después de leer noticias del fin de semana. Si la respuesta llega tarde, se aplica la política de retrasos, no un precio retrospectivo.

Todas las semanas serán la muestra principal. La segunda semana de cada mes quedará como comparación predefinida: semana cuyo lunes es el segundo lunes del mes. Son aproximadamente 260 cortes semanales en cinco años frente a 60 mensuales, no cientos de observaciones independientes por multiplicar cinco acciones.

### 10.3 Selección y elegibilidad

La clasificación cubrirá todas las empresas con suficientes variables. La simulación principal utilizará hasta cinco emisores, con cinco posiciones potenciales de igual peso y efectivo donde corresponda. No se forzará completar cinco nombres sin evidencia o elegibilidad. La referencia emparejada tendrá el mismo número de posiciones y exposición para separar selección de participación.

La elegibilidad necesita historia, precios válidos, estado de negociación y un umbral de capacidad ligado al importe nocional y a la liquidez observada. Esos valores quedan pendientes de la auditoría y deberán fijarse antes de mirar beneficios. No se propone sustituir este paso por «las 500 empresas más conocidas».

Se evaluará por separado una cesta de 20 emisores y una variante con límites sectoriales para conocer la concentración. No se elegirá retrospectivamente la variante ganadora y se presentará como la hipótesis original.

### 10.4 Referencias de mercado apropiadas

El **Formosa Stock Index** combina los mercados TWSE y TPEx; su metodología describe una versión de rentabilidad total. Será el candidato de referencia amplia, condicionado a obtener la serie adecuada y actualizada. [S21–S22]

También se calculará el universo elegible equiponderado y referencias por mercado/sector. El Formosa publicado al cierre sirve para la trayectoria de patrimonio diaria; no se fingirá que su cierre anterior es una entrada de apertura equivalente. Para el intervalo apertura–cierre de cada selección se usará una referencia con los mismos extremos temporales o se declarará la diferencia.

Las comparaciones emparejadas deben compartir moneda, dividendos, exposición, período y costes aplicables. Se distinguirá comparar contra un índice teórico de comparar contra una implementación simulada con costes.

### 10.5 Suerte de escoger una sola acción

Para responder a la experiencia original, se simularán trayectorias eligiendo al azar una acción de cada lista archivada. Propuesta: 10.000 trayectorias con semilla fijada, sin presentarlas como 10.000 muestras nuevas del mercado.

Se contrastará la mejor recomendación ordenada, la media de la lista y el abanico de resultados de una elección individual. Este análisis permite mostrar que una experiencia favorable puede ser compatible con una lista mediocre, sin negar que la lista podría contener información útil.

## 11. Motor de resultados: específico para Taiwán

La negociación ordinaria de TWSE tiene sesión de 09:00 a 13:30 y unidades habituales de 1.000 acciones; los lotes menores utilizan su propio mecanismo. Existen límites diarios de precio y excepciones que requieren tratamiento por instrumento y fecha. Las comisiones se negocian; no se debe tratar el porcentaje de referencia como una tarifa universal. [S03]

El motor inicial separará dos salidas: una simulación de señal con pesos ideales y una simulación de ejecución con lotes, importes y efectivo. La primera no se denominará ejecutable para una cantidad concreta.

Se registrará el estado de cada entrada y salida: ejecutada bajo el supuesto, no ejecutable, suspendida, pendiente o no resuelta. Los precios diarios no prueban la cantidad disponible en una subasta ni la prioridad en una cola de límite. Se impondrán escenarios conservadores cuando no exista detalle suficiente.

El libro contable conservará posiciones, efectivo, costes, derechos de dividendos y eventos corporativos. Si una acción no puede venderse al cierre previsto, permanece en el libro: su dinero no reaparece para financiar la siguiente cesta. La ausencia de un precio no es una rentabilidad cero ni una eliminación automática.

### 11.1 Costes

La tasa general de venta de acciones es **0,3%**. No se utilizará una reducción para operaciones intradía en una estrategia de varios días. Las vigencias históricas y particularidades se configurarán por fecha. [S04–S05]

Ejemplo aritmético: una comisión hipotética de referencia de 0,1425% por lado, más 0,3% de impuesto en la venta, suma aproximadamente **0,585% de fricción por vuelta**, antes de spread y deslizamiento y suponiendo importes semejantes de entrada y salida. No es una cotización de un intermediario ni el coste universal de toda cuenta. [S03]

Se aplicarán costes sobre importes realmente simulados y rotación real. Los escenarios de deslizamiento serán hipótesis explícitas, no cifras observadas: por ejemplo, 5, 10 y 25 puntos básicos por lado, además de tasas y comisión. El escenario central se congela antes de la evaluación reservada.

Un resultado que desaparece con costes plausibles no se presentará como ventaja utilizable. La reducción de rotación mediante persistencia de señales u horizontes mayores será otro experimento, no una corrección retroactiva destinada a salvar la curva.

## 12. Métricas y decisiones de continuidad

### 12.1 Tres cuadros de mando

**Calidad informativa:** precisión de entidades, cifras y referencias; duplicados; cobertura por sector y mercado; retraso; proporción de revisiones; errores críticos. Se evaluará con muestras humanas ciegas al resultado bursátil.

**Calidad predictiva:** correlación de rangos por fecha, rendimiento relativo de los primeros puestos, estabilidad, probabilidades calibradas, diferencias frente a modelos sin texto y sensibilidad por período. Una buena ordenación no implica que los nombres suban en términos absolutos.

**Resultados de cartera:** rentabilidad neta, exceso sobre referencias, peor semana, caída máxima diaria, exposición, concentración, rotación, costes y porcentaje de decisiones no ejecutables. El patrimonio incluye efectivo y posiciones pendientes.

### 12.2 Incertidumbre y múltiples experimentos

La métrica principal será la media semanal del exceso neto de H1 sobre Q1 bajo exposición emparejada. Se acompañará de intervalos que respeten bloques de semanas y de sensibilidades a longitud de bloque, costes y liquidez. La regla de remuestreo se fijará antes de observar la reserva.

Se informarán también tamaños de efecto y distribución, no sólo una significación estadística. Un intervalo amplio significa evidencia inconclusa, no automáticamente éxito ni inutilidad.

Prompts, semillas, horizontes, filtros, modelos, universos y métodos de consenso cuentan como ensayos cuando se usan para buscar una mejora. La literatura del Deflated Sharpe Ratio explica por qué seleccionar retrospectivamente entre muchos ensayos puede inflar el resultado aparente. [S32]

El seguimiento prospectivo tendrá revisiones previamente programadas y límites de uso de los resultados para cambiar reglas. No se declarará validación por detener la observación justo después de una buena racha. Doce semanas sirven para probar operación; el tiempo necesario para una conclusión depende de variabilidad y tamaño de la ventaja.

### 12.3 Criterios propuestos, no alcanzados

Antes de valorar rendimiento se exigen cero filtraciones temporales críticas conocidas, reproducibilidad del libro, identificación correcta de instrumentos y trazabilidad de cada afirmación factual. Como objetivos iniciales de muestreo, propongo precisión de entidades del 99% y de cifras extraídas del 98%, acompañadas de tamaño de muestra e intervalos; no son resultados actuales.

Para avanzar en complejidad, el componente nuevo debe demostrar una mejora relevante o una reducción de coste manteniendo calidad. Si el sistema sólo mejora claridad y cobertura, el producto puede continuar como asistente documental, sin etiqueta de selector superior de acciones.

## 13. Actualización continua sin alterar el experimento

### 13.1 Tres ritmos independientes

| Ritmo | Propuesta operativa | Restricción |
|---|---|---|
| Datos | Ingesta incremental de anuncios/noticias; consolidación después de la disponibilidad real de cada conjunto. | Respetar permisos y límites; comprobar frescura, no asumir que el cierre implica descarga completa. |
| Pronósticos | Clasificación diaria y selección semanal, identificadas por separado. | Cada predicción publicada permanece inmutable. |
| Modelos | Revisión mensual inicial y candidatos en sombra. | Sólo etiquetas maduras, evaluación y aprobación de versión. |

La frecuencia de consulta —por ejemplo, cada 15 minutos en fuentes autorizadas— es una propuesta sujeta a límites del proveedor, no una promesa de tiempo real. Se medirán latencias de origen e ingestión.

El panel mostrará `source_as_of`, edad del dato, última captura, última ejecución correcta y cobertura. Un error de descarga no se convertirá en «no pasó nada». Si falta una fuente crítica, se detiene o degrada el pronóstico conforme a reglas declaradas.

Las actualizaciones de fuentes, impuestos, calendario, APIs y modelos tienen su propio registro. Se revisarán al menos mensualmente y ante anuncios relevantes. Actualizar el código o un proveedor no autoriza a reconstruir silenciosamente resultados previos.

### 13.2 Fallos operativos

Si una predicción no se publica a tiempo, la política inicial de simulación será no abrir nuevas posiciones basadas en esa corrida, sin borrar las posiciones existentes. La semana permanece en el registro operativo. Los análisis de calidad de señales pueden distinguir corridas válidas, pero informarán la cobertura y el efecto de esas exclusiones.

No se tratará una caída de la API como una abstención inteligente. Tampoco se sustituirá automáticamente una fuente por otra con distintas fechas o semántica para mantener una apariencia de continuidad.

## 14. Arquitectura de construcción

Flujo propuesto:

`fuentes → archivo original versionado → maestro y datos temporales → variables/eventos → clasificación → registro de predicciones → libro simulado → evaluación → interfaz`

Python es una propuesta para ingestión, modelos y pruebas; Parquet más un motor de consulta local son suficientes para un prototipo de datos tabulares, sin imponer desde el comienzo una red de microservicios. La selección de interfaz y almacenamiento dependerá del volumen medido y del entorno del constructor.

Los módulos serán intercambiables mediante contratos: proveedor, calendario, identidad, publicaciones, eventos, características, entrenamiento, inferencia, archivo, simulación y evaluación. El esquema adjunto separa predicción de resultados.

No se guardarán secretos en documentos, prompts o repositorios. Los procesos de lenguaje tendrán herramientas mínimas y cuotas; las fuentes externas no podrán ordenar cambios de configuración. La evaluación no dependerá de volver a llamar al modelo para reconstruir su respuesta original.

### 14.1 Producto visible

La pantalla de mercado mostrará cobertura completa y ausencias, no sólo los primeros nombres. La de temas mostrará eventos nuevos y su evidencia, incluyendo sectores no tecnológicos. La ficha empresarial separará hechos, hipótesis, riesgos y datos pendientes. El calendario distinguirá anunciado de realizado.

El registro de pronósticos permitirá recuperar la lista y orden originales, comparar modelos, revisar por qué una operación se simuló o no, y abrir sus costes. Un panel separado mostrará calidad de datos, cobertura y versiones. Los resultados históricos potencialmente contaminados y los prospectivos no compartirán una etiqueta ambigua de «backtest validado».

Se propone chino tradicional para las fichas que revisará ella, con identificadores de datos y código estables, y documentación de proyecto en español. Las traducciones no cambiarán el contenido económico ni reemplazarán el original para auditoría.

## 15. Qué deben hacer Fable y Astra

Fable actuará inicialmente como constructor: diseña módulos contra esta especificación, implementa adaptadores y pruebas y documenta decisiones. Astra actuará como revisor adversarial: busca anticipación de datos, fallos de unidades, costes, identidades, calendario y estadísticas.

El revisor debe producir contraejemplos ejecutables, no una aprobación literaria. Los cambios que alteren una prueba crítica o una regla congelada requieren revisión explícita. El acuerdo entre ambos no permite saltarse un fallo.

Cuando se comparen como pronosticadores, recibirán el mismo paquete y responderán de forma independiente. No se dará a Astra la respuesta de Fable salvo en un tratamiento de consenso declarado. Su papel en la construcción no demuestra superioridad como modelo financiero.

Se registrarán modelo solicitado y devuelto, proveedor, parámetros, versión del prompt, coste y respuesta original. Si sólo existe un alias mutable, no se inventará una instantánea inmutable; se documentará la limitación y se segmentarán los cambios detectados.

## 16. Costes, recursos y decisiones de gasto

Las fichas actuales consultadas de Fable 5.1 y Astra muestran tarifas estándar de **10 USD por millón de tokens de entrada y 50 USD por millón de salida**. El coste real depende de modalidad, caché, longitud, herramientas y salida facturable, incluido razonamiento cuando proceda. [S42–S43]

Un ejemplo de capacidad, no un censo actual: revisar 2.000 empresas todos los días con 4.000 tokens de entrada y 500 de salida facturable por empresa cuesta 130 USD por modelo y día a esas tarifas. Dos modelos durante 22 jornadas serían **5.720 USD**. No incluye datos ni desarrollo.

Otro ejemplo: reservar a los modelos mayores 50 expedientes diarios de 8.000 tokens de entrada y 1.000 de salida facturable arroja **286 USD mensuales para dos modelos durante 22 jornadas**, antes de extracción masiva, modelos auxiliares, datos y herramientas. Esta reducción ilustra la utilidad de la priorización; no prueba que 50 expedientes sean suficientes.

Las cifras son operaciones aritméticas, no presupuestos cerrados ni equivalencias entre modelos de distinto esfuerzo. Dos mil tokens visibles no garantizan dos mil tokens facturados. La suscripción de ChatGPT no incluye automáticamente ese consumo de API. [S44]

Los precios de TEJ y de una licencia adecuada de noticias siguen pendientes. Tampoco se presupuestó una GPU porque no se ha medido un entrenamiento. La primera decisión de gasto debe ser una prueba acotada de datos y consumo, con límite aprobado, no una compra grande basada en una rentabilidad hipotética.

## 17. Hoja de ruta por entregables

### Entrega A — Contrato de datos y prueba de cobertura

Cerrar licencias, universo, calendario, significado de columnas y política temporal. Reconstruir doce cortes variados de prueba y casos adversos, sin usarlos como demostración financiera. Entregar manifiesto de cobertura, auditoría de fuentes y asuntos bloqueantes.

### Entrega B — Motor sin IA y censo completo

Implementar identidad histórica, precios, eventos, libro de efectivo y comparaciones simples. Mostrar el censo de TWSE y TPEx y todas las exclusiones. Superar pruebas de dividendos, ajustes, suspensiones y corte temporal antes de añadir selección por lenguaje.

### Entrega C — Primer registro prospectivo y modelo numérico

Una vez congelado un protocolo utilizable, comenzar el registro de pronósticos de carteras simuladas. En paralelo, entrenar y evaluar el modelo numérico con ventanas temporales. No esperar a construir toda la arquitectura avanzada para empezar a acumular evidencia futura.

### Entrega D — Documentos y sistema híbrido

Incorporar eventos extraídos y compararlos contra la misma base numérica. Ejecutar también Fable, Astra y la variante temática como tratamientos separados, con límites de coste y exposición iguales cuando corresponda.

### Entrega E — Especialización justificada

Adaptar un modelo pequeño, añadir grafos o series temporales sólo cuando la evaluación identifique una limitación concreta. Mantener los nuevos componentes en sombra y conservar el histórico de decisiones.

### Entrega F — Informe de evidencia

Distinguir ventaja observada, ausencia de mejora y evidencia inconclusa. Informar incertidumbre, costes, cobertura, concentración y rendimiento prospectivo. Decidir qué componente merece continuar; no exigir una conclusión positiva para reconocer el valor de la investigación.

El plazo de ingeniería depende de acceso a datos y calidad del entorno. El plazo de validación científica no puede sustituirse por una promesa de construir rápido: necesita resultados futuros que aún no existen.

## 18. Riesgos y respuestas

| Riesgo | Consecuencia | Respuesta de diseño |
|---|---|---|
| Noticias o revisiones futuras | Ventaja ficticia. | Versiones, cortes y pruebas adversariales. |
| Memoria del modelo | Histórico no identificable como predicción genuina. | Etiquetas de evidencia, modelo numérico limpio y registro prospectivo. |
| Supervivencia y empresas famosas | Muestra favorecida retrospectivamente. | Maestro histórico y cobertura visible por sector. |
| Costes y ejecuciones imposibles | Rendimiento no realizable. | Libro determinista, capacidad y escenarios conservadores. |
| Sobreajuste de prompts/modelos | Mejor resultado elegido entre muchos. | Registro de todos los ensayos y reserva temporal. |
| Cambio de régimen | Relación aprendida deja de funcionar. | Monitorización, incertidumbre y candidatos en sombra. |
| Falta de cobertura en chino | Omisión de noticias o empresas. | Evaluación humana y originales, no sólo fuentes en inglés. |
| Coste del procesamiento total | Presupuesto crece con universo/documentos. | Caché, eventos deduplicados, modelos especializados y cuotas. |
| Licencia insuficiente | Uso no autorizado del dato. | Auditoría antes de subir texto a APIs o distribuir resultados. |
| Dependencia de dos asistentes | Consenso sin evidencia. | Motor, datos y pruebas separados de las opiniones. |

## 19. Criterios finales y futuro del proyecto

Mi recomendación es **avanzar con la auditoría y una primera versión híbrida**, manteniendo la posibilidad de que no aparezca ventaja bursátil. No recomendaría dedicar meses a un gran entrenamiento antes de comprobar que los datos y comparaciones están bien construidos.

El futuro más defendible del producto es una herramienta de investigación de Taiwán con fuentes verificables y seguimiento de hipótesis. Si además una clasificación mejora de manera persistente y neta frente a alternativas fuertes, habrá evidencia para una segunda etapa. Eso se decide con datos posteriores, no con la sofisticación de la arquitectura.

Una eventual distribución comercial exigiría una revisión específica de licencias, privacidad y normativa aplicable al servicio concreto. Esta investigación no determina que la venta de recomendaciones esté autorizada ni constituye una opinión jurídica.

**La mejor primera demostración no será una curva ascendente. Será reconstruir qué se sabía en una fecha, producir una predicción a tiempo y explicar exactamente cómo se midió después.**

## 20. Qué queda sin comprobar

No se ha ejecutado una clasificación de todas las acciones al 9 de septiembre de 2026. No hay listas actuales de compra o venta en este documento. No se compraron datos ni se contactó a proveedores. No se probó el acceso a todas las APIs, la integridad de sus históricos, el permiso contractual de reutilización ni la ejecución de librerías propuestas.

No se entrenaron modelos ni se midieron tiempos de GPU. No se realizaron backtests o simulaciones financieras; los únicos cálculos numéricos del documento son ejemplos explicativos. No se ha activado una tarea continua de actualización.

Las decisiones pendientes operativas —presupuesto, proveedor, licencia, importe nocional, umbral de capacidad y política exacta de resultados no resueltos— quedan marcadas en el archivo de protocolo. No impiden definir el proyecto, pero sí impiden declararlo listo para una evaluación económica cerrada.

---

# Fuentes


**Fecha de consulta:** 9 de septiembre de 2026. Referencias primarias, oficiales o documentación del propio proveedor. La descripción de un producto no sustituye una auditoría de sus datos. La fecha de consulta no certifica disponibilidad antes de la apertura de ese día.

## S01 — TWSE — sitio oficial
Bolsa, cotizaciones y estadísticas oficiales. No se descargó un censo completo en esta investigación.
Fuente: `https://www.twse.com.tw/en/`

## S02 — TPEx — sitio oficial
Segundo mercado incluido desde la versión inicial; confirmar universos y tableros por instrumento.
Fuente: `https://www.tpex.org.tw/en-us/index.html`

## S03 — TWSE — Trading Mechanism Introduction
Horarios, lotes, límites de precio y comisiones de referencia. Las notas fiscales antiguas se contrastan con S04–S05.
Fuente: `https://www.twse.com.tw/en/products/system/trading.html`

## S04 — TWSE — Guide to Investing
Costes e impuestos de negociación; contrastar vigencia por fecha.
Fuente: `https://www.twse.com.tw/en/about/company/guide.html`

## S05 — Ministerio de Finanzas — Securities Transaction Tax Act
Norma primaria del impuesto sobre transacciones. Venta ordinaria de acciones: tasa general del 0,3%.
Fuente: `https://law-out.mof.gov.tw/EngLawContent.aspx?id=330`

## S06 — TWSE — Holiday Schedule
Calendario de sesiones; registrar también cierres extraordinarios y su fecha de anuncio.
Fuente: `https://www.twse.com.tw/en/trading/holiday.html`

## S07 — TWSE — OpenAPI
Punto de descubrimiento oficial de APIs. Auditar esquemas y latencia antes de construir adaptadores.
Fuente: `https://openapi.twse.com.tw/`

## S08 — TPEx — OpenAPI
API oficial indexada; la apertura directa presentó problemas. Contrato y muestras siguen pendientes.
Fuente: `https://www.tpex.org.tw/openapi/`

## S09 — TWSE — guía de MOPS
Explica el sistema de divulgaciones. La accesibilidad de cada endpoint de MOPS debe probarse.
Fuente: `https://shl.twse.com.tw/page/library/tips/2.html`

## S10 — FinMind — documentación técnica TaiwanMarket
Universos, cotizaciones y ajustes. Los precios reajustados son retrospectivos; no confundir ajustes descargados hoy con niveles históricos conocidos.
Fuente: `https://finmind.github.io/tutor/TaiwanMarket/Technical/`

## S11 — FinMind — documentación fundamental TaiwanMarket
Datos fundamentales y retiradas. La fecha contable no certifica por sí sola la publicación original.
Fuente: `https://finmind.github.io/tutor/TaiwanMarket/Fundamental/`

## S12 — FinMind — repositorio del proveedor
Biblioteca y condiciones técnicas; cobertura y licencia del dato son comprobaciones distintas a la licencia del código.
Fuente: `https://github.com/FinMind/FinMind`

## S13 — TEJ — Taiwan Stock Data Solutions
Candidato para historia taiwanesa. Precio, derechos y paquete exacto sin confirmar.
Fuente: `https://www.tejwin.com/en/solution/taiwan-stock-data/`

## S14 — TEJ — Quantitative Investment Database
Descripción del proveedor sobre datos temporales, mercado y eventos. No sustituye una auditoría de muestras.
Fuente: `https://www.tejwin.com/en/news/quantitative-investment/`

## S15 — TEJ — Monthly Revenue Information, part 1
Actualización del 2-09-2026; publicaciones mensuales, excepción de seguros y preservación de revisiones. Resultados del proveedor no se adoptan como validación de nuestro sistema.
Fuente: `https://www.tejwin.com/en/insight/monthly-revenue-info-part1/`

## S16 — TDCC — Shareholding statistics
Distribuciones agregadas de tenencias; no revelan por sí solas identidad ni intención de inversores.
Fuente: `https://www.tdcc.com.tw/portal/en/smWeb/qryStock`

## S17 — SEC — EDGAR Application Programming Interfaces
Divulgaciones estadounidenses para relaciones internacionales; conservar presentación y versión.
Fuente: `https://www.sec.gov/search-filings/edgar-application-programming-interfaces`

## S18 — ALFRED — Help
Versiones históricas de datos macroeconómicos, útiles para evitar revisiones futuras.
Fuente: `https://alfred.stlouisfed.org/help`

## S19 — Ministerio de Finanzas — August 2026 Exports and Imports
Publicación fechada 9-09-2026. Ejemplo de actualidad verificada, no señal de selección bursátil. No se verificó hora intradía.
Fuente: `https://www.mof.gov.tw/eng/singlehtml/f48d641f159a4866b1d31c0916fbcc71?cntId=902986e9e4a74e28858be27694182cf7`

## S20 — TSMC — Financial Calendar
Al consultar, ingresos de agosto programados para 10-09-2026. El calendario avisa que las fechas pueden cambiar.
Fuente: `https://investor.tsmc.com/english/financial-calendar`

## S21 — Taiwan Index Plus — Formosa Stock Index
Referencia conjunta de TWSE y TPEx. Distinguir versión de precio de rentabilidad total.
Fuente: `https://taiwanindex.com.tw/en/indexes/FRMSA`

## S22 — TWSE — Formosa Stock Index methodology
Metodología oficial, revisión de julio de 2021, que describe también la versión de rentabilidad total. Confirmar última versión al implementar.
Fuente: `https://www.twse.com.tw/downloads/en/products/indices/IndexSen01.pdf`

## S23 — Lopez-Lira y Tang — Can ChatGPT Forecast Stock Price Movements?
Investigación primaria de noticias y predicción; no prueba directa de una cesta semanal en todo Taiwán.
Fuente: `https://arxiv.org/abs/2304.07619`

## S24 — Glasserman y Lin — Assessing Look-Ahead Bias
Estudia sesgos de conocimiento posterior e identidad del emisor. Diagnósticos no equivalen a eliminación garantizada.
Fuente: `https://arxiv.org/abs/2309.17322`

## S25 — Lopez-Lira, Tang y Zhu — The Memorization Problem
Versión revisada en diciembre de 2025; límites de las evaluaciones dentro del período de entrenamiento y de los prompts de fecha.
Fuente: `https://arxiv.org/abs/2504.14765`

## S26 — He y colaboradores — Chronologically Consistent Large Language Models
ChronoBERT y ChronoGPT; alternativa de modelos con restricciones cronológicas de entrenamiento.
Fuente: `https://arxiv.org/abs/2502.21206`

## S27 — Gu, Kelly y Xiu — Empirical Asset Pricing via Machine Learning
Investigación primaria sobre aprendizaje automático y predicción de rendimientos. No extrapolar automáticamente a otro mercado u horizonte.
Fuente: `https://www.nber.org/papers/w25398`

## S28 — Liao y colaboradores — Generalized Stock Price Prediction Combined with News Fusion
Trabajo de 2026 con seis acciones taiwanesas seleccionadas y muestra estadounidense; errores de pronóstico no equivalen a beneficio neto de todo el mercado.
Fuente: `https://arxiv.org/html/2603.19286v1`

## S29 — Chen y Pu — Autonomous Market Intelligence: Agentic AI Nowcasting Predicts Stock Returns
Prepublicación de 2026 con pronósticos prospectivos estadounidenses desde 2025; resultado prometedor pero muestra y alcance limitados.
Fuente: `https://arxiv.org/abs/2601.11958`

## S30 — Crisostomo y Mykhalyuk — Large Language Models and Stock Investing: Is the Human Factor Required?
Investigación de 2026 sobre errores financieros, fuentes y supervisión humana. No valida por sí sola nuestro sistema.
Fuente: `https://arxiv.org/abs/2603.19944`

## S31 — FinVerse: Financial Time-Series Benchmark
Prepublicación de agosto de 2026; evaluación financiera orientada a decisiones, no solamente a exactitud convencional.
Fuente: `https://arxiv.org/abs/2608.03259`

## S32 — Bailey y López de Prado — The Deflated Sharpe Ratio
Investigación primaria sobre sesgo de selección por múltiples ensayos y distribuciones no normales.
Fuente: `https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf`

## S33 — TradingAgents — Multi-Agents LLM Financial Trading Framework
Arquitectura de agentes especializados; referencia para un comparador experimental, no prueba de ventaja en Taiwán.
Fuente: `https://arxiv.org/abs/2412.20138`

## S34 — FinGPT — repositorio oficial
Referencia de adaptación de modelos financieros. Ningún resultado ajeno se imputa a este proyecto.
Fuente: `https://github.com/AI4Finance-Foundation/FinGPT`

## S35 — Qlib — repositorio oficial de Microsoft
Infraestructura cuantitativa a evaluar; necesita adaptadores, calendarios y controles propios para Taiwán.
Fuente: `https://github.com/microsoft/qlib`

## S36 — LightGBM — Parameters
Documentación del modelo tabular candidato. Congelar versión y validar la función objetivo.
Fuente: `https://lightgbm.readthedocs.io/en/stable/Parameters.html`

## S37 — scikit-learn — Probability calibration
Herramientas y principios de calibración; ajustar calibrador en muestra distinta al entrenamiento y evaluar después.
Fuente: `https://scikit-learn.org/stable/modules/calibration.html`

## S38 — Hu y colaboradores — LoRA
Adaptación eficiente mediante matrices de bajo rango; no implica desaprender información futura.
Fuente: `https://arxiv.org/abs/2106.09685`

## S39 — Dettmers y colaboradores — QLoRA
Adaptación de modelos cuantizados; la memoria necesaria debe medirse con el checkpoint y longitud reales.
Fuente: `https://arxiv.org/abs/2305.14314`

## S40 — Amazon — Chronos forecasting
Familia de modelos de series temporales; Chronos-2 es un candidato comparativo, no un predictor bursátil validado para esta tarea.
Fuente: `https://github.com/amazon-science/chronos-forecasting`

## S41 — Google Research — TimesFM-3
Anuncio del 31-08-2026 de modelo multivariante, con enlaces de distribución; no certifica habilidad bursátil.
Fuente: `https://research.google/blog/timesfm-3-a-zero-shot-foundation-model-for-multivariate-forecasting/`

## S42 — Anthropic — Claude Fable 5.1 overview
Modelo actual verificado; tarifas estándar y corte de conocimiento. Revalidar antes de una corrida.
Fuente: `https://platform.claude.com/docs/en/models/fable-5-1/overview`

## S43 — OpenAI — GPT-6 Astra model
Modelo actual verificado; tarifa, corte y ausencia de fine-tuning para este modelo en la ficha consultada.
Fuente: `https://developers.openai.com/api/docs/models/gpt-6-astra`

## S44 — OpenAI — ChatGPT and API billing
Facturación de API separada de la suscripción de ChatGPT.
Fuente: `https://help.openai.com/en/articles/9039756-managing-billing-for-chatgpt-and-the-api-platform`

## S45 — FinBen — A Holistic Financial Benchmark for Large Language Models
Referencia para distinguir comprensión financiera, extracción y predicción como tareas diferentes.
Fuente: `https://arxiv.org/abs/2402.12659`

## S46 — TEJ — Differences among TEJ API, Tool API and TQuant Lab
Herramientas del proveedor a evaluar tras definir cobertura, contrato y pruebas; no se probó su ejecución.
Fuente: `https://www.tejwin.com/en/insight/differences-among-tej-api-tej-tool-api-and-tquant-lab/`

## S47 — Gobierno de Taiwán — Company data metadata
Metadatos del catálogo empresarial. La frecuencia del espejo no debe confundirse con la del origen.
Fuente: `https://data.gov.tw/dataset/18419`
