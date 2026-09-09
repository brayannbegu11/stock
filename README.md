# taiwan-ia-lab

Laboratorio vivo de inteligencia y evaluación bursátil para todas las acciones ordinarias de TWSE y TPEx, con control temporal estricto. Sólo análisis y carteras simuladas: sin órdenes reales, sin intermediarios.

- Especificación recibida (GPT-6 Pro, v2.0, 9-09-2026): `docs/spec/v2/`
- Informes del constructor (Fable 5.1): `docs/informes/`
- Revisiones del revisor independiente (GPT-6 Astra vía Codex CLI): `review/out/`

## Empezar

```bash
python -m pip install -e ".[dev,model]"
python -m pytest -q -p no:cacheprovider   # 200 pruebas de aceptación, sin red
python scripts/capture_daily.py           # captura diaria a data/raw (OpenAPI TWSE/TPEx + FinMind), con ingested_at real
python scripts/build_master.py            # maestro SCD2 y censo desde las capturas → data/store, docs/informes/10_censo_<fecha>.md
python scripts/fetch_history_sample.py    # muestra estratificada del censo con barras y dividendos de FinMind (red, ~5 min)
python scripts/run_q0_demo.py --start 2024-01-01 --end 2025-12-31   # demo de extremo a extremo (sin red)
```

La captura diaria puede programarse en Windows con `scripts/register_daily_capture.ps1` (no se registra sola: es un cambio persistente del sistema y se lanza a mano).

Revisión adversarial con Astra (requiere Codex CLI autenticado):

```powershell
.\review\run_astra.ps1 -Ronda ronda8_verificacion -Effort high
```

## Estado (9-09-2026)

- **Núcleo determinista** (`src/twlab/`): calendario oficial versionado (2026 zh; 2021-2026 en), plan semanal del protocolo, maestro SCD2, archivo sólo anexado con sellos, paquetes por corte con plan y archivo JSON, validación del contrato de predicción, libro por lotes y propietarios, cesta semanal, exceso emparejado y bootstrap por bloques que no cruzan huecos. 200 pruebas sintéticas en verde, incluidos los contraejemplos de las rondas 1 a 7 de Astra.
- **Datos reales**: 37 endpoints capturados; maestro con 2.348 segmentos y universo simulable de 1.973 acciones ordinarias (informe 10); muestra archivada de 67 valores TWSE 2021-2025; demo Q0 de 102 semanas 2024-2025 con paquete, predicción validada, libro y evaluación (informe 11). La demo prueba que la cadena funciona; **no** mide rentabilidad.
- **No existe todavía**: adaptadores criptográficos de sello (el registro de producción está vacío), extractores de noticias/anuncios, maestro histórico completo, modelo numérico, módulo de informe estadístico, interfaz.
- Los bloqueantes que requieren decisión del usuario están en `docs/informes/01_entendimiento_bloqueantes_y_plan.md` §4.2 y en `docs/informes/09_respuesta_ronda7_astra.md` §4.
