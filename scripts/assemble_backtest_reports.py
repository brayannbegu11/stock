"""Ensambla los informes 15, 15b y 15c: cabecera construida desde el JSON del backtest + informe generado por run_backtest.py.

Sólo actúa sobre archivos que empiezan por el título generado (`# Backtest <etiqueta>`); si ya tienen cabecera, no los toca.
Los JSON se localizan por patrón (el más reciente de cada escenario), igual que en export_site_data.py.

Uso: python scripts/assemble_backtest_reports.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INF = ROOT / "docs" / "informes"
FC = ("Q0", "Q1", "A1")
NAMES = {"Q0": "Q0 momentum 20 sesiones", "Q1": "Q1 tabular", "A1": "A1 azar (control)"}


SCENARIO_GLOBS = {
    "standard": "backtest_universe_2026-05-04_*.json",
    "user": "backtest_user_75kTWD_oddlots_*.json",
    "longhist": "backtest_universe_longhist_2021_*.json",
}


def latest(glob: str):
    files = sorted((ROOT / "data" / "store").glob(glob), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def load(scenario_id: str):
    p = latest(SCENARIO_GLOBS[scenario_id])
    if p is None:
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def pct(x, d=2, sign=True):
    if x is None:
        return "n/d"
    s = "−" if x < 0 else ("+" if sign and x > 0 else "")
    return f"{s}{abs(x)*100:.{d}f}".replace(".", ",") + " %"


def twd(x):
    return f"{int(round(x)):,}".replace(",", ".")


MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def periodo(s) -> str:
    a, b = s["period"]
    ma, mb = MESES[int(a[5:7]) - 1], MESES[int(b[5:7]) - 1]
    return f"{ma}-{mb} {b[:4]}" if a[:4] == b[:4] else f"{ma} {a[:4]}-{mb} {b[:4]}"


def demote_generated(text: str) -> str:
    lines = text.split("\n")
    if lines and lines[0].startswith("# "):
        t = lines[0][2:].strip()
        lines[0] = "## Informe generado: " + t[0].lower() + t[1:]
    return "\n".join(lines)


def paired_txt(p):
    if not p:
        return "—"
    m, n, ci = p.get("mean"), p.get("n_used"), p.get("ci95")
    base = f"{pct(m)} con {n} semanas emparejables"
    if p.get("degenerate") or not ci:
        return base + ": **no estimable**"
    extra = f" (variabilidad limitada: {p.get('n_fixed_observations')} semanas fijas)" if p.get("variability_limited") else ""
    return base + f", IC 95 % [{pct(ci[0])}, {pct(ci[1])}]{extra}"


def temporal_sentence(s, cw) -> str:
    """Clasificación temporal de la lista de la semana, derivada del archivo con las mismas reglas que el sitio."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("export_site_data", Path(__file__).with_name("export_site_data.py"))
        ex = importlib.util.module_from_spec(spec); spec.loader.exec_module(ex)
    except Exception:  # noqa: BLE001 - sin exportador no se afirma nada
        return "Clasificación temporal no determinada (exportador no disponible)."
    alabel = (s.get("assumptions") or {}).get("archive_label") or s["label"]
    c = ex.classify_week(alabel, cw)
    fa, inp = c["fa"], c["inp"]
    ruta = f"`forecast/{alabel}/<pronosticador>/{cw['week_id']}` en `data/raw`"
    if not fa["before_deadline"]:
        return (f"Emitida y archivada ({ruta}) **después** del plazo o sin identidad verificable ({', '.join(fa['reasons']) or 'plazo superado'}): "
                "es una reconstrucción con datos ya conocidos, no una predicción prospectiva.")
    if c["prospective"]:
        return (f"Archivada ({ruta}) antes del plazo declarado por cada predicción, con reloj del sistema, con todos los datos del "
                "paquete ingeridos antes del corte y con la lista igual a la archivada: predicción del protocolo según el reloj de "
                "esta máquina, sin sello externo y con el paquete construido en modo histórico (readmisión verificada pendiente).")
    if inp.get("reason") == "late_inputs":
        return (f"Archivada ({ruta}) antes del plazo, pero con datos del paquete recibidos después del corte "
                f"({', '.join(c['reasons'])}): no cuenta como predicción del protocolo.")
    return (f"Archivada ({ruta}) antes del plazo, pero la procedencia de las entradas no queda acreditada o la identidad de lo "
            f"mostrado no coincide con el archivo ({', '.join(c['reasons'])}): no cuenta como predicción del protocolo.")


def picks_table(cw, note_col):
    rows = []
    for f in FC:
        x = cw["forecasters"][f]
        picks = x.get("picks", [])
        sel = " · ".join(f"{p['symbol']} {p['name']}" for p in picks)
        failed = [p for p in picks if p.get("entry_status") == "entry_failed"]
        if x.get("filled") is None:
            st = "entrada pendiente (la apertura del lunes aún no ha ocurrido)"          # R20-05
        else:
            st = f"{x['filled']} de {x['filled'] + x['failed']} ejecutadas"
            if failed:
                st += "; sin lote posible: " + ", ".join(p["symbol"] for p in failed)
        rows.append(f"| {NAMES[f]} | {sel} | {st} |")
    return f"| Pronosticador | Selección (símbolo, nombre) | {note_col} |\n|---|---|---|\n" + "\n".join(rows)


def common_table(s, a, initial):
    F = s["forecasters"]
    attempts = {f: F[f]["weeks_selected"] * a["slots"] for f in FC}
    ew = s["universe_ew"]["mean_weekly_gross_open_close"]
    cell = lambda fn: " | ".join(fn(F[f], f) for f in FC)
    return f"""| | Q0 momentum | Q1 tabular | A1 azar | Universo elegible (bruto) |
|---|---|---|---|---|
| Media semanal bruta de las selecciones | {cell(lambda x, f: pct(x['mean_weekly_gross_pick_return']))} | {pct(ew)} |
| Media semanal neta de la cartera (apertura→cierre) | {cell(lambda x, f: pct(x['mean_weekly_net_return_open_close']))} | — |
| Semanas con neto > 0 (de las medibles) | {cell(lambda x, f: f"{x['weeks_positive']}/{x.get('weeks_measured', x['weeks_selected'])}")} | — |
| Entradas fallidas (lote más caro que el nocional del puesto) | {cell(lambda x, f: f"{x['entry_failures']} de {attempts[f]}")} | — |
| Coste medio sobre importe comprado + vendido heredado | {cell(lambda x, f: pct(x['mean_costs_over_invested'], 2, False))} | — |
| Patrimonio final (inicial {twd(initial)} TWD) | {cell(lambda x, f: f"{twd(x['final_equity'])} ({pct(x['total_net_return'], 1)})")} | — |
| Exceso neto emparejado frente a A1 | {paired_txt(F['Q0'].get('paired_excess_vs_baseline'))} | {paired_txt(F['Q1'].get('paired_excess_vs_baseline'))} | — | — |"""


def header_15(d):
    s = d["summary"]; a = s["assumptions"]; F = s["forecasters"]
    weeks = d["weeks"]; operated = s["weeks_operated"]
    cw = [w for w in weeks if w.get("pending_outcome")][-1]
    initial = a["notional"] * a["slots"]
    operated_ids = [w["week_id"] for w in weeks if not w.get("pending_outcome") and w["week_id"] not in s.get("weeks_extraordinary_closure_unhandled", [])]
    closures = ", ".join(s.get("weeks_extraordinary_closure_unhandled", [])) or "ninguna"
    diff_a1_q1 = F["A1"]["mean_weekly_net_return_open_close"] - F["Q1"]["mean_weekly_net_return_open_close"]
    net = {f: F[f]["mean_weekly_net_return_open_close"] for f in FC}
    ew_gross = s["universe_ew"]["mean_weekly_gross_open_close"]
    if net["Q0"] < net["A1"] and net["Q1"] < net["A1"]:
        lectura = "las dos reglas de precios lo hicieron peor que el azar" + (", y el azar peor que el mercado" if net["A1"] < ew_gross else "")
    else:
        lectura = "ninguna regla de precios se separa del azar de forma que pueda leerse sin intervalo"
    comp_costes = "es mayor que" if abs(diff_a1_q1) > F["Q1"]["mean_costs_over_invested"] else "no supera"
    return f"""# Backtest del universo completo, {periodo(s)} (Q0, Q1, A1; sin dividendos)

**Qué es:** el primer recorrido del protocolo sobre **todas** las acciones ordinarias del tablero principal de TWSE y TPEx ({twd(s['universe_size'])} valores del maestro, informe 10), con las cotizaciones oficiales diarias por fecha (`twlab/sources/twse_daily.py`: TWSE `MI_INDEX`, TPEx `dailyQuotes`, capturadas el 9 y 10 de septiembre de 2026 para las sesiones desde julio de 2024; Astra comprobó que 15.538 pares TWSE–FinMind de 2025 coinciden exactamente). Periodo: cortes dominicales entre {s['period'][0]} y {s['period'][1]} ({s['weeks_total']} semanas: {operated} operadas y la semana en curso, pendiente de desenlace). La corrida no usa ningún LLM; es una reconstrucción histórica con datos archivados después de los cortes, **no** evidencia prospectiva (véase la lista de la semana más abajo). Etiqueta: `{s['label']}`; cifras tomadas de `data/store/backtest_{s['label']}.json`, generado con el código corregido en la ronda 17 (dimensionado exacto con comisión, estados de entrada de la semana pendiente).

**Qué demuestra:** que la cadena completa (paquete → predicción validada → libro → emparejamiento) funciona sobre el universo real, con unos {int(sum(w['eligible'] for w in weeks) / len(weeks)):,} valores elegibles por semana de media; que gestiona una sesión oficial sin datos (viernes 10-07-2026: ninguna de las {twd(s['universe_size'])} acciones tiene cotización en ninguna de las dos fuentes; no hay anuncio de cierre archivado, sólo la ausencia de datos; las salidas quedaron bloqueadas y se reintentaron la semana siguiente, y la semana {closures} quedó fuera de las medias de retorno por no tener retorno medible, aunque sus costes conocidos sí entran en la media de costes); y que emite y archiva la lista de la semana en curso.

**Qué NO demuestra:** rentabilidad. {operated} semanas no bastan; la fuente no trae dividendos (mayo-septiembre es la temporada de reparto en Taiwán: los retornos, las etiquetas de Q1 y las comparaciones están **sesgados a la baja**; el control 100→90 con dividendo de 10 rinde 0 % con derechos y −10 % sin ellos); el universo es el censo vigente (supervivencia); los costes son ilustrativos; y el exceso emparejado es **degenerado** cuando quedan pocas semanas emparejables (las entradas fallidas de Q0 y Q1 dejan exposiciones muy distintas de las de A1): en ese caso no hay intervalo de confianza que publicar.

## Resultado en una tabla ({operated} semanas operadas, {operated_ids[0]} a {operated_ids[-1]})

{common_table(s, a, initial)}

Lectura correcta: en un mercado que subió ({pct(s['universe_ew']['mean_weekly_gross_open_close'])} semanal el universo elegible, bruto), {lectura}. La diferencia media neta A1−Q1 ({pct(diff_a1_q1)} por semana) {comp_costes} el coste medio ({pct(F['Q1']['mean_costs_over_invested'], 2, False)} sobre compras brutas más ventas brutas heredadas); con {operated} semanas, sin dividendos y sin intervalo, la diferencia no puede atribuirse a la señal. Lo que sí es un hecho operativo:

1. **El dimensionado proporcional (efectivo disponible / {a['slots']} por puesto, ≈ 0,8-1 M TWD) no puede comprar un lote de 1.000 acciones de los valores más caros.** Q1 elige con frecuencia 台積電 (2330, ≈ 2.400 TWD), 鴻海, 緯穎 o 欣興: {F['Q1']['entry_failures']} entradas fallidas de {F['Q1']['weeks_selected'] * a['slots']}. Hay que decidir: subir el capital, admitir lotes sueltos (零股; escenario del informe 15b) o filtrar el universo por precio. Es una decisión de protocolo y cambia el universo elegible.
2. **La regla de emparejamiento (misma exposición ±{a['exposure_tolerance']}) deja fuera a la mayoría de las semanas** cuando un pronosticador falla entradas y el otro no. O se corrige el dimensionado (punto 1) o el emparejamiento debe definirse de otro modo.
3. Los costes ilustrativos (≈ {pct(F['A1']['mean_costs_over_invested'], 2, False)} semanal sobre compras brutas más ventas brutas heredadas) son del orden de las diferencias semanales entre pronosticadores.

## Lista de la semana en curso (corte {cw['cutoff_at'][:10]} 18:00 Taipei; semana {cw['week_id']})

{temporal_sentence(s, cw)} Entrada simulada en la primera apertura tras el plazo; salida prevista en el último cierre de la semana (pendiente).

{picks_table(cw, "Estado de la entrada simulada")}

Estas listas son la salida del laboratorio, no una recomendación: los dos pronosticadores han quedado por debajo del azar en las {operated} semanas anteriores.

## Límites específicos de esta corrida

- Sin dividendos: la fuente oficial por fecha no los trae; libro, etiquetas de Q1 y comparaciones operan sin derechos (FinMind, que sí los trae, limita a ~300 peticiones por hora en el nivel gratuito).
- Q1 entrenado con un mínimo de 40 semanas de etiqueta (no 52): el historial descargado empieza en julio de 2024; la segunda fase de descarga (2021-2024) lo ampliará.
- {s['bars_without_regular_price_dropped']:,} barras sin precio de sesión regular excluidas; sesiones oficiales sin datos en ambas fuentes según `market_warnings` del JSON (cierres por tifón de 2024 y el 10-07-2026, sin anuncio archivado).
- Procedencia de los paquetes: cada documento de barras declara la fuente (`twse`/`tpex`), el extractor y, por fuente, el manifiesto de capturas de cada sesión de su ventana; una serie con sesiones sin captura enumerada no se admite (ronda 17). La readmisión verificada de series multi-captura queda pendiente (extractor por escribir).
- Todo lo demás: informe 11 §4-5 (costes, dimensionado, tolerancia de exposición, liquidez, tablero de innovación, disponibilidad de barras por política de 24 h, calendario capturado en 2026).

---

*A continuación, el informe generado automáticamente por `scripts/run_backtest.py` (tablas y selecciones semana a semana).*

"""


def header_15b(d, d_std):
    s = d["summary"]; a = s["assumptions"]; F = s["forecasters"]
    weeks = d["weeks"]; operated = s["weeks_operated"]
    cw = [w for w in weeks if w.get("pending_outcome")][-1]
    initial = a["notional"] * a["slots"]
    attempts = {f: F[f]["weeks_selected"] * a["slots"] for f in FC}
    std = d_std["summary"]["forecasters"]
    comp = "; ".join(f"{f}: {pct(F[f]['mean_weekly_net_return_open_close'])} frente a {pct(std[f]['mean_weekly_net_return_open_close'])}" for f in FC)
    costs = "; ".join(f"{f} {pct(F[f]['mean_costs_over_invested'], 2, False)} (estándar {pct(std[f]['mean_costs_over_invested'], 2, False)})" for f in FC)
    fails = "; ".join(f"{f} {F[f]['entry_failures']} de {attempts[f]} (estándar {std[f]['entry_failures']})" for f in FC)
    ew, ew_std = s["universe_ew"]["mean_weekly_gross_open_close"], d_std["summary"]["universe_ew"]["mean_weekly_gross_open_close"]
    liq = a["liquidity_multiple"] * a["notional"]
    liq_std = d_std["summary"]["assumptions"]["liquidity_multiple"] * d_std["summary"]["assumptions"]["notional"]
    elig = int(sum(w["eligible"] for w in weeks) / len(weeks)); elig_std = int(sum(w["eligible"] for w in d_std["weeks"]) / len(d_std["weeks"]))
    return f"""# Backtest del universo completo con el capital del usuario: 75.000 TWD en lotes sueltos ({periodo(s)})

**Qué es:** la misma corrida del informe 15 (mismo universo de {twd(s['universe_size'])} acciones, mismas {operated} semanas operadas, misma fuente oficial por fecha, **sin dividendos**), con el dimensionado que corresponde al capital real del usuario (2-3 mil USD): **{twd(initial)} TWD** iniciales, cinco puestos de {twd(a['notional'])} TWD nominales con dimensionado {a['sizing']} (efectivo disponible / {a['slots']}), **lotes sueltos** (`lot_size=1`, 零股), comisión {pct(float(a['commission_per_side']), 4, False)} por lado con **mínimo de {int(float(a.get('min_commission_twd', 20)))} TWD por orden**, impuesto de venta {pct(float(a['sell_tax']), 1, False)} y deslizamiento de {a['slippage_bps']} pb por lado (el mercado de lotes sueltos es menos líquido). Etiqueta: `{s['label']}`; cifras tomadas de `data/store/backtest_{s['label']}.json`, generado con el código corregido en la ronda 17 (la cantidad comprada respeta el nocional del puesto incluida la comisión mínima). Aproximación declarada: los precios son los de la sesión regular, no los del mercado de lotes sueltos (cambio de plan P7: propuesto en el prompt de la ronda 17, evaluado por Astra en su ronda 17, recogido como adenda en el informe 22 §2 y en el informe 23 §2).

**Qué cambia respecto al estándar:** el universo elegible es **mayor**: la regla de liquidez del protocolo exige que la mediana del importe negociado en 20 sesiones sea ≥ {a['liquidity_multiple']} × el nocional del puesto, es decir {twd(liq)} TWD frente a {twd(liq_std)} TWD en el estándar; entran valores pequeños que en el informe 15 quedaban fuera ({elig:,} elegibles por semana de media frente a {elig_std:,}), por lo que **las listas de Q0, Q1 y A1 no coinciden con las del informe 15** (A1 se sortea sobre ese universo distinto) y el universo bruto de referencia rinde {pct(ew)} semanal frente a {pct(ew_std)}. Con lotes sueltos casi todas las entradas caben ({fails}); a cambio, la comisión mínima pesa más sobre importes pequeños (coste medio sobre compras brutas más ventas brutas heredadas: {costs}). Medias semanales netas frente al escenario estándar: {comp}.

**Qué NO demuestra:** lo mismo que el informe 15: {operated} semanas no bastan, no hay dividendos, el universo es el censo vigente y el exceso emparejado se calcula con las semanas emparejables que haya. Las cifras siguientes las reproduce `scripts/run_backtest.py` con los parámetros del README.

## Resultado en una tabla ({operated} semanas operadas)

{common_table(s, a, initial)}

Lectura: el orden entre pronosticadores y el signo de las medias se leen en la tabla; ninguna diferencia es estadísticamente distinguible de cero con {operated} semanas. Con {twd(a['notional'])} TWD por puesto, la comisión mínima de {int(float(a.get('min_commission_twd', 20)))} TWD equivale al {pct(float(a.get('min_commission_twd', 20)) / a['notional'], 2, False)} del nocional por lado, por encima del {pct(float(a['commission_per_side']), 4, False)} nominal siempre que el importe de la orden baje de {twd(float(a.get('min_commission_twd', 20)) / float(a['commission_per_side']))} TWD.

## Lista de la semana en curso ({cw['week_id']}, corte {cw['cutoff_at'][:10]} 18:00 Taipei)

Lista **distinta** de la del informe 15: el universo elegible con {twd(a['notional'])} TWD por puesto incluye valores menos líquidos (regla de liquidez escalada con el nocional), y Q0, Q1 y A1 se calculan sobre él. {temporal_sentence(s, cw)}

{picks_table(cw, "Estado de la entrada simulada con lotes sueltos")}

## Límites específicos de esta corrida

- Precios de sesión regular como aproximación a los de lotes sueltos (que se cruzan a las 13:30 y en sesión intradía desde 2020 con su propio libro de órdenes): los deslizamientos reales pueden ser mayores; el {a['slippage_bps']} pb es una hipótesis declarada, no una medición.
- Comisión mínima de {int(float(a.get('min_commission_twd', 20)))} TWD como hipótesis habitual del mercado; la del intermediario del usuario no se ha confirmado.
- Sin dividendos, censo vigente, {operated} semanas: mismas advertencias que el informe 15.
- El nocional por puesto es proporcional al efectivo disponible (efectivo / {a['slots']}), por lo que tras semanas negativas los importes bajan y la comisión mínima pesa más.
- Universo elegible más amplio y menos líquido que el del informe 15 (misma regla, umbral {int(liq_std / liq)} veces menor): los resultados de ambos informes no son comparables valor a valor, sólo como dos escenarios del mismo protocolo.

---

*A continuación, el informe generado automáticamente por `scripts/run_backtest.py` (tablas y selecciones semana a semana).*

"""


def header_15c(d, d_std):
    s = d["summary"]; a = s["assumptions"]; F = s["forecasters"]
    weeks = d["weeks"]; operated = s["weeks_operated"]
    cw = [w for w in weeks if w.get("pending_outcome")][-1]
    initial = a["notional"] * a["slots"]
    std = d_std["summary"]["forecasters"]
    hist = (F["Q1"].get("training_history") or [""])[0]
    comp = "; ".join(f"{f}: {pct(F[f]['mean_weekly_net_return_open_close'])} frente a {pct(std[f]['mean_weekly_net_return_open_close'])}" for f in FC)
    elig = int(sum(w["eligible"] for w in weeks) / len(weeks)); elig_std = int(sum(w["eligible"] for w in d_std["weeks"]) / len(d_std["weeks"]))
    warns = "; ".join(w[:110] for w in s.get("market_warnings", [])[:3])
    return f"""# Backtest del universo completo con historial largo (2021-2026): mismo periodo, Q1 entrenado con más semanas

**Qué es:** la corrida del informe 15 (mismo universo de {twd(s['universe_size'])} acciones, mismas {operated} semanas operadas de mayo-septiembre 2026, mismo capital de {twd(initial)} TWD y lotes de 1.000, **sin dividendos**) cargando las cotizaciones oficiales por fecha desde el 4 de enero de 2021 (`{s['manifest']}`), de modo que Q1 se entrena con todas las semanas de etiqueta disponibles desde 2021 (mínimo configurado: 52, frente a 40 en el informe 15); primera manifestación de entrenamiento: `{hist}`. Etiqueta: `{s['label']}`; cifras tomadas de `data/store/backtest_{s['label']}.json`.

**Qué cambia respecto al informe 15:** Q0 y A1 no aprenden, así que sólo cambian si cambia el universo elegible ({elig:,} elegibles por semana de media frente a {elig_std:,}). Medias semanales netas frente al informe 15: {comp}. Entradas fallidas de Q1: {F['Q1']['entry_failures']} (informe 15: {std['Q1']['entry_failures']}).

**Qué NO demuestra:** lo mismo que el informe 15: {operated} semanas, sin dividendos, censo vigente, costes ilustrativos. Más historial de entrenamiento no añade semanas de evaluación.

## Resultado en una tabla ({operated} semanas operadas)

{common_table(s, a, initial)}

## Lista de la semana en curso ({cw['week_id']}, corte {cw['cutoff_at'][:10]} 18:00 Taipei)

{temporal_sentence(s, cw)}

{picks_table(cw, "Estado de la entrada simulada")}

## Límites específicos de esta corrida

- {s['bars_without_regular_price_dropped']:,} barras sin precio de sesión regular excluidas; avisos de carga: {warns}.
- Sin dividendos en todo el historial 2021-2026: las etiquetas de Q1 de la temporada de reparto de cada año están sesgadas a la baja.
- Todo lo demás: informe 15 §Límites.

---

*A continuación, el informe generado automáticamente por `scripts/run_backtest.py` (tablas y selecciones semana a semana).*

"""


def _assemble(path: Path, generated_prefix: str, build):
    if not path.exists():
        print(f"{path.name}: no existe"); return
    txt = path.read_text(encoding="utf-8")
    if txt.startswith(generated_prefix):
        path.write_text(build() + demote_generated(txt), encoding="utf-8", newline="\n")
        print(f"{path.name} ensamblado")
    else:
        print(f"{path.name}: ya tiene cabecera; no se toca")


def main():
    d_std = load("standard")
    if d_std is None:
        print("no hay JSON del escenario estándar"); return 1
    _assemble(INF / "15_backtest_universo_2026.md", "# Backtest universe_", lambda: header_15(d_std))
    d_user = load("user")
    if d_user is not None:
        _assemble(INF / "15b_backtest_universo_2026_lotes_sueltos.md", "# Backtest user_", lambda: header_15b(d_user, d_std))
    d_long = load("longhist")
    if d_long is not None:
        _assemble(INF / "15c_backtest_universo_2026_historial_2021.md", "# Backtest universe_longhist", lambda: header_15c(d_long, d_std))
    return 0


if __name__ == "__main__":
    sys.exit(main())
