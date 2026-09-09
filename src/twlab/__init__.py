"""twlab — laboratorio bursátil de Taiwán con control temporal.

Reglas no negociables (ver docs/spec/v2/CONTRATOS_DATOS.md):
- Toda observación lleva `recorded_at`/`ingested_at` reales; nunca se falsifican.
- Los precios nominales y ajustados no se mezclan sin transformación explícita.
- El predictor sólo ve `information_packet`; el evaluador sólo lee predicciones selladas.
- El libro (ledger) calcula dinero; los modelos sólo puntúan o extraen.
"""
__version__ = "0.1.0"
