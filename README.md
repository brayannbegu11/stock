# taiwan-ia-lab

Laboratorio vivo de inteligencia y evaluación bursátil para todas las acciones ordinarias de TWSE y TPEx, con control temporal estricto. Sólo análisis y carteras simuladas: sin órdenes reales, sin intermediarios.

- Especificación recibida (GPT-6 Pro, v2.0, 9-09-2026): `docs/spec/v2/`
- Informes del constructor (Fable 5.1): `docs/informes/`
- Revisiones del revisor independiente (GPT-6 Astra vía Codex CLI): `review/out/`

## Empezar

```bash
python -m pip install -e ".[dev,model]"
python -m pytest -q -p no:cacheprovider   # 265 pruebas de aceptación, sin red
python scripts/capture_daily.py           # captura diaria a data/raw (OpenAPI TWSE/TPEx + FinMind), con ingested_at real
python scripts/build_master.py            # maestro SCD2 y censo desde las capturas → data/store, docs/informes/10_censo_<fecha>.md
python scripts/fetch_history_sample.py    # muestra estratificada del censo con barras y dividendos de FinMind (red, ~5 min)
python scripts/fetch_universe_history.py  # histórico de todo el tablero principal (red, ~2 h; reanudable)
python scripts/run_q0_demo.py --start 2024-01-01 --end 2025-12-31   # demo de extremo a extremo (sin red)
python scripts/run_backtest.py --manifest sample --start 2024-01-01 --end 2025-12-31 --forecasters Q0,Q1,A1   # backtest con Q1
python scripts/run_backtest.py --manifest universe --weeks-back 17 --forecasters Q0,Q1,A1 --report 15_backtest_universo_2026.md
```

El último corte sin desenlace se emite como `pending_outcome`: es la lista de la semana en curso (cinco valores por pronosticador), archivada en `data/raw` con hora real.

La captura diaria puede programarse en Windows con `scripts/register_daily_capture.ps1` (no se registra sola: es un cambio persistente del sistema y se lanza a mano).

Revisión adversarial con Astra (requiere Codex CLI autenticado; lanzar desde PowerShell 7):

```powershell
.\review\run_astra.ps1 -Ronda ronda12_verificacion -Effort high
```

## Estado (9-09-2026)

- **Núcleo determinista** (`src/twlab/`): calendario oficial versionado (2026 zh; 2021-2026 en) con clasificador de frases catalogadas que rehúsa adivinar, plan semanal del protocolo, maestro SCD2 con identidad símbolo+fecha de alta y universo del tablero principal por defecto, archivo sólo anexado con sellos, paquetes por corte con plan, archivo JSON y readmisión documento a documento (archivo obligatorio, integridad de bytes, re-derivación por extractor) al recuperarlos, validación del contrato de predicción, libro por lotes y propietarios, cesta semanal, exceso emparejado con tolerancia de exposición declarada y bootstrap por bloques dentro de tramos con pesos exactos por longitud. 244 pruebas sintéticas en verde, incluidos los contraejemplos de las rondas 1 a 9 de Astra.
- **Datos reales**: 37 endpoints capturados a diario (tarea programada de Windows registrada el 9-09-2026); maestro con 2.348 segmentos y universo simulable por defecto de 1.937 acciones ordinarias del tablero principal (informe 10); muestra archivada de 67 valores TWSE 2021-2025 con identidad de captura comprobada; histórico del universo completo en descarga; demo Q0 de 102 semanas 2024-2025 con paquete, predicción validada, libro y evaluación (informe 11). La demo prueba que la cadena funciona; **no** mide rentabilidad ni ejercita la gestión de cierres sobrevenidos.
- **Backtest con pronosticadores** (`twlab/backtest.py`, `twlab/models/q1.py`): recorrido semanal con Q0 (momentum), Q1 (ridge + LightGBM sobre rangos de retorno total semanal, entrenado sólo con etiquetas cuya apertura y cierre estaban disponibles al corte, reentrenado cada 4 semanas, con identificador de entrenamiento por hash de filas y configuración) y A1 (aleatorio emparejado); límite de simulación = mín(fin del periodo, último dato). Sobre la muestra 2024-2025 (informe 14) Q1 supera a A1 en +0,08 % semanal neto con IC 95 % [−0,31 %, +0,35 %]: no distinguible de cero, y los costes ilustrativos dejan a los tres en negativo.
- **No existe todavía**: adaptadores criptográficos de sello (el registro de producción está vacío), extractores de noticias/anuncios, pronosticadores con LLM (L1/L2), política de cierres sobrevenidos, adaptador de lotes menores, maestro histórico completo, módulo de informe estadístico, interfaz.
- Los bloqueantes que requieren decisión del usuario están en `docs/informes/01_entendimiento_bloqueantes_y_plan.md` §4.2, `docs/informes/11_demo_q0_2024-2025.md` §4 y `docs/informes/17_respuesta_ronda11_astra.md` §4. Última ronda de Astra respondida: 11 (informe 17); 265 pruebas incluyen sus contraejemplos.
