
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from xgboost import XGBRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

print("===================================")
print(" CORENEX AI FORECASTING ENGINE")
print("===================================")

# Load processed historical data
df = pd.read_csv("weekly_skill_demand.csv")
df["week"] = pd.to_datetime(df["week"])

# Select the most demanded skills
top_skills = (
    df.groupby("skill")["demand"]
    .sum()
    .nlargest(5)
    .index.tolist()
)

print("\nSkills selected:", top_skills)

def make_features(series):
    data = pd.DataFrame({"demand": series})

    for lag in [1, 2, 3, 4]:
        data[f"lag_{lag}"] = data["demand"].shift(lag)

    data["rolling_mean_4"] = (
        data["demand"].shift(1)
        .rolling(4).mean()
    )

    return data.dropna()

results = []
future_results = []

for skill in top_skills:

    print(f"\nTraining model for: {skill}")

    # Create continuous weekly time series
    skill_data = df[df["skill"] == skill]

    series = (
        skill_data.groupby("week")["demand"]
        .sum()
        .sort_index()
    )

    full_index = pd.date_range(
        series.index.min(),
        series.index.max(),
        freq="7D"
    )

    series = series.reindex(
        full_index,
        fill_value=0
    )

    features = make_features(series)

    # Reserve final 8 weeks for testing
    split = len(features) - 8

    if split < 15:
        print("Not enough historical data. Skipping.")
        continue

    train = features.iloc[:split]
    test = features.iloc[split:]

    X_train = train.drop(columns=["demand"])
    y_train = train["demand"]

    X_test = test.drop(columns=["demand"])
    y_test = test["demand"]

    # Train XGBoost
    model = XGBRegressor(
        n_estimators=150,
        max_depth=3,
        learning_rate=0.03,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=2
    )

    model.fit(X_train, y_train)

    predictions = model.predict(X_test)
    predictions = np.maximum(predictions, 0)

    # Baseline: previous week's demand
    baseline = series.shift(1).loc[test.index].values

    # Evaluation
    mae = mean_absolute_error(y_test, predictions)

    rmse = np.sqrt(
        mean_squared_error(y_test, predictions)
    )

    denominator = (
        np.abs(y_test.values) +
        np.abs(predictions)
    )

    smape = np.mean(
        np.where(
            denominator == 0,
            0,
            200 * np.abs(y_test.values - predictions)
            / denominator
        )
    )

    baseline_mae = mean_absolute_error(
        y_test,
        baseline
    )

    print("Test MAE:", round(mae, 2))
    print("Test RMSE:", round(rmse, 2))
    print("Test sMAPE:", round(smape, 2), "%")
    print("Baseline MAE:", round(baseline_mae, 2))

    # Save actual vs predicted
    for date, actual, predicted in zip(
        test.index, y_test, predictions
    ):
        results.append({
            "skill": skill,
            "week": date,
            "actual_demand": actual,
            "predicted_demand": round(float(predicted), 2)
        })

    # Retrain on all available history
    final_model = XGBRegressor(
        n_estimators=150,
        max_depth=3,
        learning_rate=0.03,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=2
    )

    final_model.fit(
        features.drop(columns=["demand"]),
        features["demand"]
    )

    # Forecast next 4 weeks recursively
    history = list(series.values)

    for step in range(4):

        row = {
            "lag_1": history[-1],
            "lag_2": history[-2],
            "lag_3": history[-3],
            "lag_4": history[-4],
            "rolling_mean_4": np.mean(history[-4:])
        }

        prediction = float(
            final_model.predict(
                pd.DataFrame([row])
            )[0]
        )

        prediction = max(0, prediction)

        history.append(prediction)

        future_date = (
            series.index[-1] +
            pd.Timedelta(weeks=step + 1)
        )

        future_results.append({
            "skill": skill,
            "week": future_date,
            "forecast_demand": round(prediction, 2)
        })

# Save evaluation and forecast files
pd.DataFrame(results).to_csv(
    "model_evaluation.csv",
    index=False
)

pd.DataFrame(future_results).to_csv(
    "future_forecast.csv",
    index=False
)

print("\n===================================")
print("FORECASTING COMPLETED!")
print("===================================")

print("\nEvaluation saved: model_evaluation.csv")
print("Future predictions saved: future_forecast.csv")

# Plot one skill's actual vs predicted results
if results:
    output = pd.DataFrame(results)
    selected = output["skill"].iloc[0]
    plot_data = output[output["skill"] == selected]

    plt.figure(figsize=(10, 5))

    plt.plot(
        plot_data["week"],
        plot_data["actual_demand"],
        marker="o",
        label="Actual Demand"
    )

    plt.plot(
        plot_data["week"],
        plot_data["predicted_demand"],
        marker="o",
        linestyle="--",
        label="XGBoost Prediction"
    )

    plt.title(
        f"CoreNex: Actual vs Predicted Demand - {selected}"
    )

    plt.xlabel("Week")
    plt.ylabel("Job Skill Mentions")
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("forecast_comparison.png", dpi=150)
    plt.show()

    print("\nGraph saved: forecast_comparison.png")
