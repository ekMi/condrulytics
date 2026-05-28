import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from db import engine, run_query, table_exists

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from src.modeling.serving import DEFAULT_ARTIFACT_PATH, predict_runner_race


RACE_PAGE = "pages/2_Courses.py"


def get_query_int(name):
    value = st.query_params.get(name)
    if isinstance(value, list):
        value = value[0] if value else None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def format_time(seconds):
    if pd.isna(seconds):
        return ""

    seconds = int(round(seconds))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"


def format_pace(seconds_per_km):
    if pd.isna(seconds_per_km):
        return ""

    seconds = int(round(seconds_per_km))
    return f"{seconds // 60:d}:{seconds % 60:02d}/km"


def open_race(race_id):
    st.session_state["selected_race_id"] = int(race_id)
    st.switch_page(RACE_PAGE)


def make_numeric_domain(dataframe, columns, min_margin=1.0):
    values = []

    for column in columns:
        if column in dataframe.columns:
            values.append(pd.to_numeric(dataframe[column], errors="coerce"))

    if not values:
        return None

    all_values = pd.concat(values).dropna()
    if all_values.empty:
        return None

    min_value = float(all_values.min())
    max_value = float(all_values.max())
    margin = max(min_margin, (max_value - min_value) * 0.08)

    return [min_value - margin, max_value + margin]


st.title("Coureurs")

runners = run_query(
    """
    SELECT runner_id, name_clean
    FROM dim_runner
    ORDER BY name_clean
    """
)

if runners.empty:
    st.warning("Aucun coureur disponible.")
    st.stop()

labels = {row.runner_id: row.name_clean for row in runners.itertuples()}
query_runner_id = st.session_state.pop("selected_runner_id", None)
if query_runner_id is None:
    query_runner_id = get_query_int("runner_id")

selectbox_index = 0
runner_ids = runners["runner_id"].astype(int).tolist()
if query_runner_id is not None and query_runner_id in runner_ids:
    selectbox_index = runner_ids.index(query_runner_id)

runner_id = st.selectbox(
    "Coureur",
    runners["runner_id"],
    format_func=lambda value: labels[value],
    index=selectbox_index,
)
st.query_params["runner_id"] = str(int(runner_id))

has_predictions = table_exists("fact_runner_race_analysis")
has_model_artifact = Path(DEFAULT_ARTIFACT_PATH).exists()

prediction_select = """
    a.predicted_performance_index,
    a.predicted_time_sec,
    a.predicted_z
""" if has_predictions else """
    NULL::double precision AS predicted_performance_index,
    NULL::double precision AS predicted_time_sec,
    NULL::double precision AS predicted_z
"""

prediction_join = (
    """
    LEFT JOIN fact_runner_race_analysis a
        ON a.runner_id = f.runner_id
       AND a.race_id = f.race_id
    """
    if has_predictions
    else ""
)

history = run_query(
    f"""
    WITH race_stats AS (
        SELECT
            race_id,
            AVG(speed_kmh) AS race_mean_speed,
            STDDEV_SAMP(speed_kmh) AS race_std_speed
        FROM fact_results
        GROUP BY race_id
    )
    SELECT
        f.result_id,
        f.race_id,
        ra.date,
        ra.year,
        ra.name AS race,
        ra.distance,
        f.position,
        f.position_category,
        f.time_sec,
        f.speed_kmh,
        f.category_clean,
        (f.speed_kmh - rs.race_mean_speed) / NULLIF(rs.race_std_speed, 0) AS speed_z_race,
        100 + 10 * ((f.speed_kmh - rs.race_mean_speed) / NULLIF(rs.race_std_speed, 0)) AS performance_index,
        {prediction_select}
    FROM fact_results f
    JOIN dim_race ra ON f.race_id = ra.race_id
    JOIN race_stats rs ON f.race_id = rs.race_id
    {prediction_join}
    WHERE f.runner_id = :runner_id
    ORDER BY ra.date
    """,
    {"runner_id": int(runner_id)},
)

if history.empty:
    st.warning("Aucun résultat disponible pour ce coureur.")
    st.stop()

history["date"] = pd.to_datetime(history["date"])
history["time"] = history["time_sec"].apply(format_time)
history["pace_sec_km"] = history["time_sec"] / history["distance"]
history["pace"] = history["pace_sec_km"].apply(format_pace)
history["speed"] = history["speed_kmh"].round(2).astype(str) + " km/h"
history["predicted_time"] = history["predicted_time_sec"].apply(format_time)
history["time_gap_sec"] = history["time_sec"] - history["predicted_time_sec"]
history["index_gap"] = history["performance_index"] - history["predicted_performance_index"]

total_distance = history["distance"].sum()
avg_pace = history["pace_sec_km"].mean()
avg_index = history["performance_index"].mean()
best_index_row = history.loc[history["performance_index"].idxmax()]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Courses", len(history))
col2.metric("Distance totale", f"{total_distance:.1f} km")
col3.metric("Allure moyenne", format_pace(avg_pace))
col4.metric("Indice moyen", f"{avg_index:.1f}")

col1, col2 = st.columns([1, 3])
with col1:
    st.metric("Meilleure performance relative", f"{best_index_row.performance_index:.1f}")
with col2:
    st.write(
        f"{best_index_row.race} ({int(best_index_row.year)}) - "
        f"{best_index_row.distance:.2f} km - {format_time(best_index_row.time_sec)}"
    )

tab_profile, tab_simulation, tab_details = st.tabs(["Profil", "Simulation", "Détail"])

x_date = alt.X(
    "date:T",
    title="Date",
    axis=alt.Axis(format="%Y-%m", tickCount=7, labelAngle=-35, labelOverlap=True),
)
performance_domain = make_numeric_domain(history, ["performance_index"])

with tab_profile:
    left, right = st.columns([2, 1])

    profile_history = history.dropna(subset=["predicted_performance_index"]).copy()
    profile_domain = make_numeric_domain(
        history,
        ["performance_index", "predicted_performance_index"],
    )

    index_chart = (
        alt.Chart(history)
        .mark_line(point=True, color="#2563eb")
        .encode(
            x=x_date,
            y=alt.Y(
                "performance_index:Q",
                title="Indice de performance",
                scale=alt.Scale(domain=profile_domain, zero=False),
            ),
            tooltip=[
                alt.Tooltip("race:N", title="Course"),
                alt.Tooltip("distance:Q", title="Distance", format=".2f"),
                alt.Tooltip("position:Q", title="Position"),
                alt.Tooltip("time:N", title="Temps"),
                alt.Tooltip("pace:N", title="Allure"),
                alt.Tooltip("performance_index:Q", title="Indice", format=".1f"),
            ],
        )
    )

    if profile_history.empty:
        left.altair_chart(index_chart.properties(height=340), use_container_width=True)
    else:
        expected_line = (
            alt.Chart(profile_history)
            .mark_line(color="#c2410c")
            .encode(
                x=x_date,
                y=alt.Y(
                    "predicted_performance_index:Q",
                    title="Indice de performance",
                    scale=alt.Scale(domain=profile_domain, zero=False),
                ),
                tooltip=[
                    alt.Tooltip("race:N", title="Course"),
                    alt.Tooltip("predicted_performance_index:Q", title="Indice attendu", format=".1f"),
                    alt.Tooltip("predicted_time:N", title="Temps attendu"),
                ],
            )
        )
        expected_points = (
            alt.Chart(profile_history)
            .mark_circle(size=65, color="#c2410c")
            .encode(
                x=x_date,
                y=alt.Y(
                    "predicted_performance_index:Q",
                    title="Indice de performance",
                    scale=alt.Scale(domain=profile_domain, zero=False),
                ),
                tooltip=[
                    alt.Tooltip("race:N", title="Course"),
                    alt.Tooltip("predicted_performance_index:Q", title="Indice attendu", format=".1f"),
                    alt.Tooltip("predicted_time:N", title="Temps attendu"),
                ],
            )
        )
        left.altair_chart(
            (expected_line + expected_points + index_chart).properties(height=340),
            use_container_width=True,
        )

    distance_index = (
        alt.Chart(history)
        .mark_circle(size=75, opacity=0.75, color="#0f766e")
        .encode(
            x=alt.X("distance:Q", title="Distance (km)"),
            y=alt.Y(
                "performance_index:Q",
                title="Indice",
                scale=alt.Scale(domain=performance_domain, zero=False),
            ),
            tooltip=[
                alt.Tooltip("race:N", title="Course"),
                alt.Tooltip("year:Q", title="Année"),
                alt.Tooltip("distance:Q", title="Distance", format=".2f"),
                alt.Tooltip("performance_index:Q", title="Indice", format=".1f"),
            ],
        )
    )
    right.altair_chart(distance_index.properties(height=340), use_container_width=True)

with tab_simulation:
    st.subheader("Simulation rétrospective sur une course non courue")
    st.caption(
        "La course sélectionnée doit déjà exister dans les résultats : l'estimation utilise "
        "la moyenne et l'écart-type des coureurs qui l'ont terminée."
    )

    candidate_races = run_query(
        """
        SELECT race_id, name, year, distance
        FROM dim_race
        WHERE race_id NOT IN (
            SELECT race_id
            FROM fact_results
            WHERE runner_id = :runner_id
        )
        ORDER BY year DESC, name
        """,
        {"runner_id": int(runner_id)},
    )

    if candidate_races.empty:
        st.info("Ce coureur a déjà un résultat sur toutes les courses disponibles.")
    else:
        race_labels = {
            row.race_id: f"{row.name} - {int(row.year)} ({row.distance:.2f} km)"
            for row in candidate_races.itertuples()
        }

        race_id = st.selectbox(
            "Course à simuler",
            candidate_races["race_id"],
            format_func=lambda value: race_labels[value],
        )

        if not has_model_artifact:
            st.info("Lance d'abord le module de régression pour entraîner un modèle.")
        elif st.button("Estimer le temps"):
            prediction = predict_runner_race(
                engine,
                runner_id=int(runner_id),
                race_id=int(race_id),
                min_history=3,
            )

            if not prediction["ok"]:
                st.warning(prediction["message"])
            else:
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Temps estimé", format_time(prediction["predicted_time_sec"]))
                col2.metric("Allure estimée", format_pace(prediction["predicted_pace_sec_km"]))
                col3.metric("Vitesse estimée", f"{prediction['predicted_speed_kmh']:.2f} km/h")
                col4.metric("Indice estimé", f"{prediction['predicted_performance_index']:.1f}")

                st.write(
                    f"Z-score estimé : {prediction['predicted_z']:.2f}. "
                    f"Historique utilisé : au moins trois courses précédentes."
                )

with tab_details:
    st.caption("Cliquez sur le nom d'une course pour ouvrir sa page.")

    header = st.columns([1.0, 3.0, 1.0, 0.9, 1.0, 1.0, 0.9, 0.9, 1.0, 1.0])
    header[0].caption("Date")
    header[1].caption("Course")
    header[2].caption("Distance")
    header[3].caption("Pos.")
    header[4].caption("Catégorie")
    header[5].caption("Temps")
    header[6].caption("Allure")
    header[7].caption("Vit.")
    header[8].caption("Indice")
    header[9].caption("Attendu")

    with st.container(height=620, border=True):
        for row in history.sort_values("date", ascending=False).itertuples():
            cols = st.columns([1.0, 3.0, 1.0, 0.9, 1.0, 1.0, 0.9, 0.9, 1.0, 1.0])
            cols[0].write(row.date.strftime("%Y-%m-%d"))
            if cols[1].button(row.race, key=f"runner_race_{row.result_id}", use_container_width=True):
                open_race(row.race_id)
            cols[2].write(f"{row.distance:.2f} km")
            cols[3].write(int(row.position) if pd.notna(row.position) else "")
            cols[4].write(row.category_clean or "")
            cols[5].write(row.time)
            cols[6].write(row.pace)
            cols[7].write(f"{row.speed_kmh:.2f}")
            cols[8].write(f"{row.performance_index:.1f}" if pd.notna(row.performance_index) else "")
            cols[9].write(row.predicted_time)
