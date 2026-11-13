# CoreNex — Phase 3 Completion Report (UI/UX)

**Status:** Complete. All 7 pages implemented, verified in a real browser at 4 viewports.
**Date:** 2026-11-12
**Scope:** Phase 3 only (UI/UX). Phase 0 ingestion, Phase 1 methodology validation and
Phase 2 backtest outputs are consumed read-only and were **not** modified.

---

## 1. What was built

A new Streamlit application that presents the already-validated CoreNex data and Phase 2
results as a professional, interactive analytics product — without changing the underlying
methodology, data or any Phase 2 artifact.

The legacy `corenex_app.py` (78 KB) was left **untouched**. The new app is a separate
entry point (`app.py`) with its own data-access and design-system layers.

| Layer | File | Purpose |
|---|---|---|
| Entry point | `app.py` (645 lines) | Sidebar navigation, 7 page renderers, cached data loading |
| Data access | `corenex/data_access.py` (201 lines) | Loads + validates only cleared datasets; derived aggregates; forecast readiness |
| Design system | `corenex/ui.py` (198 lines) | Palette, CSS, KPI cards, badges, status pills, empty/error states, chart layout |
| Package | `corenex/__init__.py` | Package marker |
| Tests | `tests_ui.py` (141 lines) | Streamlit `AppTest` smoke + interaction tests |
| Browser checks | `verify_ui.py` (206 lines) | Real headless-Chrome run via CDP: errors, charts, overflow, 4 viewports |

---

## 2. Pages

| # | Page | Key content | Interactive |
|---|---|---|---|
| 1 | **Overview** | Executive KPIs, demand concentration, 2026 cross-section, readiness banner | — |
| 2 | **Skills Intelligence** | Searchable directory of 252 skills, skill profile, trajectory | search, min-share slider, sort, skill select |
| 3 | **Demand Analytics** | Weekly/monthly demand, share vs volume, concentration, index | month range, chart mode |
| 4 | **Monthly Forecasts** | Phase 2 backtest evidence, model comparison, honest forecast panel | horizon, skill |
| 5 | **Technology Comparison** | Compare up to 6 skills on a normalised basis | multi-select (≤6) |
| 6 | **Data & Methodology** | Provenance registry, licensing, methodology, model table, limitations | — |
| 7 | **About CoreNex** | Plain-language explainer of metrics and data policy | — |

Navigation is a collapsed sidebar radio. Each page is also deep-linkable, e.g.
`http://localhost:8501/?page=demand-analytics` (used by the verification harness).

---

## 3. Design system

- Dark navy theme inherited from the existing `.streamlit/config.toml`.
- Central palette in `corenex/ui.py` (`C` dict): surface, panel, border, text/text2/text3,
  accent, plus semantic `STATUS_COLORS` (green/amber/red) and `MODEL_COLORS`.
- Reusable components: `inject_css()`, `page_header()`, `section_label()`, `kpi()` /
  `kpi_row()`, `badge()` / `status_badge()`, `empty_state()`, `error_state()`,
  `panel()`, `model_color()`, `trend_color()`.
- Charts share one Plotly base via `plotly_layout()` / `apply_layout()`, which merges
  axis overrides instead of overwriting them (fixed after testing).
- Responsive by construction: Streamlit columns collapse; verified no horizontal overflow
  at 1440 / 1280 / 834 / 390 px.

---

## 4. Data integrity

`corenex/data_access.py` loads exactly the **14 cleared datasets** and nothing else:

```
weekly_skill_demand (11779, 3)   current_skill_demand (404, 9)
skill_demand_monthly (4410, 7)   skill_discovery (444, 10)
phase2_backtest_metrics (420, 8) phase2_backtest_predictions (420, 6)
phase2_intervals (10, 9)         phase2_index (120, 4)
source_registry / collection_manifest / phase2_{selection,coverage,parameters,readiness}
```

**Restricted data is never served.** `data_jobs.csv`, `market_data/raw/**`,
`vocabulary_cache.json`, credentials and local absolute paths appear only as a declared
deny-list and as explanatory text — never as data. No observation is fabricated; the app
states its own limits on the About and Data & Methodology pages.

Forecast readiness is surfaced honestly rather than implied:

```
supports_genuine_2026_27_forecast: False
reason: only 1 year of data; 2026 corpus is methodologically fragmented
max_consistent_months: 6
```

The Monthly Forecasts page therefore shows Phase 2 backtest evidence and a relative
2023=100 index, explicitly labelled as **not** a Dec 2026–2027 absolute forecast.

---

## 5. Testing performed

### 5.1 `AppTest` smoke + interaction (`tests_ui.py`) — all pass

```
[PASS] app loads without exception
[PASS] Overview / Skills Intelligence / Demand Analytics / Monthly Forecasts
[PASS] Technology Comparison / Data & Methodology / About CoreNex
[PASS] skills search filters (252 -> 1 rows)
[PASS] skills empty state shown
[PASS] forecast horizon control works
[PASS] comparison multiselect works (options=60, picked=2)
[PASS] demand range control works
[PASS] Phase 2 outputs unchanged
RESULT: all UI smoke tests passed
```

### 5.2 Real browser verification (`verify_ui.py`) — 28/28 pass

Headless Chrome driven over the DevTools Protocol; every page at desktop (1440×900),
laptop (1280×800), tablet (834×1112) and mobile (390×844). For each page/viewport the
harness asserts: no uncaught exception, no console error, no Streamlit exception element,
expected heading present, charts actually rendered (SVG marks), no horizontal overflow.

Representative results:

```
[PASS] desktop  overview              charts=6 marks=40  tables=0 inputs=8
[PASS] desktop  skills-intelligence   charts=3 marks=63  tables=2 inputs=14
[PASS] desktop  demand-analytics      charts=9 marks=127 tables=0 inputs=12
[PASS] desktop  monthly-forecasts     charts=3 marks=35  tables=2 inputs=14
[PASS] desktop  technology-comparison charts=6 marks=36  tables=2 inputs=9
[PASS] mobile   overview              charts=6 marks=40  tables=0 inputs=8  overflow=0
RESULT: 28/28 page/viewport checks passed
```

### 5.3 Bugs found and fixed during verification

1. `plotly_layout()` returned a dict containing `xaxis`/`yaxis`, so call sites passing
   `xaxis=...` raised `got multiple values for keyword argument` on 4 of 7 pages.
   Fixed with a merge-safe `apply_layout()` helper and updated all call sites.
2. `Monthly Forecasts` crashed with
   `can only concatenate str (not "MonthBegin") to str` — `last_month` came back as a
   string from the index. Fixed by coercing with `pd.Timestamp(...)`.
3. Sidebar radio was inaccessible to `AppTest` before the first run (widget tree empty).
   Fixed in the test harness, not the app.

### 5.4 Phase 2 outputs unchanged

`tests_ui.py` hashes all Phase 2 artifacts before and after the UI test and asserts they
are byte-identical: `backtest_metrics.csv`, `backtest_predictions.csv`,
`prediction_intervals.csv`, `interval_coverage.json`, `model_selection.json`,
`demand_index_2023_eq100.csv`. Result: **unchanged**.

---

## 6. Screenshots

Captured in `docs/screenshots/` (28 PNGs) — every page at desktop, plus `-tablet` and
`-mobile` variants for responsive evidence:

```
overview.png              skills-intelligence.png     demand-analytics.png
monthly-forecasts.png     technology-comparison.png   data-and-methodology.png
about-corenex.png
overview-{tablet,mobile}.png   ... (same pattern for all 7 pages)
```

---

## 7. How to run

```powershell
py -m pip install -r requirements.txt
streamlit run app.py
# open http://localhost:8501
```

Optional:

```powershell
py -m pip install -r requirements-analysis.txt   # re-run Phase 0/1/2 scripts
py -m pip install websockets                     # run verify_ui.py
python tests_ui.py                               # AppTest smoke + interaction suite
python verify_ui.py                              # real-browser checks (needs Chrome/Edge)
```

Requires Python 3.14 with the pinned versions in `requirements.txt`
(`streamlit 1.67.0`, `pandas 3.1.1`, `numpy 2.5.0`, `plotly 7.1.0`, `pyarrow 26.0.1`).

---

## 8. Known limitations (carried forward, not introduced here)

- **2023 only (N = 1 year):** trend and seasonality cannot be separated; no genuine
  Dec 2026–2027 absolute forecast is supported. The app says so and shows a relative index.
- **`demand` = skill mentions, not postings/vacancies/headcount.** Volume drifts with
  source mix; only relative shares are near-stationary.
- **2026 monthly series is methodologically fragmented** (different source and method each
  month, structural break at Jun→Jul) and is presented as a cross-section only.
- **Prediction intervals are indicative** — empirical residual quantiles calibrated on
  backtest residuals. Mean empirical coverage 83.33% against an 80% target, but estimated
  from only 6 backtest origins per skill (10 skills), so intervals are indicative, not
  guaranteed.
- **Selected model is Naive.** No candidate beat Naive by the pre-registered ≥10% MASE
  margin, so no complex model is claimed as better.
- Web UI is unauthenticated; it is a local analytical tool, not a public deployment.

---

## 9. Recommended next improvements

1. **Extend the series to ≥24 months** by pinning one source/method — the single change
   that unlocks a genuine forecast (Phase 1/2 recommendation S0/S1).
2. **Re-run Phase 2 with ≥24 months** and re-select the model under the same MASE rule.
3. **Per-skill forecast view** once a longer series exists, with calibrated intervals.
4. **CSV export** of the directory, backtest metrics and index.
5. **Light theme + PDF/PNG export** of the Data & Methodology page for stakeholders.
6. **Automated visual regression** using the existing `verify_ui.py` screenshots as baselines.
7. **Authentication** if this is ever exposed beyond localhost.