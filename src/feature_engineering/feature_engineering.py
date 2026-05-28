import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def load_data():
    try:
        from ..loading.db_config import engine
    except ImportError:
        from src.loading.db_config import engine

    query = """
    SELECT
        fr.result_id,
        fr.runner_id,
        fr.race_id,
        fr.time_sec,
        fr.speed_kmh,
        fr.position,
        fr.position_category,
        r.name AS race_name,
        r.distance,
        r.date,
        r.year
    FROM fact_results fr
    JOIN dim_race r ON fr.race_id = r.race_id
    """
    df = pd.read_sql(query, engine)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _shifted_expanding_mean(series: pd.Series) -> pd.Series:
    return series.shift(1).expanding(min_periods=1).mean()


def _shifted_expanding_std(series: pd.Series) -> pd.Series:
    return series.shift(1).expanding(min_periods=2).std()


def _shifted_expanding_max(series: pd.Series) -> pd.Series:
    return series.shift(1).expanding(min_periods=1).max()


def _shifted_rolling_mean(series: pd.Series, window: int) -> pd.Series:
    return series.shift(1).rolling(window, min_periods=1).mean()


def _add_race_normalization(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the race baseline and the runner's relative performance.

    speed_z_race is a race-normalized performance score: it measures how far
    the observed speed is from the average speed of the same race, in standard
    deviations. It is useful because runners from the same race share route,
    weather, ground condition and organization effects that are not explicitly
    available in the dataset.
    """

    df["race_participants"] = df.groupby("race_id")["runner_id"].transform("count")
    df["race_mean_speed"] = df.groupby("race_id")["speed_kmh"].transform("mean")
    df["race_std_speed"] = df.groupby("race_id")["speed_kmh"].transform("std")
    df["race_median_speed"] = df.groupby("race_id")["speed_kmh"].transform("median")

    race_std = df["race_std_speed"].replace(0, np.nan)
    df["speed_z_race"] = (df["speed_kmh"] - df["race_mean_speed"]) / race_std

    # User-facing scale: 100 = average in the race, +10 = one std dev faster.
    df["performance_index"] = 100 + 10 * df["speed_z_race"]

    return df


def _add_runner_history(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build runner features using only races before the current row.

    These columns are suitable for predictive modeling because they avoid using
    the current or future result to describe the runner before a race.
    """

    df = df.sort_values(["runner_id", "date", "race_id"]).copy()
    runners = df.groupby("runner_id", group_keys=False)

    df["prior_race_count"] = runners.cumcount()
    df["prior_avg_speed"] = runners["speed_kmh"].transform(_shifted_expanding_mean)
    df["prior_std_speed"] = runners["speed_kmh"].transform(_shifted_expanding_std)
    df["prior_best_speed"] = runners["speed_kmh"].transform(_shifted_expanding_max)

    df["prior_avg_z"] = runners["speed_z_race"].transform(_shifted_expanding_mean)
    df["prior_std_z"] = runners["speed_z_race"].transform(_shifted_expanding_std)
    df["prior_best_z"] = runners["speed_z_race"].transform(_shifted_expanding_max)

    df["recent_speed_roll3"] = runners["speed_kmh"].transform(
        lambda s: _shifted_rolling_mean(s, 3)
    )
    df["recent_z_roll3"] = runners["speed_z_race"].transform(
        lambda s: _shifted_rolling_mean(s, 3)
    )

    df["days_since_last_race"] = runners["date"].diff().dt.days
    first_seen_date = runners["date"].transform("first")
    df["runner_history_years"] = (df["date"] - first_seen_date).dt.days / 365.25

    return df


def _add_race_context(df: pd.DataFrame) -> pd.DataFrame:
    df["race_month"] = df["date"].dt.month
    df["race_dayofyear"] = df["date"].dt.dayofyear
    return df


def build_features(df: pd.DataFrame, min_history: int = 2) -> pd.DataFrame:
    """
    Build an analysis/modeling dataset.

    The intended modeling path is to predict a runner's expected normalized
    performance (target_z) for a race, then convert this predicted z-score into
    an expected speed and time using a race baseline.
    """

    df = df.copy()
    df = df.sort_values(["runner_id", "date", "race_id"])

    df = _add_race_normalization(df)
    df = _add_runner_history(df)
    df = _add_race_context(df)

    df["source_result_id"] = df["result_id"]
    df["actual_position"] = df["position"]
    df["actual_position_category"] = df["position_category"]
    df["actual_time_sec"] = df["time_sec"]
    df["actual_speed_kmh"] = df["speed_kmh"]
    df["target_z"] = df["speed_z_race"]

    df = df.replace([np.inf, -np.inf], np.nan)
    df = df[df["prior_race_count"] >= min_history]
    df = df[df["target_z"].notna()]

    return df


def save(df, path: str = "data/features/features_ml.parquet"):
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)


def save_to_postgres(df: pd.DataFrame):
    try:
        from ..loading.db_config import engine
        from ..loading.models import FactRunnerRaceAnalysis, create_tables
    except ImportError:
        from src.loading.db_config import engine
        from src.loading.models import FactRunnerRaceAnalysis, create_tables

    create_tables()
    _ensure_analysis_columns(engine, FactRunnerRaceAnalysis.__table__)

    columns = [
        col.name
        for col in FactRunnerRaceAnalysis.__table__.columns
        if col.name != "analysis_id"
    ]
    db_df = df[[col for col in columns if col in df.columns]].copy()
    records = [
        {
            key: (None if pd.isna(value) else value.item() if hasattr(value, "item") else value)
            for key, value in row.items()
        }
        for row in db_df.to_dict("records")
    ]

    with engine.begin() as conn:
        conn.execute(FactRunnerRaceAnalysis.__table__.delete())
        if records:
            conn.execute(FactRunnerRaceAnalysis.__table__.insert(), records)


def _ensure_analysis_columns(engine, table):
    with engine.begin() as conn:
        for column in table.columns:
            if column.primary_key:
                continue

            column_type = column.type.compile(dialect=engine.dialect)
            conn.exec_driver_sql(
                f"ALTER TABLE {table.name} "
                f"ADD COLUMN IF NOT EXISTS {column.name} {column_type}"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build feature dataset")
    parser.add_argument(
        "--output",
        default="data/features/features_ml.parquet",
        help="Output parquet path",
    )
    parser.add_argument(
        "--min-history",
        type=int,
        default=2,
        help="Minimum previous races required for a training row",
    )
    parser.add_argument(
        "--save-db",
        action="store_true",
        help="Also write features to PostgreSQL table fact_runner_race_analysis",
    )

    args = parser.parse_args()

    df = load_data()
    df = build_features(df, min_history=args.min_history)
    save(df, args.output)

    if args.save_db:
        save_to_postgres(df)

    print("Feature engineering terminé")
