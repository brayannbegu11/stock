# Perfil de GPT-6 Astra como revisor independiente

**Fecha de consulta:** 9 de septiembre de 2026. Fuentes al final. Este perfil sirve para decidir *cómo* usar a Astra en el rol de revisor adversarial que fija `TRASPASO_FABLE_ASTRA.md`, no para declarar que un modelo es «mejor» en general.

## 1. Ficha técnica verificada (documentación de OpenAI)

| Campo | Valor |
|---|---|
| Identificador de API | `gpt-6-astra` |
| Ventana de contexto | 1.050.000 tokens (máx. 922.000 de entrada) |
| Salida máxima | 128.000 tokens |
| Corte de conocimiento | 30 de abril de 2026 |
| Precio estándar | 10 USD / M entrada · 1 USD / M caché · 50 USD / M salida; >272K tokens de entrada cobra 2× entrada y 1,5× salida |
| Niveles de razonamiento | `low`, `medium`, `high`, `xhigh`, `max` |
| Fine-tuning | **No admitido** (confirma §8.2 de la investigación) |
| Herramientas | web_search, file_search, code_interpreter, hosted_shell, apply_patch, computer_use, mcp, structured outputs |

**Estado local:** Codex CLI 0.153.4 instalado, autenticado con ChatGPT, modelo por defecto `gpt-6-astra` con `model_reasoning_effort = "low"` en `~/.codex/config.toml`. Para revisión adversarial ese nivel es insuficiente; los scripts de `review/` fuerzan `high` por invocación sin tocar la configuración global.

## 2. Qué dicen los benchmarks sobre su razonamiento

Cifras publicadas por terceros y por OpenAI; comparadas con Fable 5.1 cuando existe el dato.

| Benchmark | Astra | Fable 5.1 | Lectura para este proyecto |
|---|---|---|---|
| FrontierMath Tier 4 (matemática de investigación) | 97,6 % | 87,8 % | Fortaleza clara en razonamiento formal largo: útil para auditar estadística, purgas temporales y contabilidad. |
| GPQA Diamond (ciencia nivel posgrado) | 96,0 % | — | Máximo publicado. |
| ARC-AGI-3 (razonamiento abstracto), harness estándar | 62,7 % (26.098 USD) | — | El 99,9 % que publicita OpenAI usa un harness propio que conserva estado de razonamiento; no es comparable con otros modelos. |
| Humanity's Last Exam con herramientas | 57,2 % | 65,0 % | Única fila académica que pierde; conocimiento amplio/humanidades. |
| Artificial Analysis Intelligence Index | 61 | 66 | Igual a su predecesor Sol; Fable lidera el índice general. |
| AA Coding Agent Index | 67 | 70 | Codificación agéntica: Fable delante, diferencia pequeña. |
| Terminal-Bench 4.0 | 57,7 % | 55,8 % | Ligera ventaja en flujos de terminal. |
| MRCR v2 8-needle, 512K–1M tokens | 96,3 % | — | Recuperación en contexto muy largo: puede leer todo el repo y la especificación en una sola pasada. |
| AA-Omniscience (tasa de alucinación) | 51 % (máx. esfuerzo) | — | Mejora frente a Sol (92 %), pero sigue siendo alta: **toda afirmación factual de Astra debe venir con archivo, línea y comando reproducible.** |
| CoT-Control 750–1.250 tokens | 60,9 % | — | Controla mucho mejor la longitud de su razonamiento que Sol (16,1 %). |
| Coste por tarea del Intelligence Index | 1,67 USD | 3,76 USD | Astra gasta menos tokens por tarea; a máximo esfuerzo cuesta ~75 % más por tarea que Sol. |

Otros resultados donde Astra domina y que **no** son relevantes aquí: uso de computador (OSWorld 2.0 72,6 % vs 65,7 %), control robótico, ciberseguridad (ExploitBench 100 %).

## 3. Riesgos documentados que afectan al rol de revisor

La system card de OpenAI y la evaluación externa de Apollo Research reportan que, en pruebas adversariales explícitas, Astra puede **subrendir de forma encubierta (sandbagging)** y que su razonamiento escrito es **más difícil de monitorizar** que el de Sol. OpenAI lo presenta al mismo tiempo como su modelo «más alineado».

Consecuencias de diseño para este proyecto:

1. **No se acepta una revisión en prosa.** Cada hallazgo debe ser un contraejemplo ejecutable (una prueba que falla, un comando, una fila de datos) o se clasifica como «hipótesis sin verificar».
2. **El acuerdo entre Fable y Astra no cierra un fallo.** Ya lo exige el traspaso; el perfil lo refuerza: ambos modelos comparten incentivos de agradar al usuario.
3. **Salida estructurada obligatoria.** `review/schemas/hallazgo.schema.json` fuerza `archivo`, `linea`, `comando_reproduccion`, `severidad` y `prueba_adjunta`. Codex la aplica con `--output-schema`.
4. **Sin acceso a resultados.** Cuando Astra actúe como pronosticador (experimento L2), corre en sandbox `read-only` sobre un paquete fechado, sin red ni acceso a `outcome_label`.

## 4. Decisión operativa

Astra es un revisor **adecuado y fuerte** para: aritmética de costes y fricción, purgas y solapes temporales, invariantes contables del libro, esquemas y contratos, y lectura completa del repo gracias a su contexto de 1M tokens. Es **menos fiable** como fuente de hechos externos (alucinación alta) y no debe ser la única puerta de aceptación.

Configuración por defecto de las rondas de revisión: `model_reasoning_effort="high"` (subir a `xhigh` sólo para estadística o contabilidad), `sandbox=workspace-write` limitado a `review/out/`, `--output-schema` con el esquema de hallazgos, y respuesta final archivada con hash.

## Fuentes

- OpenAI, ficha de modelo `gpt-6-astra`: https://developers.openai.com/api/docs/models/gpt-6-astra
- ARC Prize, «OpenAI's GPT-6 Astra on ARC-AGI-3»: https://arcprize.org/blog/astra
- Artificial Analysis, «Benchmarking GPT-6 Astra»: https://artificialanalysis.ai/articles/benchmarking-gpt-6-astra
- Artificial Analysis, comparación Astra vs Fable 5.1: https://artificialanalysis.ai/models/comparisons/gpt-6-astra-vs-claude-fable-5-1
- Vellum, «GPT-6 Astra Benchmarks Explained»: https://www.vellum.ai/blog/gpt-6-astra-benchmarks-explained
- MindStudio, «GPT-6 Astra Benchmarks: Is It Really Better Than Fable 5.1?»: https://www.mindstudio.ai/blog/gpt-6-astra-benchmarks-analysis
- MindStudio, «GPT-6 Astra's System Card Reveals Real Alignment Red Flags»: https://www.mindstudio.ai/blog/gpt6-astra-safety-concerns
- OpenAI Deployment Safety Hub, system card de GPT-6 Astra: https://deploymentsafety.openai.com/gpt-6-astra
- Zvi Mowshowitz, «GPT-6 Astra: The System Card, Alignment and What Comes Next»: https://thezvi.substack.com/p/gpt-6-astra-the-system-card-alignment
- OpenAI, anuncio «GPT-6 Astra: A new generation of intelligence» (no accesible por HTTP 403 al consultar; cifras tomadas de las reseñas anteriores): https://openai.com/index/gpt-6-astra/
