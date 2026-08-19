from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import text

from .regression import FEATURE_COLUMNS


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ARTIFACT_PATH = PROJECT_ROOT / "models" / "linear_regression_z_score.joblib"


def _read_sql(engine, query: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params)


def _seconds_per_km(time_sec: float, distance: float) -> float:
    return time_sec / distance if distance else np.nan


def load_model_artifact(path: str | Path = DEFAULT_ARTIFACT_PATH) -> dict:
    artifact_path = Path(path)

    if not artifact_path.exists():
        return {
            "ok": False,
            "message": (
                "Aucun modèle entraîné n'a été trouvé. "
                "Lance d'abord python -m src.modeling.regression --save-db."
            ),
        }

    return {
        "ok": True,
        "artifact_path": str(artifact_path),
        "artifact": joblib.load(artifact_path),
    }


def build_prediction_features(
    engine,
    runner_id: int,
    race_id: int,
    min_history: int = 3,
) -> dict:
    race = _read_sql(
        engine,
        """
        SELECT race_id, name, distance, date, year
        FROM dim_race
        WHERE race_id = :race_id
        """,
        {"race_id": race_id},
    )

    if race.empty:
        return {"ok": False, "message": "Course introuvable."}

    race_row = race.iloc[0]
    race_date = pd.Timestamp(race_row["date"])

    already_run = _read_sql(
        engine,
        """
        SELECT 1
        FROM fact_results
        WHERE runner_id = :runner_id
          AND race_id = :race_id
        LIMIT 1
        """,
        {"runner_id": runner_id, "race_id": race_id},
    )

    if not already_run.empty:
        return {
            "ok": False,
            "message": "Ce coureur a déjà un résultat pour cette course.",
        }

    race_stats = _read_sql(
        engine,
        """
        SELECT
            COUNT(*) AS race_participants,
            AVG(speed_kmh) AS race_mean_speed,
            STDDEV_SAMP(speed_kmh) AS race_std_speed
        FROM fact_results
        WHERE race_id = :race_id
        """,
        {"race_id": race_id},
    ).iloc[0]

    if pd.isna(race_stats["race_std_speed"]) or race_stats["race_std_speed"] <= 0:
        return {
            "ok": False,
            "message": "La course sélectionnée n'a pas assez de résultats pour calculer une base fiable.",
        }

    history = _read_sql(
        engine,
        """
        WITH race_stats AS (
            SELECT
                race_id,
                AVG(speed_kmh) AS race_mean_speed,
                STDDEV_SAMP(speed_kmh) AS race_std_speed
            FROM fact_results
            GROUP BY race_id
        )
        SELECT
            f.speed_kmh,
            ra.date,
            (f.speed_kmh - rs.race_mean_speed) / NULLIF(rs.race_std_speed, 0) AS speed_z_race
        FROM fact_results f
        JOIN dim_race ra ON f.race_id = ra.race_id
        JOIN race_stats rs ON f.race_id = rs.race_id
        WHERE f.runner_id = :runner_id
          AND ra.date < :target_date
        ORDER BY ra.date, f.race_id
        """,
        {"runner_id": runner_id, "target_date": race_date},
    )

    history = history.dropna(subset=["speed_z_race"]).copy()
    if len(history) < min_history:
        return {
            "ok": False,
            "message": f"Il faut au moins {min_history} courses précédentes pour proposer une prédiction.",
        }

    history["date"] = pd.to_datetime(history["date"])
    last_date = history["date"].max()
    first_date = history["date"].min()

    feature_row = {
        "distance": float(race_row["distance"]),
        "race_month": int(race_date.month),
        "race_dayofyear": int(race_date.dayofyear),
        "prior_race_count": int(len(history)),
        "prior_avg_speed": float(history["speed_kmh"].mean()),
        "prior_std_speed": float(history["speed_kmh"].std()),
        "prior_best_speed": float(history["speed_kmh"].max()),
        "prior_avg_z": float(history["speed_z_race"].mean()),
        "prior_std_z": float(history["speed_z_race"].std()),
        "prior_best_z": float(history["speed_z_race"].max()),
        "recent_speed_roll3": float(history["speed_kmh"].tail(3).mean()),
        "recent_z_roll3": float(history["speed_z_race"].tail(3).mean()),
        "days_since_last_race": int((race_date - last_date).days),
        "runner_history_years": float((race_date - first_date).days / 365.25),
        "race_mean_speed": float(race_stats["race_mean_speed"]),
        "race_std_speed": float(race_stats["race_std_speed"]),
        "race_name": race_row["name"],
        "race_date": race_date,
    }

    return {"ok": True, "features": feature_row}


def predict_runner_race(
    engine,
    runner_id: int,
    race_id: int,
    min_history: int = 3,
    artifact_path: str = DEFAULT_ARTIFACT_PATH,
) -> dict:
    artifact_result = load_model_artifact(artifact_path)
    if not artifact_result["ok"]:
        return artifact_result

    feature_result = build_prediction_features(
        engine,
        runner_id=runner_id,
        race_id=race_id,
        min_history=min_history,
    )
    if not feature_result["ok"]:
        return feature_result

    artifact = artifact_result["artifact"]
    features = artifact.get("features", FEATURE_COLUMNS)
    row = pd.Series(feature_result["features"])
    x = pd.DataFrame([row])[features]

    predicted_z = float(artifact["model"].predict(x)[0])
    predicted_speed = max(
        row["race_mean_speed"] + predicted_z * row["race_std_speed"],
        1,
    )
    predicted_time = row["distance"] / predicted_speed * 3600

    return {
        "ok": True,
        "artifact_path": artifact_result["artifact_path"],
        **feature_result["features"],
        "predicted_z": predicted_z,
        "predicted_performance_index": 100 + 10 * predicted_z,
        "predicted_speed_kmh": predicted_speed,
        "predicted_time_sec": predicted_time,
        "predicted_pace_sec_km": _seconds_per_km(predicted_time, row["distance"]),
    }
