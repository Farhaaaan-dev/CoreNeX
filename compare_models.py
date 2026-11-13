
import pandas as pd
import numpy as np

from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

print("CORENEX - MODEL COMPARISON EXPERIMENT")

df = pd.read_csv("weekly_skill_demand.csv")
df["week"] = pd.to_datetime(df["week"])

top_skills = (
    df.groupby("skill")["demand"]
    .sum()
    .nlargest(5)
    .index.tolist()
)

all_results = []

for skill in top_skills:

    print("\nEvaluating:", skill)

    data = df[df["skill"] == skill]

    series = (
        data.groupby("week")["demand"]
        .sum()
        .sort_index()
    )

    index = pd.date_range(
        series.index.min(),
        series.index.max(),
        freq="7D"
    )

    series = series.reindex(index, fill_value=0)

    features = pd.DataFrame({"demand": series})

    for lag in [1, 2, 3, 4]:
        features[f"lag_{lag}"] = series.shift(lag)

    features["rolling_mean_4"] = (
        series.shift(1).rolling(4).mean()
    )

    features = features.dropna()

    split = len(features) - 8

    if split < 15:
        print("Insufficient history - skipped")
        continue

    train = features.iloc[:split]
    test = features.iloc[split:]

    X_train = train.drop(columns="demand")
    y_train = train["demand"]

    X_test = test.drop(columns="demand")
    y_test = test["demand"]

    # Model A: Previous-week baseline
    previous_week = X_test["lag_1"].values

    # Model B: Four-week moving average
    moving_average = X_test["rolling_mean_4"].values

    # Model C: XGBoost
    model = XGBRegressor(
        n_estimators=150,
        max_depth=3,
        learning_rate=0.03,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=2
    )

    model.fit(X_train, y_train)

    xgb_prediction = np.maximum(
        model.predict(X_test), 0
    )

    predictions = {
        "Previous Week": previous_week,
        "Moving Average": moving_average,
        "XGBoost": xgb_prediction
    }

    for model_name, pred in predictions.items():

        mae = mean_absolute_error(y_test, pred)

        rmse = np.sqrt(
            mean_squared_error(y_test, pred)
        )

        denominator = (
            np.abs(y_test.values) + np.abs(pred)
        )

        smape = np.mean(
            np.where(
                denominator == 0,
                0,
                200 * np.abs(
                    y_test.values - pred
                ) / denominator
            )
        )

        all_results.append({
            "skill": skill,
            "model": model_name,
            "MAE": round(mae, 2),
            "RMSE": round(rmse, 2),
            "sMAPE": round(smape, 2)
        })

        print(
            model_name,
            "| MAE:", round(mae, 2),
            "| RMSE:", round(rmse, 2),
            "| sMAPE:", round(smape, 2)
        )

results = pd.DataFrame(all_results)

results.to_csv(
    "model_comparison.csv",
    index=False
)

print("\n========== FINAL MODEL COMPARISON ==========")

print(
    results.sort_values(["skill", "MAE"])
    .to_string(index=False)
)

print("\nSaved: model_comparison.csv")
print("COMPARISON COMPLETED!")
