"""
CoreNex Forecasting Engine v2.0
================================
Evaluates three forecasting models independently for every eligible skill:

  1. Previous Week Baseline   -- predicts the most recently observed demand
  2. Four-Week Moving Average -- predicts the mean of the last four observed weeks
  3. XGBoost Regressor        -- lag + rolling-mean features (identical to train_forecast.py)

Evaluation methodology
----------------------
Rolling one-step-ahead evaluation over the final TEST_WEEKS (8) weeks.
At each step i the model receives ONLY actual observations that precede
week (n - TEST_WEEKS + i).  Actual test values are NEVER fed back into
XGBoost features, so there is zero future-data leakage.

Outputs
-------
  model_evaluation.csv     -- per-week actual vs predicted for every skill & model
  model_comparison.csv     -- MAE / RMSE / sMAPE for every (skill, model) pair
  best_model_per_skill.csv -- winning model (lowest MAE) for each eligible skill
  future_forecast.csv      -- 12-week recursive forecast using the winning model
  forecasting_summary.csv  -- eligibility, model selection, coverage per skill
"""

import logging
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

INPUT_FILE         = "weekly_skill_demand.csv"
TEST_WEEKS         = 8      # weeks held out for rolling evaluation
MIN_NONZERO_WEEKS  = 12     # skill must have >= this many non-zero demand weeks
MIN_TRAIN_ROWS     = 15     # minimum feature rows needed to fit XGBoost
MAX_FORECAST_WEEKS = 12     # generate forecasts for weeks 1 .. 12

# XGBoost hyperparameters -- preserved from existing train_forecast.py
XGB_PARAMS = dict(
    n_estimators  = 150,
    max_depth     = 3,
    learning_rate = 0.03,
    objective     = "reg:squarederror",
    random_state  = 42,
    n_jobs        = 2,
)

MODEL_NAMES = ["Previous Week", "Moving Average", "XGBoost"]

OUT_EVAL       = "model_evaluation.csv"
OUT_COMPARISON = "model_comparison.csv"
OUT_BEST       = "best_model_per_skill.csv"
OUT_FORECAST   = "future_forecast.csv"
OUT_SUMMARY    = "forecasting_summary.csv"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt = "%H:%M:%S",
)
log = logging.getLogger("CoreNex")


# ---------------------------------------------------------------------------
# Feature Engineering
# ---------------------------------------------------------------------------

def make_features(series):
    """
    Build lag-1..4 and rolling-mean-4 features.
    Identical feature set to the existing train_forecast.py implementation.
    Returns DataFrame with columns: demand, lag_1..4, rolling_mean_4.
    First 4 rows contain NaN (callers must dropna() as appropriate).
    """
    data = pd.DataFrame({"demand": series.values}, index=series.index)
    for lag in [1, 2, 3, 4]:
        data[f"lag_{lag}"] = data["demand"].shift(lag)
    data["rolling_mean_4"] = data["demand"].shift(1).rolling(4).mean()
    return data


# ---------------------------------------------------------------------------
# Metric Helpers
# ---------------------------------------------------------------------------

def _smape(actual, predicted):
    """Symmetric Mean Absolute Percentage Error -- safe for zero-demand weeks."""
    denom = np.abs(actual) + np.abs(predicted)
    return float(np.mean(np.where(denom == 0, 0.0, 200.0 * np.abs(actual - predicted) / denom)))


def calc_metrics(actual, predicted):
    """Return dict with MAE, RMSE, sMAPE.  Predictions clamped to >= 0."""
    actual    = np.asarray(actual,    dtype=float)
    predicted = np.maximum(np.asarray(predicted, dtype=float), 0.0)
    return {
        "MAE"  : round(float(mean_absolute_error(actual, predicted)), 4),
        "RMSE" : round(float(np.sqrt(mean_squared_error(actual, predicted))), 4),
        "sMAPE": round(_smape(actual, predicted), 4),
    }


# ---------------------------------------------------------------------------
# XGBoost One-Step Prediction
# ---------------------------------------------------------------------------

def xgb_predict_next(hist):
    """
    Train XGBoost on hist and return a one-step-ahead prediction.

    If hist is too short to build MIN_TRAIN_ROWS feature rows, falls back to
    the 4-week moving average so evaluation is never blocked.

    Parameters
    ----------
    hist : pd.Series  Actual demand observations up to but NOT including
                      the prediction date.

    Returns
    -------
    float  Predicted demand >= 0.
    """
    features = make_features(hist).dropna()
    if len(features) < MIN_TRAIN_ROWS:
        return float(hist.iloc[-4:].mean()) if len(hist) >= 4 else float(hist.mean())

    X = features.drop(columns="demand")
    y = features["demand"]

    model = XGBRegressor(**XGB_PARAMS)
    model.fit(X, y, verbose=False)

    row = {
        "lag_1"         : float(hist.iloc[-1]),
        "lag_2"         : float(hist.iloc[-2]),
        "lag_3"         : float(hist.iloc[-3]),
        "lag_4"         : float(hist.iloc[-4]),
        "rolling_mean_4": float(hist.iloc[-4:].mean()),
    }
    return max(0.0, float(model.predict(pd.DataFrame([row]))[0]))


# ---------------------------------------------------------------------------
# Rolling One-Step-Ahead Evaluation
# ---------------------------------------------------------------------------

def rolling_evaluate(series):
    """
    Rolling one-step-ahead evaluation over the final TEST_WEEKS weeks.

    For test step i (i = 0 .. TEST_WEEKS-1):
      split      = len(series) - TEST_WEEKS
      hist       = series.iloc[:split + i]   -- actual values only
      prediction = model(hist)
      target     = series.iloc[split + i]    -- actual value (not fed back)

    Actual test observations are NEVER used as model inputs; only real
    historical values prior to each prediction date are used.

    Returns
    -------
    pd.DataFrame  Columns: week, actual_demand, Previous Week,
                            Moving Average, XGBoost
    """
    n     = len(series)
    split = n - TEST_WEEKS
    rows  = []

    for i in range(TEST_WEEKS):
        pred_idx = split + i
        hist     = series.iloc[:pred_idx]
        actual   = float(series.iloc[pred_idx])
        week     = series.index[pred_idx]

        # Previous Week
        pw = float(hist.iloc[-1]) if len(hist) >= 1 else 0.0

        # Four-Week Moving Average
        if len(hist) >= 4:
            ma = float(hist.iloc[-4:].mean())
        elif len(hist) > 0:
            ma = float(hist.mean())
        else:
            ma = 0.0

        # XGBoost (retrained on actual history at every step)
        xgb = xgb_predict_next(hist) if len(hist) >= 5 else ma

        rows.append({
            "week"          : week,
            "actual_demand" : actual,
            "Previous Week" : max(0.0, pw),
            "Moving Average": max(0.0, ma),
            "XGBoost"       : max(0.0, xgb),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Future Recursive Forecast
# ---------------------------------------------------------------------------

def generate_future_forecast(series, model_name, horizon=MAX_FORECAST_WEEKS):
    """
    Recursive future forecast using the specified model.
    Trained on the complete historical series.
    Predicted values accumulate in a buffer used as lags for subsequent steps.

    Parameters
    ----------
    series     : pd.Series  Complete historical weekly demand.
    model_name : str        One of "Previous Week", "Moving Average", "XGBoost".
    horizon    : int        Number of future weeks to forecast.

    Returns
    -------
    list of dicts  Keys: week, forecast_demand, horizon_weeks
    """
    history   = list(series.values.astype(float))
    last_date = series.index[-1]

    xgb_model = None
    if model_name == "XGBoost":
        features = make_features(series).dropna()
        if len(features) >= MIN_TRAIN_ROWS:
            X = features.drop(columns="demand")
            y = features["demand"]
            xgb_model = XGBRegressor(**XGB_PARAMS)
            xgb_model.fit(X, y, verbose=False)

    forecasts = []

    for step in range(1, horizon + 1):
        future_date = last_date + pd.Timedelta(weeks=step)

        if model_name == "Previous Week":
            pred = float(history[-1])

        elif model_name == "Moving Average":
            window = history[-4:] if len(history) >= 4 else history
            pred = float(np.mean(window))

        elif model_name == "XGBoost" and xgb_model is not None:
            row = {
                "lag_1"         : history[-1],
                "lag_2"         : history[-2],
                "lag_3"         : history[-3],
                "lag_4"         : history[-4],
                "rolling_mean_4": float(np.mean(history[-4:])),
            }
            pred = max(0.0, float(xgb_model.predict(pd.DataFrame([row]))[0]))

        else:
            window = history[-4:] if len(history) >= 4 else history
            pred = float(np.mean(window))

        pred = max(0.0, pred)
        history.append(pred)

        forecasts.append({
            "week"           : future_date,
            "forecast_demand": round(pred, 2),
            "horizon_weeks"  : step,
        })

    return forecasts


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def build_series(df, skill, full_index):
    """
    Aggregate demand for `skill`, reindex to cover every week in `full_index`,
    fill missing weeks with 0 (no job postings => zero demand that week).
    """
    sub = (
        df[df["skill"] == skill]
        .groupby("week")["demand"]
        .sum()
        .sort_index()
    )
    return sub.reindex(full_index, fill_value=0)


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def main():

    t_start = time.time()

    log.info("=" * 70)
    log.info("  CORENEX FORECASTING ENGINE v2.0")
    log.info("  Rolling one-step-ahead  |  Per-skill model selection")
    log.info("  3 models  |  All eligible skills  |  12-week future forecast")
    log.info("=" * 70)

    # Load & validate
    log.info(f"Loading {INPUT_FILE} ...")
    df = pd.read_csv(INPUT_FILE)
    df["week"] = pd.to_datetime(df["week"])

    dup_count  = df.duplicated(subset=["week", "skill"]).sum()
    null_count = df.isnull().sum().sum()
    log.info(f"  Rows: {len(df):,}  |  Duplicates: {dup_count}  |  Nulls: {null_count}")

    if dup_count:
        log.warning(f"  Dropping {dup_count} duplicate (week, skill) rows.")
        df = df.drop_duplicates(subset=["week", "skill"])

    df = df.sort_values(["skill", "week"]).reset_index(drop=True)

    full_index = pd.date_range(df["week"].min(), df["week"].max(), freq="7D")
    all_skills = sorted(df["skill"].unique())

    log.info(
        f"  Skills: {len(all_skills)}  |  Weeks: {len(full_index)}  "
        f"({full_index[0].date()} to {full_index[-1].date()})"
    )
    log.info(
        f"  Test window: last {TEST_WEEKS} weeks  |  "
        f"Eligibility threshold: >= {MIN_NONZERO_WEEKS} non-zero weeks"
    )
    log.info(
        f"  Forecast horizon: 1 to {MAX_FORECAST_WEEKS} weeks "
        f"beyond {full_index[-1].date()}"
    )
    log.info("")

    # Accumulators
    eval_rows       = []
    comparison_rows = []
    best_rows       = []
    forecast_rows   = []
    summary_rows    = []

    n_eligible   = 0
    n_ineligible = 0

    for idx, skill in enumerate(all_skills, 1):

        series      = build_series(df, skill, full_index)
        nonzero_wks = int((series > 0).sum())

        # Eligibility check
        if nonzero_wks < MIN_NONZERO_WEEKS:
            n_ineligible += 1
            reason = (
                f"only {nonzero_wks} non-zero demand weeks "
                f"(minimum required: {MIN_NONZERO_WEEKS})"
            )
            log.info(
                f"  [{idx:3d}/{len(all_skills)}]  SKIP    {skill:<26}"
                f"  |  {reason}"
            )
            summary_rows.append({
                "skill"             : skill,
                "eligible"          : False,
                "reason"            : reason,
                "num_nonzero_weeks" : nonzero_wks,
                "total_weeks"       : len(series),
                "best_model"        : None,
                "forecast_generated": False,
            })
            continue

        # Eligible
        n_eligible += 1
        log.info(
            f"  [{idx:3d}/{len(all_skills)}]  EVAL    {skill:<26}"
            f"  |  non-zero weeks: {nonzero_wks}/53"
        )

        # Rolling evaluation
        eval_df = rolling_evaluate(series)

        for _, row in eval_df.iterrows():
            for m in MODEL_NAMES:
                eval_rows.append({
                    "week"            : row["week"],
                    "skill"           : skill,
                    "model"           : m,
                    "actual_demand"   : row["actual_demand"],
                    "predicted_demand": round(float(row[m]), 2),
                })

        # Metrics
        actual        = eval_df["actual_demand"].values
        skill_metrics = {m: calc_metrics(actual, eval_df[m].values) for m in MODEL_NAMES}

        # Best model: lowest MAE, ties broken by RMSE
        best_model = min(
            skill_metrics,
            key=lambda m: (skill_metrics[m]["MAE"], skill_metrics[m]["RMSE"]),
        )

        for m in MODEL_NAMES:
            comparison_rows.append({
                "skill"        : skill,
                "model"        : m,
                "MAE"          : skill_metrics[m]["MAE"],
                "RMSE"         : skill_metrics[m]["RMSE"],
                "sMAPE"        : skill_metrics[m]["sMAPE"],
                "is_best_model": m == best_model,
            })

        best_rows.append({
            "skill"     : skill,
            "best_model": best_model,
            "MAE"       : skill_metrics[best_model]["MAE"],
            "RMSE"      : skill_metrics[best_model]["RMSE"],
            "sMAPE"     : skill_metrics[best_model]["sMAPE"],
        })

        # Future forecasts (weeks 1..MAX_FORECAST_WEEKS)
        fc_list = generate_future_forecast(series, best_model)
        for fc in fc_list:
            forecast_rows.append({
                "skill"           : skill,
                "week"            : fc["week"],
                "horizon_weeks"   : fc["horizon_weeks"],
                "forecast_demand" : fc["forecast_demand"],
                "model_used"      : best_model,
            })

        summary_rows.append({
            "skill"             : skill,
            "eligible"          : True,
            "reason"            : "ok",
            "num_nonzero_weeks" : nonzero_wks,
            "total_weeks"       : len(series),
            "best_model"        : best_model,
            "forecast_generated": True,
        })

    # Save outputs
    log.info("")
    log.info("Saving output files ...")

    pd.DataFrame(eval_rows).to_csv(OUT_EVAL, index=False)
    log.info(f"  {OUT_EVAL:<35}  {len(eval_rows):>7,} rows")

    pd.DataFrame(comparison_rows).to_csv(OUT_COMPARISON, index=False)
    log.info(f"  {OUT_COMPARISON:<35}  {len(comparison_rows):>7,} rows")

    pd.DataFrame(best_rows).to_csv(OUT_BEST, index=False)
    log.info(f"  {OUT_BEST:<35}  {len(best_rows):>7,} rows")

    pd.DataFrame(forecast_rows).to_csv(OUT_FORECAST, index=False)
    log.info(f"  {OUT_FORECAST:<35}  {len(forecast_rows):>7,} rows")

    pd.DataFrame(summary_rows).to_csv(OUT_SUMMARY, index=False)
    log.info(f"  {OUT_SUMMARY:<35}  {len(summary_rows):>7,} rows")

    # Final report
    best_df_out  = pd.DataFrame(best_rows)
    comp_df_out  = pd.DataFrame(comparison_rows)
    model_wins   = best_df_out["best_model"].value_counts()
    best_comp_df = comp_df_out[comp_df_out["is_best_model"]]
    avg_by_win   = best_comp_df.groupby("model")[["MAE","RMSE","sMAPE"]].mean().round(2)
    overall_avg  = best_comp_df[["MAE","RMSE","sMAPE"]].mean().round(2)

    elapsed = time.time() - t_start

    log.info("")
    log.info("=" * 70)
    log.info("  FINAL REPORT")
    log.info("=" * 70)
    log.info(f"  Total skills discovered       : {len(all_skills)}")
    log.info(f"  Successfully evaluated        : {n_eligible}")
    log.info(f"  Excluded (insufficient data)  : {n_ineligible}")
    log.info(f"  Future forecast rows saved    : {len(forecast_rows)}")
    log.info(f"  Pipeline runtime              : {elapsed:.1f}s")
    log.info("")
    log.info("  Model selection wins:")
    for m in MODEL_NAMES:
        count = int(model_wins.get(m, 0))
        pct   = count / max(n_eligible, 1) * 100
        log.info(f"    {m:<22}  ->  {count:>3} skills  ({pct:.1f}%)")
    log.info("")
    log.info("  Avg metrics (best-model selections only):")
    for m_name, row in avg_by_win.iterrows():
        log.info(
            f"    {m_name:<22}  "
            f"MAE={row['MAE']:.2f}  RMSE={row['RMSE']:.2f}  sMAPE={row['sMAPE']:.2f}%"
        )
    log.info(
        f"\n  Overall avg (best model per skill):"
        f"  MAE={overall_avg['MAE']:.2f}"
        f"  RMSE={overall_avg['RMSE']:.2f}"
        f"  sMAPE={overall_avg['sMAPE']:.2f}%"
    )
    log.info("=" * 70)

    return {
        "n_skills"    : len(all_skills),
        "n_eligible"  : n_eligible,
        "n_ineligible": n_ineligible,
        "model_wins"  : model_wins.to_dict(),
        "avg_MAE"     : float(overall_avg["MAE"]),
        "avg_RMSE"    : float(overall_avg["RMSE"]),
        "avg_sMAPE"   : float(overall_avg["sMAPE"]),
    }


if __name__ == "__main__":
    main()
