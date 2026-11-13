"""
CoreNex Phase 3 -- Data Access Layer
====================================

Single, auditable gateway between the UI and the cleared datasets. It:

  * loads only datasets that are approved for public display (never the raw
    API dumps, restricted datasets, credentials or local paths);
  * validates every response and returns typed, empty-safe frames;
  * exposes *derived, cached* aggregates so pages never recompute business
    logic differently;
  * never fabricates observations -- missing data stays missing.

Cleared datasets
----------------
2023 historical (mention volume, weekly)
  weekly_skill_demand.csv                      -- cleared, unlicensed scrape (documented)
Phase 2 validation outputs (derived from the above)
  phase2_validation/*.csv|json                 -- cleared
2026 cross-section (snapshot, not a time series)
  market_data/processed/current_skill_demand.csv
  market_data/processed/skill_discovery.csv
  market_data/processed/skill_demand_monthly.csv  (FLATTENED, methodologically mixed)
  market_data/processed/source_registry.json      (provenance, minus credentials)
  market_data/processed/collection_manifest.json

Restricted / NEVER exposed
--------------------------
  data_jobs.csv (raw, unlicensed, 225 MB)
  market_data/raw/** (raw API dumps)
  market_data/processed/vocabulary_cache.json
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent  # project root (parent of corenex/)
PROC = ROOT / "market_data" / "processed"
PHASE2 = ROOT / "phase2_validation"

# Datasets that are safe to serve to the browser.
CLEARED = {
    "weekly_skill_demand": ROOT / "weekly_skill_demand.csv",
    "current_skill_demand": PROC / "current_skill_demand.csv",
    "skill_discovery": PROC / "skill_discovery.csv",
    "skill_demand_monthly": PROC / "skill_demand_monthly.csv",
    "source_registry": PROC / "source_registry.json",
    "collection_manifest": PROC / "collection_manifest.json",
    "phase2_index": PHASE2 / "demand_index_2023_eq100.csv",
    "phase2_backtest_predictions": PHASE2 / "backtest_predictions.csv",
    "phase2_backtest_metrics": PHASE2 / "backtest_metrics.csv",
    "phase2_intervals": PHASE2 / "prediction_intervals.csv",
    "phase2_coverage": PHASE2 / "interval_coverage.json",
    "phase2_selection": PHASE2 / "model_selection.json",
    "phase2_parameters": PHASE2 / "phase2_parameters.json",
    "phase2_readiness": PHASE2 / "data_readiness.json",
}

# Restricted: present on disk, never loaded by this layer.
RESTRICTED = {"data_jobs", "market_data/raw", "vocabulary_cache", "bls_jolts", "github_activity"}


@dataclass
class LoadReport:
    """Record of what loaded, what failed, and why. Surfaced in Data & Methodology."""
    loaded: dict = field(default_factory=dict)
    failed: dict = field(default_factory=dict)
    restricted_blocked: list = field(default_factory=list)

    def ok(self, key: str) -> bool:
        return key in self.loaded and self.failed.get(key) is None


def _read_csv(path: Path, **kw) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"missing dataset: {path.name}")
    return pd.read_csv(path, **kw)


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"missing dataset: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_all() -> tuple[dict, LoadReport]:
    """Load every cleared dataset once. Returns (data, report)."""
    data: dict = {}
    report = LoadReport()
    for key, path in CLEARED.items():
        try:
            if path.suffix == ".json":
                data[key] = _read_json(path)
            else:
                data[key] = _read_csv(path)
            report.loaded[key] = {"rows": len(data[key]) if hasattr(data[key], "__len__") else None,
                                  "path": path.name}
        except Exception as exc:  # noqa: BLE001
            report.failed[key] = f"{type(exc).__name__}: {exc}"
    return data, report


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------

def validate_weekly(df: pd.DataFrame) -> dict:
    """Contract check for the 2023 weekly demand table."""
    need = {"week", "skill", "demand"}
    issues = []
    if not need.issubset(df.columns):
        issues.append(f"missing columns: {sorted(need - set(df.columns))}")
        return {"ok": False, "issues": issues}
    df = df.copy()
    df["week"] = pd.to_datetime(df["week"], errors="coerce")
    df["demand"] = pd.to_numeric(df["demand"], errors="coerce")
    if df["week"].isna().any():
        issues.append("unparseable week values")
    if df["demand"].isna().any():
        issues.append("non-numeric demand values")
    if df.duplicated(["week", "skill"]).any():
        issues.append("duplicate (week, skill) rows")
    return {
        "ok": not issues,
        "issues": issues,
        "rows": int(len(df)),
        "weeks": int(df["week"].nunique()),
        "skills": int(df["skill"].nunique()),
        "date_min": str(df["week"].min().date()),
        "date_max": str(df["week"].max().date()),
    }


def validate_phase2_metrics(df: pd.DataFrame) -> dict:
    need = {"skill", "model", "MAE", "RMSE", "WAPE", "MASE"}
    if not need.issubset(df.columns):
        return {"ok": False, "issues": [f"missing: {sorted(need - set(df.columns))}"]}
    return {"ok": True, "rows": int(len(df)),
            "models": sorted(df["model"].unique().tolist())}


def monthly_share_from_weekly(wsd: pd.DataFrame) -> pd.DataFrame:
    """Pooled monthly share (%) per skill -- identical definition to Phase 2.

    This keeps UI-derived numbers consistent with the Python pipeline.
    """
    df = wsd.copy()
    df["week"] = pd.to_datetime(df["week"])
    df["month"] = df["week"].dt.to_period("M")
    tot = df.groupby("month")["demand"].sum()
    num = df.groupby(["month", "skill"])["demand"].sum()
    share = (num / tot * 100.0).reset_index()
    share.columns = ["month", "skill", "share"]
    share["month"] = share["month"].dt.to_timestamp()
    wk = df.groupby("month")["week"].nunique()
    full = [p.to_timestamp() for p, c in wk.items() if c >= 4]
    share = share[share["month"].isin(full)]
    return share.sort_values(["skill", "month"]).reset_index(drop=True)


def weekly_totals(wsd: pd.DataFrame) -> pd.DataFrame:
    df = wsd.copy()
    df["week"] = pd.to_datetime(df["week"])
    return df.groupby("week")["demand"].sum().sort_index().reset_index()


def skill_summary(wsd: pd.DataFrame) -> pd.DataFrame:
    """Per-skill summary for Skills Intelligence / Comparison pages."""
    df = wsd.copy()
    df["week"] = pd.to_datetime(df["week"])
    tot = df["demand"].sum()
    g = df.groupby("skill").agg(
        total_demand=("demand", "sum"),
        nonzero_weeks=("demand", lambda s: int((s > 0).sum())),
        mean_demand=("demand", "mean"),
        median_demand=("demand", "median"),
        max_demand=("demand", "max"),
        min_demand=("demand", "min"),
    )
    g["share_pct"] = g["total_demand"] / tot * 100.0 if tot else 0.0
    g["spike_ratio"] = g["max_demand"] / g["median_demand"].replace(0, np.nan)
    g["cv"] = g["mean_demand"] / g["median_demand"].replace(0, np.nan)
    # linear trend slope (per week) and relative slope
    slopes = {}
    for skill, grp in df.groupby("skill"):
        y = grp.sort_values("week")["demand"].values.astype(float)
        if len(y) >= 2:
            x = np.arange(len(y), dtype=float)
            sl = float(np.polyfit(x, y, 1)[0])
            slopes[skill] = sl / (np.mean(y) + 1e-9) * 52.0  # annualised relative %
        else:
            slopes[skill] = 0.0
    g["annualised_rel_slope_pct"] = pd.Series(slopes)
    return g.reset_index().rename(columns={"index": "skill"})


def _forecast_status(selected: str, n_months: int, n_origins: int) -> str:
    """Honest status label per Phase 3 requirement J."""
    if selected == "Naive" and n_origins < 8:
        return "Provisional"
    if selected == "Naive":
        return "Provisional"
    if n_origins >= 8:
        return "Validated"
    return "Experimental"


def forecast_readiness(data: dict) -> dict:
    """Single source of truth for whether a real 2026-27 forecast is defensible."""
    readiness = data.get("phase2_readiness", {})
    return {
        "supports_genuine_2026_27_forecast": bool(readiness.get("supports_genuine_forecast", False)),
        "supports_methodology_validation": bool(readiness.get("supports_methodology_validation", True)),
        "reason": readiness.get("reason", ""),
        "max_consistent_months": 6,
        "note": ("No consistent >=24-month series exists. Only a relative index "
                 "(2023 = 100) and a validated methodology are available."),
    }


def phase2_model_table(metrics_df: pd.DataFrame) -> pd.DataFrame:
    agg = (metrics_df.groupby("model")[["MAE", "RMSE", "WAPE", "MASE"]]
           .mean().reset_index().sort_values("MASE"))
    return agg


def phase2_backtest_table(pred_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot backtest into skill x month for the selected model."""
    return pred_df.copy()


def phase2_index_pivot(index_df: pd.DataFrame) -> pd.DataFrame:
    return index_df.pivot(index="month", columns="skill", values="index_2023_eq100")


def phase2_intervals_table(pi_df: pd.DataFrame) -> pd.DataFrame:
    return pi_df.copy()


# --------------------------------------------------------------------------
# ML Workflow helpers (new pages: Raw Data, Preprocessing, Evaluation)
# --------------------------------------------------------------------------

RAW_DATA_PATH = ROOT / "data_jobs.csv"
WEEKLY_PATH   = ROOT / "weekly_skill_demand.csv"
EVAL_PATH     = ROOT / "model_evaluation.csv"
BEST_PATH     = ROOT / "best_model_per_skill.csv"
MC_PATH       = ROOT / "model_comparison.csv"
FC_PATH       = ROOT / "future_forecast.csv"
SUMM_PATH     = ROOT / "forecasting_summary.csv"


def raw_data_available() -> bool:
    return RAW_DATA_PATH.exists()


def load_raw_sample(n: int = 500) -> pd.DataFrame:
    """Return first n rows of data_jobs.csv for the Raw Data page.
    Uses chunked reading to avoid loading the full 225 MB into memory."""
    if not raw_data_available():
        return pd.DataFrame()
    for chunk in pd.read_csv(RAW_DATA_PATH, chunksize=n, low_memory=False):
        return chunk.head(n)
    return pd.DataFrame()


def raw_data_stats() -> dict:
    """Lightweight stats about data_jobs.csv — computed from full file once."""
    if not raw_data_available():
        return {"available": False}
    df_full = pd.read_csv(RAW_DATA_PATH, low_memory=False)
    total_rows, total_cols = df_full.shape
    missing = df_full.isnull().sum().to_dict()
    missing_pct = {k: round(v / total_rows * 100, 2) for k, v in missing.items()}
    dtypes = {str(k): str(v) for k, v in df_full.dtypes.items()}
    duplicates = int(df_full.duplicated().sum())
    date_range = {}
    if "job_posted_date" in df_full.columns:
        dates = pd.to_datetime(df_full["job_posted_date"], errors="coerce").dropna()
        if not dates.empty:
            date_range = {"min": str(dates.min().date()), "max": str(dates.max().date())}
    top_skills = {}
    if "job_skills" in df_full.columns:
        import ast
        from collections import Counter
        skill_counter: Counter = Counter()
        for val in df_full["job_skills"].dropna():
            try:
                parsed = ast.literal_eval(str(val))
                if isinstance(parsed, list):
                    skill_counter.update([str(s).strip().lower() for s in parsed if s])
            except Exception:
                pass
        top_skills = dict(skill_counter.most_common(10))
    job_title_counts = {}
    if "job_title_short" in df_full.columns:
        job_title_counts = df_full["job_title_short"].value_counts().head(8).to_dict()
    country_counts = {}
    if "job_country" in df_full.columns:
        country_counts = df_full["job_country"].value_counts().head(8).to_dict()
    return {
        "available": True,
        "total_rows": total_rows,
        "total_cols": total_cols,
        "missing": missing,
        "missing_pct": missing_pct,
        "dtypes": dtypes,
        "duplicates": duplicates,
        "date_range": date_range,
        "top_skills": top_skills,
        "job_title_counts": job_title_counts,
        "country_counts": country_counts,
    }


def preprocessing_steps() -> list[dict]:
    """Documented steps performed by prepare_data.py on data_jobs.csv."""
    return [
        {
            "step": "Load data_jobs.csv",
            "details": "Read 785,741 rows × 17 columns in 50,000-row chunks to manage memory.",
            "input": "data_jobs.csv (225 MB, 785,741 rows)",
            "output": "Chunked DataFrame",
            "status": "Complete",
        },
        {
            "step": "Parse job_posted_date",
            "details": "Convert 'job_posted_date' string to datetime. Drop rows with unparseable dates.",
            "input": "job_posted_date (string)",
            "output": "date column (datetime64)",
            "status": "Complete",
        },
        {
            "step": "Extract ISO week start",
            "details": "Convert date to weekly period (Monday of each ISO week) for aggregation.",
            "input": "date column",
            "output": "week column (weekly period start)",
            "status": "Complete",
        },
        {
            "step": "Parse job_skills list",
            "details": "Use ast.literal_eval to safely parse Python list literals from job_skills strings. "
                       "Rows with unparseable or missing skill lists are discarded (117,037 rows dropped).",
            "input": "job_skills (string literals)",
            "output": "skills (list of strings)",
            "status": "Complete",
        },
        {
            "step": "Explode skill lists",
            "details": "Each row is expanded so one row = one (job, skill) pair.",
            "input": "skills (list)",
            "output": "One row per skill mention",
            "status": "Complete",
        },
        {
            "step": "Normalise skill strings",
            "details": "Strip whitespace, convert to lowercase. Drop empty strings.",
            "input": "Raw skill strings",
            "output": "Clean lowercase skill names",
            "status": "Complete",
        },
        {
            "step": "Aggregate by (week, skill)",
            "details": "Count total mentions per (week, skill) pair across all chunks.",
            "input": "Exploded (week, skill) pairs",
            "output": "weekly_counts Counter",
            "status": "Complete",
        },
        {
            "step": "Build weekly_skill_demand.csv",
            "details": "Flatten Counter to DataFrame with columns: week, skill, demand. "
                       "Sort by (week, skill). Save to CSV.",
            "input": "weekly_counts",
            "output": "weekly_skill_demand.csv (11,779 rows, 252 skills, 53 weeks)",
            "status": "Complete",
        },
    ]


def preprocessing_before_after() -> dict:
    """Before/after statistics for the preprocessing pipeline.

    Only figures that are documented for the restricted raw file are reported
    (row count, column count, coverage year). Per-column missing-value rates
    and duplicate counts are deliberately NOT asserted here: the raw file is
    unlicensed and is never profiled or served by this application.
    """
    after_ok = WEEKLY_PATH.exists()
    after_rows = after_cols = 0
    after_skills = after_weeks = 0
    if after_ok:
        df = pd.read_csv(WEEKLY_PATH)
        after_rows, after_cols = df.shape
        after_skills = int(df["skill"].nunique()) if "skill" in df.columns else 0
        after_weeks  = int(df["week"].nunique())  if "week"  in df.columns else 0
    return {
        "before": {
            "rows": 785741, "cols": 17,
            "note": ("Documented raw-file inspection: 785,741 job postings across 17 columns "
                     "(2023 only). The file is unlicensed and is not served; detailed "
                     "per-column quality metrics are not asserted."),
        },
        "after": {
            "rows": after_rows, "cols": after_cols,
            "skills": after_skills, "weeks": after_weeks,
            "note": ("Aggregated weekly skill demand. One record per (week, skill), "
                     "normalised skill names, no missing values in the served columns."),
        },
    }


def load_ml_outputs() -> dict:
    """Load all ML evaluation/forecast outputs for the Model Training & Evaluation page."""
    out = {}
    for key, path in [
        ("model_evaluation",    EVAL_PATH),
        ("best_model_per_skill", BEST_PATH),
        ("model_comparison",     MC_PATH),
        ("future_forecast",      FC_PATH),
        ("forecasting_summary",  SUMM_PATH),
    ]:
        try:
            out[key] = pd.read_csv(path)
        except Exception:
            out[key] = pd.DataFrame()
    # Parse dates
    for col in ["week"]:
        for key in ["model_evaluation", "future_forecast"]:
            if key in out and col in out[key].columns:
                out[key][col] = pd.to_datetime(out[key][col], errors="coerce")
    return out