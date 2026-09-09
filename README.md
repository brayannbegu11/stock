# taiwan-ia-lab

Laboratorio vivo de inteligencia y evaluación bursátil para todas las acciones ordinarias de TWSE y TPEx, con control temporal estricto. Sólo análisis y carteras simuladas: sin órdenes reales, sin intermediarios.

- Especificación recibida (GPT-6 Pro, v2.0, 9-09-2026): `docs/spec/v2/`
- Informes del constructor (Fable 5.1): `docs/informes/`
- Revisiones del revisor independiente (GPT-6 Astra vía Codex CLI): `review/out/`

## Empezar

```bash
python -m pip install -e ".[dev,model]"
python -m pytest -q                       # pruebas de aceptación, sin red
python scripts/capture_daily.py           # captura diaria a data/raw (OpenAPI TWSE/TPEx + FinMind)
```

Revisión adversarial con Astra (requiere Codex CLI autenticado):

```powershell
.\review\run_astra.ps1 -Ronda ronda7_verificacion -Effort high
```

## Estado

Entrega A (auditoría de fuentes) en primera pasada; entrega B (núcleo determinista) con 187 pruebas sintéticas en verde (incluye los contraejemplos de las rondas 1 a 6 de Astra). No hay modelos entrenados, backtests ni pronósticos. Los bloqueantes que requieren decisión del usuario están en `docs/informes/01_entendimiento_bloqueantes_y_plan.md` §4.2.
