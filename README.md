# taiwan-ia-lab

**Author: Brayann Benavides.** A living stock-forecasting lab for every common stock on TWSE and TPEx (Taiwan), run under a strict point-in-time clock and reviewed adversarially by an independent model. Analysis and simulated portfolios only: no real orders, no brokers, no credentials.

- **Website (Spanish · English · 繁體中文):** https://brayannbegu11.github.io/stock/ — published from the `gh-pages` branch by `scripts/deploy_pages.py`; the source is `docs/index.html` on `main`, with its data embedded by `scripts/export_site_data.py`, so the page also opens directly from disk.
- Specification received (GPT-6 Pro, v2.0, 9 Sep 2026): `docs/spec/v2/`
- Builder's reports (Spanish): `docs/informes/`
- Independent review rounds (GPT-6 Astra via Codex CLI): `review/out/`

## Getting started

```bash
python -m pip install -e ".[dev,model]"
python -m pytest -q -p no:cacheprovider            # 290 acceptance tests, no network
python scripts/capture_daily.py                    # daily capture to data/raw (TWSE/TPEx OpenAPI + FinMind), real ingested_at
python scripts/build_master.py                     # SCD2 security master and census -> data/store, docs/informes/10_censo_<date>.md
python scripts/fetch_history_sample.py             # stratified census sample with FinMind bars and dividends (network, ~5 min)
python scripts/fetch_universe_daily.py --start 2024-07-01   # official per-date quotes for the whole market (network, ~2 h; resumable; no dividends)
python scripts/run_q0_demo.py --start 2024-01-01 --end 2025-12-31          # end-to-end demo (no network)
python scripts/run_backtest.py --manifest sample --start 2024-01-01 --end 2025-12-31 --forecasters Q0,Q1,A1
python scripts/run_backtest.py --manifest daily --lookback-start 2024-07-01 --start 2026-05-04 --end 2026-09-09 --forecasters Q0,Q1,A1 --min-train-weeks 40 --report 15_backtest_universo_2026.md
python scripts/run_backtest.py --manifest daily --lookback-start 2024-07-01 --start 2026-05-04 --end 2026-09-09 --forecasters Q0,Q1,A1 --min-train-weeks 40 --notional 15000 --lot-size 1 --min-commission 20 --slippage-bps 20 --label user_75kTWD_oddlots_2026 --report 15b_backtest_universo_2026_lotes_sueltos.md
python scripts/export_site_data.py                 # refresh docs/site/data.json and embed it in docs/index.html
python scripts/deploy_pages.py                     # publish docs/index.html + docs/site to the gh-pages branch (GitHub Pages)
```

The last cutoff without an outcome is emitted as `pending_outcome`: that is the current week's list (five securities per forecaster), archived in `data/raw` with a real timestamp.

The daily capture runs as a Windows scheduled task since 9 Sep 2026 (18:30 local time) via `scripts/register_daily_capture.ps1`; remove it with `-Eliminar`.

Adversarial review with Astra (requires an authenticated Codex CLI; launch from PowerShell 7). The runner freezes a hash of the reviewable tree before the round and refuses any change made while it runs:

```powershell
.\review\run_astra.ps1 -Ronda ronda17_verificacion -Effort high
```

## Status (10 Sep 2026)

- **Deterministic core** (`src/twlab/`): versioned official calendar (2026 zh; 2021–2026 en) with a phrase classifier that refuses to guess; weekly protocol plan; SCD2 security master keyed by symbol + listing date, main-board universe by default; append-only archive with seals; per-cutoff packets with plan, JSON archive and document-by-document readmission on reload (in prospective mode the archive is mandatory, with byte integrity and extractor re-derivation; in historical mode only when archive and extractor registry are supplied, otherwise the document is declared unverified); packet and document metadata restricted to catalogues and identifiers; prediction-contract validation; lot-based ledger with owners and exact rational arithmetic; weekly basket; paired excess with a declared exposure tolerance and block bootstrap within segments. 290 synthetic tests pass, including the counterexamples from Astra's rounds 1–16.
- **Real data**: 37 endpoints captured daily; master with 2,348 segments and a default simulable universe of 1,937 main-board common stocks (report 10); archived sample of 67 TWSE securities 2021–2025 with verified capture identity; official per-date quotes for the whole market from July 2024 (`twlab/sources/twse_daily.py`; Astra verified that 15,538 TWSE–FinMind pairs from 2025 match exactly), second phase (2021–2024) downloading; Q0 demo over 102 weeks 2024–2025 (report 11).
- **Backtest with forecasters** (`twlab/backtest.py`, `twlab/models/q1.py`): weekly walk with Q0 (momentum), Q1 (ridge + LightGBM on weekly total-return ranks, trained only on labels whose open and close were available at the cutoff, retrained every 4 weeks, training id = hash of rows and config) and A1 (paired random control); simulation bound = min(period end, last data day). On the 2024–2025 sample (report 14) Q1 beats A1 by +0.08% weekly net with a 95% CI of [−0.31%, +0.35%]: indistinguishable from zero.
- **Full universe, official per-date source** (report 15): 1,937 stocks, May–September 2026 (17 traded weeks, 1 pending), Q0/Q1/A1 **without dividends** (the source does not carry them). Net weekly means: Q0 −0.87%, Q1 −1.04%, A1 +0.35%; eligible universe +1.23% gross. The paired excess is degenerate (not estimable) with 17 weeks. The useful result is operational: with proportional sizing (cash / 5 per slot, about NT$0.8–1M) a 1,000-share lot of the most expensive stocks does not fit (16 of 80 Q1 entries failed). The scenario sized like the author's real capital (report 15b: NT$75,000, odd lots, NT$20 minimum commission, 20 bp slippage) fills almost every entry (Q0 3 of 80 failed, Q1 and A1 none) but pays about 0.95% of the invested amount per week in costs; net weekly means Q0 −1.85%, Q1 −0.94%, A1 −1.08%, all three losing money. Its eligible universe is larger because the liquidity rule scales with the notional (median 20-session turnover ≥ 20 × NT$15,000), so its weekly lists differ from the standard run's; the paired excess vs. A1 is estimable there (Q1 −0.23 pp, 95% CI [−1.44, +0.24]) and includes zero.
- **Website** (`docs/index.html`): trilingual single page (es / en / zh-Hant) with the current week's lists, both scenarios week by week, the protocol, the 16 review rounds, data coverage, limits and next steps. Data come from `docs/site/data.json`, exported by `scripts/export_site_data.py` from the backtest JSONs and the review outputs; nothing on the page is typed by hand.
- **Not built yet**: cryptographic seal adapters (the production registry is empty), news/announcement extractors, LLM forecasters (L1/L2), historical dividends for the full universe, a policy for unscheduled closures, an official odd-lot adapter, a full historical master, a statistical reporting module.
- Decisions that belong to the author are listed in `docs/informes/01_entendimiento_bloqueantes_y_plan.md` §4.2, `docs/informes/11_demo_q0_2024-2025.md` §4 and `docs/informes/21_respuesta_ronda15_astra.md` §4. Last Astra round answered: 16 (report 22).

## Layout

| Path | Contents |
|---|---|
| `src/twlab/` | Core library: calendar, master, store, packet, ledger, evaluation, backtest, models, sources |
| `tests/` | Acceptance tests (synthetic, offline) |
| `scripts/` | Capture, master build, fetches, backtest, site export and Pages deployment |
| `docs/spec/v2/` | Specification package received |
| `docs/informes/` | Builder's reports and responses to each review round (Spanish) |
| `docs/index.html`, `docs/site/` | Website and its exported data |
| `review/` | Astra runner, prompts, schemas and outputs |
| `data/reference/`, `data/audit/` | Versioned reference data and audit records |
| `data/raw/`, `data/store/` | Captures and derived stores (not committed) |

## Disclaimer

Everything here is a simulation for research. Nothing is a recommendation to buy or sell any security. Costs are illustrative, the history is short, dividends are missing from the full-universe runs and no forecaster has beaten the random control so far.
