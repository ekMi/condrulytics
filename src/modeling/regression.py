import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURE_COLUMNS = [
    "distance",
    "race_month",
    "race_dayofyear",
    "prior_race_count",
    "prior_avg_speed",
    "prior_std_speed",
    "prior_best_speed",
    "prior_avg_z",
    "prior_std_z",
    "prior_best_z",
    "recent_speed_roll3",
    "recent_z_roll3",
    "days_since_last_race",
    "runner_history_years",
]


def load_features_from_db() -> pd.DataFrame:
    try:
        from ..loading.db_config import engine
    except ImportError:
        from src.loading.db_config import engine

    query = """
    SELECT
        a.analysis_id,
        a.source_result_id,
        a.runner_id,
        a.race_id,
        a.actual_time_sec AS target_time_sec,
        ra.distance,
        ra.year,
        EXTRACT(MONTH FROM ra.date)::int AS race_month,
        EXTRACT(DOY FROM ra.date)::int AS race_dayofyear,
        a.race_mean_speed,
        a.race_std_speed,
        a.prior_race_count,
        a.prior_avg_speed,
        a.prior_std_speed,
        a.prior_best_speed,
        a.prior_avg_z,
        a.prior_std_z,
        a.prior_best_z,
        a.recent_speed_roll3,
        a.recent_z_roll3,
        a.days_since_last_race,
        a.runner_history_years,
        a.target_z
    FROM fact_runner_race_analysis a
    JOIN dim_race ra ON a.race_id = ra.race_id
    """
    return pd.read_sql(query, engine)


def load_features_from_parquet(path: str) -> pd.DataFrame:
    df = pd.read_parquet(path)

    if "result_id" not in df.columns:
        if "source_result_id" not in df.columns:
            raise ValueError(
                "Le fichier de features doit contenir result_id ou source_result_id."
            )
    else:
        df["source_result_id"] = df["result_id"]

    if "target_time_sec" not in df.columns and "time_sec" in df.columns:
        df["target_time_sec"] = df["time_sec"]
    if "target_time_sec" not in df.columns and "actual_time_sec" in df.columns:
        df["target_time_sec"] = df["actual_time_sec"]

    if "distance" not in df.columns:
        raise ValueError("Le fichier de features doit contenir une colonne distance.")

    return df


def prepare_dataset(df: pd.DataFrame) -> pd.DataFrame:
    needed_columns = list(dict.fromkeys([
        "analysis_id",
        "source_result_id",
        "runner_id",
        "race_id",
        "year",
        "distance",
        "race_mean_speed",
        "race_std_speed",
        "target_z",
        "target_time_sec",
    ] + FEATURE_COLUMNS))

    data = df[[col for col in needed_columns if col in df.columns]].copy()
    data = data.replace([np.inf, -np.inf], np.nan)
    data = data.dropna(subset=["target_z", "target_time_sec", "race_std_speed"])

    if "analysis_id" in data.columns:
        data = data.dropna(subset=["analysis_id"])
        data["analysis_id"] = data["analysis_id"].astype(int)
    if "source_result_id" in data.columns:
        data["source_result_id"] = data["source_result_id"].astype(int)

    return data


def temporal_split(df: pd.DataFrame):
    years = sorted(df["year"].dropna().unique())

    if len(years) >= 2:
        test_year = years[-1]
        train_idx = df.index[df["year"] < test_year]
        test_idx = df.index[df["year"] == test_year]

        if len(train_idx) > 0 and len(test_idx) > 0:
            return train_idx, test_idx

    return train_test_split(df.index, test_size=0.2, random_state=42)


def build_model() -> Pipeline:
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("model", LinearRegression()),
        ]
    )


def predict_time(df: pd.DataFrame, predicted_z: np.ndarray) -> pd.DataFrame:
    prediction_columns = [
        "analysis_id",
        "source_result_id",
        "runner_id",
        "race_id",
        "target_z",
        "target_time_sec",
    ]
    pred = df[[col for col in prediction_columns if col in df.columns]].copy()
    pred["predicted_z"] = predicted_z
    pred["predicted_performance_index"] = 100 + 10 * pred["predicted_z"]

    pred["predicted_speed_kmh"] = (
        df["race_mean_speed"] + pred["predicted_z"] * df["race_std_speed"]
    )
    pred["predicted_speed_kmh"] = pred["predicted_speed_kmh"].clip(lower=1)
    pred["predicted_time_sec"] = df["distance"] / pred["predicted_speed_kmh"] * 3600
    pred["abs_error_time_sec"] = (
        pred["target_time_sec"] - pred["predicted_time_sec"]
    ).abs()

    return pred


def evaluate_predictions(pred: pd.DataFrame) -> dict:
    rmse_z = np.sqrt(mean_squared_error(pred["target_z"], pred["predicted_z"]))
    rmse_time = np.sqrt(
        mean_squared_error(pred["target_time_sec"], pred["predicted_time_sec"])
    )

    return {
        "mae_z": float(mean_absolute_error(pred["target_z"], pred["predicted_z"])),
        "rmse_z": float(rmse_z),
        "r2_z": float(r2_score(pred["target_z"], pred["predicted_z"])),
        "mae_time_sec": float(pred["abs_error_time_sec"].mean()),
        "rmse_time_sec": float(rmse_time),
        "n": int(len(pred)),
    }


def save_artifact(model: Pipeline, metrics: dict, path: str) -> str:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "features": FEATURE_COLUMNS,
            "metrics": metrics,
        },
        output_path,
    )
    return str(output_path)


def save_to_postgres(predictions: pd.DataFrame) -> int:
    try:
        from ..loading.db_config import engine
        from ..loading.models import FactRunnerRaceAnalysis, create_tables
    except ImportError:
        from src.loading.db_config import engine
        from src.loading.models import FactRunnerRaceAnalysis, create_tables

    from sqlalchemy import update

    create_tables()
    _ensure_analysis_prediction_columns(engine, FactRunnerRaceAnalysis.__table__)

    updated_rows = 0
    with engine.begin() as conn:
        conn.execute(
            update(FactRunnerRaceAnalysis).values(
                predicted_z=None,
                predicted_performance_index=None,
                predicted_speed_kmh=None,
                predicted_time_sec=None,
                abs_error_time_sec=None,
                split=None,
            )
        )

        for _, row in predictions.iterrows():
            values = {
                "predicted_z": float(row["predicted_z"]),
                "predicted_performance_index": float(row["predicted_performance_index"]),
                "predicted_speed_kmh": float(row["predicted_speed_kmh"]),
                "predicted_time_sec": float(row["predicted_time_sec"]),
                "abs_error_time_sec": float(row["abs_error_time_sec"]),
                "split": row["split"],
            }

            if "analysis_id" in row and not pd.isna(row["analysis_id"]):
                statement = (
                    update(FactRunnerRaceAnalysis)
                    .where(FactRunnerRaceAnalysis.analysis_id == int(row["analysis_id"]))
                    .values(**values)
                )
            else:
                statement = (
                    update(FactRunnerRaceAnalysis)
                    .where(FactRunnerRaceAnalysis.source_result_id == int(row["source_result_id"]))
                    .values(**values)
                )

            result = conn.execute(statement)
            updated_rows += result.rowcount or 0

    return updated_rows


def _ensure_analysis_prediction_columns(engine, table):
    with engine.begin() as conn:
        for column_name in [
            "predicted_z",
            "predicted_performance_index",
            "predicted_speed_kmh",
            "predicted_time_sec",
            "abs_error_time_sec",
            "split",
        ]:
            column = table.columns[column_name]
            column_type = column.type.compile(dialect=engine.dialect)
            conn.exec_driver_sql(
                f"ALTER TABLE {table.name} "
                f"ADD COLUMN IF NOT EXISTS {column.name} {column_type}"
            )


def train_regression(
    features_path: str | None = None,
    artifact_path: str = "models/linear_regression_z_score.joblib",
    save_db: bool = False,
):
    if features_path:
        df = load_features_from_parquet(features_path)
    else:
        df = load_features_from_db()

    data = prepare_dataset(df)
    train_idx, test_idx = temporal_split(data)

    train_df = data.loc[train_idx].copy()
    test_df = data.loc[test_idx].copy()

    model = build_model()
    model.fit(train_df[FEATURE_COLUMNS], train_df["target_z"])

    train_pred = predict_time(
        train_df,
        model.predict(train_df[FEATURE_COLUMNS]),
    )
    train_pred["split"] = "train"

    test_pred = predict_time(
        test_df,
        model.predict(test_df[FEATURE_COLUMNS]),
    )
    test_pred["split"] = "test"

    train_metrics = evaluate_predictions(train_pred)
    test_metrics = evaluate_predictions(test_pred)
    metrics = {
        "train": train_metrics,
        "test": test_metrics,
        "overfitting_gap": {
            "r2_z": float(train_metrics["r2_z"] - test_metrics["r2_z"]),
            "mae_time_sec": float(
                test_metrics["mae_time_sec"] - train_metrics["mae_time_sec"]
            ),
        },
    }

    artifact = save_artifact(model, metrics, artifact_path)
    predictions = pd.concat([train_pred, test_pred], ignore_index=True)

    saved_rows = 0
    if save_db:
        saved_rows = save_to_postgres(predictions)

    return {
        "model": model,
        "metrics": metrics,
        "artifact_path": artifact,
        "saved_rows": saved_rows,
        "predictions": predictions,
    }


def main():
    parser = argparse.ArgumentParser(description="Train linear z-score regression")
    parser.add_argument(
        "--features",
        default=None,
        help="Optional feature parquet path. If omitted, features are loaded from PostgreSQL.",
    )
    parser.add_argument(
        "--artifact",
        default="models/linear_regression_z_score.joblib",
        help="Output model artifact path",
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Save train/test historical predictions in fact_runner_race_analysis",
    )
    args = parser.parse_args()

    result = train_regression(args.features, args.artifact, args.save_db)

    print("Régression linéaire terminée")
    print(json.dumps(result["metrics"], indent=2, ensure_ascii=False))
    if result["saved_rows"]:
        print(f"analysis_rows_updated={result['saved_rows']}")


if __name__ == "__main__":
    main()
