# taiwan-ia-lab

**Author: Brayann Benavides.** A living stock-forecasting lab for every common stock on TWSE and TPEx (Taiwan), run under a strict point-in-time clock and reviewed adversarially by an independent model. Analysis and simulated portfolios only: no real orders, no brokers, no credentials.

- **Website (Spanish · English · 繁體中文):** https://brayannbegu11.github.io/stock/ — published from the `gh-pages` branch by `scripts/deploy_pages.py`; the source is `docs/index.html` on `main`, with its data embedded by `scripts/export_site_data.py`, so the page also opens directly from disk.
- Specification received (GPT-6 Pro, v2.0, 9 Sep 2026): `docs/spec/v2/`
- Builder's reports (Spanish): `docs/informes/`
- Independent review rounds (GPT-6 Astra via Codex CLI): `review/out/`

## Getting started

```bash
python -m pip install -e ".[dev,model]"
python -m pytest -q -p no:cacheprovider            # acceptance tests, no network (count: python -m pytest --co -q)
python scripts/capture_daily.py                    # daily capture to data/raw (TWSE/TPEx OpenAPI + FinMind), real ingested_at
python scripts/build_master.py                     # SCD2 security master and census -> data/store, docs/informes/10_censo_<date>.md
python scripts/fetch_history_sample.py             # stratified census sample with FinMind bars and dividends (network, ~5 min)
python scripts/fetch_universe_daily.py --start 2024-07-01   # official per-date quotes for the whole market (network, ~2 h; resumable; no dividends)
python scripts/run_q0_demo.py --start 2024-01-01 --end 2025-12-31          # end-to-end demo (no network)
python scripts/run_backtest.py --manifest sample --start 2024-01-01 --end 2025-12-31 --forecasters Q0,Q1,A1
python scripts/run_backtest.py --manifest daily --lookback-start 2024-07-01 --start 2026-05-04 --end 2026-09-09 --forecasters Q0,Q1,A1 --min-train-weeks 40 --report 15_backtest_universo_2026.md
python scripts/run_backtest.py --manifest daily --lookback-start 2024-07-01 --start 2026-05-04 --end 2026-09-09 --forecasters Q0,Q1,A1 --min-train-weeks 40 --notional 15000 --lot-size 1 --min-commission 20 --slippage-bps 20 --label user_75kTWD_oddlots_2026 --report 15b_backtest_universo_2026_lotes_sueltos.md
python scripts/run_backtest.py --manifest daily --lookback-start 2021-01-04 --start 2026-05-04 --end 2026-09-09 --forecasters Q0,Q1,A1 --min-train-weeks 52 --label universe_longhist_2021_2026 --report 15c_backtest_universo_2026_historial_2021.md   # ~2 h 20 min, ~3 GB
python scripts/export_site_data.py                 # refresh docs/site/data.json and embed it in docs/index.html
python scripts/deploy_pages.py                     # publish docs/index.html + docs/site to the gh-pages branch (GitHub Pages)
python scripts/assemble_backtest_reports.py        # rebuild the hand-readable headers of reports 15/15b/15c from their JSONs
```

The last cutoff without an outcome is emitted as `pending_outcome`: that is the current week's list (five securities per forecaster), archived in `data/raw` with a real timestamp.

The daily capture runs as a Windows scheduled task since 9 Sep 2026 (18:30 local time) via `scripts/register_daily_capture.ps1`; remove it with `-Eliminar`.

**Weekly prospective cycle** (phase 3): `scripts/weekly_prospective.ps1`, registered by `scripts/register_weekly_prospective.ps1` as the Windows task "taiwan-ia-lab ciclo semanal" (Sundays 08:00 local Eastern time = 20:00 Taipei in summer, 21:00 in winter; in both cases after the 18:00 cutoff and before the Monday 08:30 deadline). It fetches the missing official sessions, runs the three scenarios up to the Taipei date with the original archive labels (`--archive-label`, so weeks already archived are reused byte-for-byte and keep their first ingestion time), rebuilds the report headers, exports the site and publishes it. A list counts as a *prediction* on the site only when, for every forecaster, the first archived ingestion of the exact bytes evaluated (sha256 recorded in the run) is intact, was written by the system clock and is at or before the `deadline_at` that prediction declares; the archived prediction is well formed (`selected` with a non-empty ranking of unique securities and strict-integer ranks 1..n in array order, or an empty abstention) and declares the week's packet hash and cutoff; the displayed status, list, symbols and names equal the archived ranking and the names carried by the archived packet; the archived packet deserialises under the lab contract, its recomputed logical hash matches the week, the file and the archive record, and every capture it references is intact, system-clocked and ingested before the cutoff; and every selected security has, in the master snapshot archived by that run **before** its predictions (each archived prediction cites that snapshot's sha256, and its first intact system-clocked ingestion must be at or before the deadline), a segment valid at the cutoff *as known at the cutoff* (rows recorded later do not count) whose symbol is the archived ticker; every price series in the archived packet must likewise belong to a security valid at the cutoff and carry its symbol. Records with wrong types in the archive index, the prediction, the packet or the master snapshot are rejected by typed checks plus the lab's own contract validators, and any other exception closes only the stage where it happens (reported as `classification_error:<type>`, with the evidence already verified kept) (a second daily task, `scripts/register_daily_quotes_fetch.ps1`, captures the per-date quotes every evening so that Friday's session is archived before the cutoff). The packet is still built in historical mode and there is no external timestamp; the site says both.

Adversarial review with Astra (requires an authenticated Codex CLI; launch from PowerShell 7). The runner freezes a hash of the reviewable tree before the round and refuses any change made while it runs:

```powershell
.\review\run_astra.ps1 -Ronda ronda20_verificacion -Effort high
```

## Status (10 Sep 2026)

- **Deterministic core** (`src/twlab/`): versioned official calendar (2026 zh; 2021–2026 en) with a phrase classifier that refuses to guess; weekly protocol plan; SCD2 security master keyed by symbol + listing date, main-board universe by default; append-only archive with seals; per-cutoff packets with plan, JSON archive and document-by-document readmission on reload (in prospective mode the archive is mandatory, with byte integrity and extractor re-derivation; in historical mode only when archive and extractor registry are supplied, otherwise the document is declared unverified); packet and document metadata restricted to catalogues and identifiers; prediction-contract validation; lot-based ledger with owners and exact rational arithmetic; weekly basket; paired excess with a declared exposure tolerance and block bootstrap within segments. The synthetic test suite passes (no network), including the counterexamples from Astra's rounds 1–20; the count is whatever `python -m pytest --co -q` reports.
- **Real data**: 37 endpoints captured daily; master with 2,348 segments and a default simulable universe of 1,937 main-board common stocks (report 10); archived sample of 67 TWSE securities 2021–2025 with verified capture identity; official per-date quotes for the whole market from July 2024 (`twlab/sources/twse_daily.py`; Astra verified that 15,538 TWSE–FinMind pairs from 2025 match exactly), second phase (2021–2024) downloading; Q0 demo over 102 weeks 2024–2025 (report 11).
- **Backtest with forecasters** (`twlab/backtest.py`, `twlab/models/q1.py`): weekly walk with Q0 (momentum), Q1 (ridge + LightGBM on weekly total-return ranks, trained only on labels whose open and close were available at the cutoff, retrained every 4 weeks, training id = hash of rows and config) and A1 (paired random control); simulation bound = min(period end, last data day). On the 2024–2025 sample (report 14) Q1 beats A1 by +0.08% weekly net with a 95% CI of [−0.31%, +0.35%]: indistinguishable from zero.
- **Full universe, official per-date source** (report 15): 1,937 stocks, May–September 2026 (17 traded weeks, 1 pending), Q0/Q1/A1 **without dividends** (the source does not carry them). Net weekly means: Q0 −0.87%, Q1 −1.04%, A1 +0.35%; eligible universe +1.23% gross. The paired excess is degenerate (not estimable) with 17 weeks. The useful result is operational: with proportional sizing (cash / 5 per slot, about NT$0.8–1M) a 1,000-share lot of the most expensive stocks does not fit (16 of 80 Q1 entries failed). The scenario sized like the author's real capital (report 15b: NT$75,000, odd lots, NT$20 minimum commission, 20 bp slippage) fills almost every entry (Q0 3 of 80 failed, Q1 and A1 none) but pays about 0.95% per week in costs, measured over gross purchases plus gross sales of inherited baskets; net weekly means Q0 −1.85%, Q1 −0.94%, A1 −1.08%, all three losing money. Its eligible universe is larger because the liquidity rule scales with the notional (median 20-session turnover ≥ 20 × NT$15,000), so its weekly lists differ from the standard run's; the paired excess vs. A1 is estimable there (Q1 −0.23 pp, 95% CI [−1.44, +0.24]) and includes zero.
- **Website** (`docs/index.html`): trilingual single page (es / en / zh-Hant) written for non-specialists: three questions answered from the data (does it work, can the numbers be trusted, can I invest), the four project phases with their derived status, the week's lists per scenario labelled prediction or reconstruction, how a week works, the three programs, results per scenario, every review round with counts derived from Astra's JSON outputs, limits, a glossary and the documents. Figures come from `docs/site/data.json`, exported by `scripts/export_site_data.py` from the backtest JSONs and the review outputs; the explanatory texts in the three languages are the author's and are checked by Astra against the artefacts.
- **Not built yet**: cryptographic seal adapters (the production registry is empty), news/announcement extractors, LLM forecasters (L1/L2), historical dividends for the full universe, a policy for unscheduled closures, an official odd-lot adapter, a full historical master, a statistical reporting module.
- Decisions that belong to the author are listed in `docs/informes/01_entendimiento_bloqueantes_y_plan.md` §4.2, `docs/informes/11_demo_q0_2024-2025.md` §4 and `docs/informes/21_respuesta_ronda15_astra.md` §4. The latest Astra round answered is always the highest-numbered `docs/informes/NN_respuesta_rondaMM_astra.md` (report 30 answers round 24 at the time of writing). Rounds 18 and 19 ended in “approved with changes”; rounds 20–24 rejected successive versions of the prospective-phase classification, each corrected in the following report. A third run (report 15c, `universe_longhist_2021_2026`) loads the official quotes since January 2021 so that Q1 trains on about 250 label weeks instead of 70: Q1 improves to −0.87% weekly net with no failed entries, still below the random control (+0.35%); Q0 and A1 are unchanged. The website shows it as a third tab.

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
