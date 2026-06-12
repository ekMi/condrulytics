import altair as alt
import pandas as pd
import streamlit as st

from db import run_query, table_exists


RUNNER_PAGE = "pages/3_Coureurs.py"


def get_query_int(name):
    value = st.query_params.get(name)
    if isinstance(value, list):
        value = value[0] if value else None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def open_runner(runner_id):
    st.session_state["selected_runner_id"] = int(runner_id)
    st.switch_page(RUNNER_PAGE)


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


def format_signed_time(seconds):
    if pd.isna(seconds):
        return ""

    sign = "+" if seconds > 0 else "-"
    seconds = abs(int(round(seconds)))
    minutes = seconds // 60
    secs = seconds % 60
    return f"{sign}{minutes:d}:{secs:02d}"


st.title("Courses")
st.caption(
    "Indice de performance : 100 = proche de la moyenne des participants de la course, "
    "> 100 = plus rapide que la moyenne, < 100 = moins rapide. Exemple : 103 indique "
    "une performance légèrement au-dessus de la moyenne, pas une note sur 100."
)

races = run_query(
    """
    SELECT race_id, name, year, distance, date
    FROM dim_race
    ORDER BY year DESC, name, distance
    """
)

if races.empty:
    st.warning("Aucune course disponible.")
    st.stop()

query_race_id = st.session_state.pop("selected_race_id", None)
if query_race_id is None:
    query_race_id = get_query_int("race_id")
years = sorted(races["year"].dropna().astype(int).unique(), reverse=True)
default_years = years[:3]

if query_race_id is not None and query_race_id in set(races["race_id"].astype(int)):
    query_year = int(races.loc[races["race_id"] == query_race_id, "year"].iloc[0])
    if query_year not in default_years:
        default_years = [query_year] + default_years

selected_years = st.sidebar.multiselect("Années", years, default=default_years)

filtered_races = races[races["year"].isin(selected_years)] if selected_years else races
labels = {
    row.race_id: f"{row.name} - {int(row.year)} ({row.distance:.2f} km)"
    for row in filtered_races.itertuples()
}

selectbox_index = 0
if query_race_id is not None and query_race_id in set(filtered_races["race_id"].astype(int)):
    selectbox_index = filtered_races["race_id"].astype(int).tolist().index(query_race_id)

race_id = st.selectbox(
    "Course",
    filtered_races["race_id"],
    format_func=lambda value: labels[value],
    index=selectbox_index,
)
st.query_params["race_id"] = str(int(race_id))

race_info = races[races["race_id"] == race_id].iloc[0]

results = run_query(
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
        f.result_id,
        f.runner_id,
        r.name_clean,
        f.position,
        f.position_category,
        f.time_sec,
        f.speed_kmh,
        f.category_clean,
        100 + 10 * ((f.speed_kmh - rs.race_mean_speed) / NULLIF(rs.race_std_speed, 0)) AS performance_index
    FROM fact_results f
    JOIN dim_runner r ON f.runner_id = r.runner_id
    JOIN race_stats rs ON f.race_id = rs.race_id
    WHERE f.race_id = :race_id
    ORDER BY f.position
    """,
    {"race_id": int(race_id)},
)

results["time"] = results["time_sec"].apply(format_time)
results["pace_sec_km"] = results["time_sec"] / float(race_info.distance)
results["pace"] = results["pace_sec_km"].apply(format_pace)
results["time_min"] = results["time_sec"] / 60
results["category_label"] = results["category_clean"].fillna("Non renseignée")

has_predictions = table_exists("fact_runner_race_analysis")
if has_predictions:
    predictions = run_query(
        """
        SELECT
            a.runner_id,
            a.predicted_time_sec,
            a.abs_error_time_sec,
            a.speed_z_race AS actual_z,
            a.predicted_z
        FROM fact_runner_race_analysis a
        WHERE a.race_id = :race_id
          AND a.predicted_time_sec IS NOT NULL
        """,
        {"race_id": int(race_id)},
    )
    results = results.merge(predictions, on="runner_id", how="left")
else:
    results["predicted_time_sec"] = pd.NA
    results["abs_error_time_sec"] = pd.NA
    results["actual_z"] = pd.NA
    results["predicted_z"] = pd.NA

results["predicted_time"] = results["predicted_time_sec"].apply(format_time)
results["time_gap_sec"] = results["time_sec"] - results["predicted_time_sec"]
results["time_gap"] = results["time_gap_sec"].apply(format_signed_time)

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Participants", len(results))
col2.metric("Distance", f"{race_info.distance:.2f} km")
col3.metric("Temps moyen", format_time(results["time_sec"].mean()))
col4.metric("Allure moyenne", format_pace(results["pace_sec_km"].mean()))
col5.metric("Vitesse moyenne", f"{results['speed_kmh'].mean():.2f} km/h")

tab_results, tab_summary = st.tabs(["Classement", "Analyse"])

with tab_results:
    st.caption("Cliquez sur le nom d'un coureur pour ouvrir sa fiche.")
    st.caption(
        "La colonne Indice compare chaque coureur au niveau observé sur cette même course."
    )

    categories = ["Toutes"] + sorted(
        results["category_label"].astype(str).unique().tolist()
    )
    selected_category = st.selectbox("Catégorie", categories)

    filtered_results = results
    if selected_category != "Toutes":
        filtered_results = results[
            results["category_label"].astype(str) == selected_category
        ]

    if has_predictions and filtered_results["predicted_time_sec"].notna().any():
        st.info(
            "L'écart est calculé comme temps réalisé moins temps attendu. "
            "Une valeur négative signifie que le coureur a été plus rapide que prévu."
        )
    elif has_predictions:
        st.info("Aucun temps attendu disponible pour cette course.")
    else:
        st.info("Les temps attendus ne sont pas disponibles dans la base actuelle.")

    header = st.columns([0.55, 0.65, 2.5, 1.0, 1.0, 1.0, 0.8, 0.9, 0.8, 0.8])
    header[0].caption("Gén.")
    header[1].caption("Cat.")
    header[2].caption("Coureur")
    header[3].caption("Catégorie")
    header[4].caption("Temps")
    header[5].caption("Attendu")
    header[6].caption("Écart")
    header[7].caption("Allure")
    header[8].caption("Vit.")
    header[9].caption("Indice")

    with st.container(height=620, border=True):
        for row in filtered_results.itertuples():
            cols = st.columns([0.55, 0.65, 2.5, 1.0, 1.0, 1.0, 0.8, 0.9, 0.8, 0.8])
            cols[0].write(int(row.position) if pd.notna(row.position) else "")
            cols[1].write(int(row.position_category) if pd.notna(row.position_category) else "")
            if cols[2].button(row.name_clean, key=f"race_runner_{row.result_id}", use_container_width=True):
                open_runner(row.runner_id)
            cols[3].write(row.category_label)
            cols[4].write(row.time)
            cols[5].write(row.predicted_time)
            cols[6].write(row.time_gap)
            cols[7].write(row.pace)
            cols[8].write(f"{row.speed_kmh:.2f}")
            cols[9].write(f"{row.performance_index:.1f}" if pd.notna(row.performance_index) else "")

with tab_summary:
    st.caption(
        "Les analyses ci-dessous décrivent la course sélectionnée ; l'indice sert à "
        "situer une performance par rapport aux participants de cette course."
    )

    category_counts = (
        results.groupby("category_label", dropna=False)
        .agg(
            participants=("result_id", "count"),
            mean_pace_sec_km=("pace_sec_km", "mean"),
            mean_speed_kmh=("speed_kmh", "mean"),
        )
        .reset_index()
        .sort_values("participants", ascending=False)
        .head(12)
    )
    category_counts["allure_moyenne"] = category_counts["mean_pace_sec_km"].apply(format_pace)
    category_chart = (
        alt.Chart(category_counts)
        .mark_bar(color="#0f766e")
        .encode(
            x=alt.X("participants:Q", title="Participants"),
            y=alt.Y("category_label:N", sort="-x", title="Catégorie"),
            tooltip=[
                alt.Tooltip("category_label:N", title="Catégorie"),
                alt.Tooltip("participants:Q", title="Participants"),
                alt.Tooltip("allure_moyenne:N", title="Allure moyenne"),
                alt.Tooltip("mean_speed_kmh:Q", title="Vitesse moyenne", format=".2f"),
            ],
        )
    )
    st.altair_chart(category_chart.properties(height=320), use_container_width=True)

    st.subheader("Temps par catégorie")

    category_summary = (
        results.groupby("category_label", dropna=False)
        .agg(
            participants=("result_id", "count"),
            best_time_sec=("time_sec", "min"),
            mean_time_sec=("time_sec", "mean"),
            median_time_sec=("time_sec", "median"),
            mean_pace_sec_km=("pace_sec_km", "mean"),
            mean_speed_kmh=("speed_kmh", "mean"),
        )
        .reset_index()
        .sort_values(["participants", "category_label"], ascending=[False, True])
    )
    category_summary["meilleur temps"] = category_summary["best_time_sec"].apply(format_time)
    category_summary["temps moyen"] = category_summary["mean_time_sec"].apply(format_time)
    category_summary["temps médian"] = category_summary["median_time_sec"].apply(format_time)
    category_summary["allure moyenne"] = category_summary["mean_pace_sec_km"].apply(format_pace)
    category_summary["vitesse moyenne"] = category_summary["mean_speed_kmh"].apply(
        lambda value: f"{value:.2f} km/h" if pd.notna(value) else ""
    )

    st.dataframe(
        category_summary[
            [
                "category_label",
                "participants",
                "meilleur temps",
                "temps moyen",
                "temps médian",
                "allure moyenne",
                "vitesse moyenne",
            ]
        ].rename(columns={"category_label": "catégorie"}),
        hide_index=True,
        use_container_width=True,
    )
