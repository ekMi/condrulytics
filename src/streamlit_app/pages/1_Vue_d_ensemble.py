import altair as alt
import pandas as pd
import streamlit as st

from db import run_query


RACE_PAGE = "pages/2_Courses.py"


def get_selected_value(chart_event, selection_name, field_name):
    selection = getattr(chart_event, "selection", None)
    if selection is None:
        return None

    selected = None
    try:
        selected = selection[selection_name]
    except (KeyError, TypeError):
        selected = getattr(selection, selection_name, None)

    if not selected:
        return None

    if isinstance(selected, list):
        if not selected:
            return None
        selected = selected[0]

    if isinstance(selected, dict):
        return selected.get(field_name)

    return selected


def open_race(race_id):
    st.session_state["selected_race_id"] = int(race_id)
    st.switch_page(RACE_PAGE)


def format_pace(seconds_per_km):
    if pd.isna(seconds_per_km):
        return ""

    seconds = int(round(seconds_per_km))
    return f"{seconds // 60:d}:{seconds % 60:02d}/km"


st.title("Vue d'ensemble")

summary = run_query(
    """
    SELECT
        COUNT(DISTINCT f.runner_id) AS runners,
        COUNT(DISTINCT f.race_id) AS races,
        COUNT(*) AS results,
        MIN(ra.year) AS first_year,
        MAX(ra.year) AS last_year,
        SUM(ra.distance) AS total_distance
    FROM fact_results f
    JOIN dim_race ra ON f.race_id = ra.race_id
    """
)

row = summary.iloc[0]
col1, col2, col3, col4 = st.columns(4)
col1.metric("Coureurs", f"{int(row.runners):,}".replace(",", " "))
col2.metric("Courses", f"{int(row.races):,}".replace(",", " "))
col3.metric("Résultats", f"{int(row.results):,}".replace(",", " "))
col4.metric("Période", f"{int(row.first_year)} - {int(row.last_year)}")

st.subheader("Dynamique du challenge")
st.caption("Cliquez sur une année pour voir les courses correspondantes")

yearly = run_query(
    """
    SELECT
        ra.year,
        COUNT(DISTINCT ra.race_id) AS races,
        COUNT(*) AS results,
        COUNT(DISTINCT f.runner_id) AS runners,
        AVG(f.speed_kmh) AS avg_speed,
        AVG(f.time_sec / NULLIF(ra.distance, 0)) AS avg_pace_sec_km
    FROM fact_results f
    JOIN dim_race ra ON f.race_id = ra.race_id
    GROUP BY ra.year
    ORDER BY ra.year
    """
)
default_year = int(yearly["year"].max())
active_year = int(st.session_state.get("overview_selected_year", default_year))
yearly["avg_pace"] = yearly["avg_pace_sec_km"].apply(format_pace)
yearly["year_status"] = yearly["year"].apply(
    lambda year: "Année sélectionnée" if int(year) == active_year else "Autres années"
)

left, right = st.columns([2, 1])

year_selection = alt.selection_point(name="year_selection", fields=["year"], empty=False)
participation_chart = (
    alt.Chart(yearly)
    .mark_bar()
    .add_params(year_selection)
    .encode(
        x=alt.X("year:O", title="Année"),
        y=alt.Y("results:Q", title="Résultats"),
        color=alt.Color(
            "year_status:N",
            legend=None,
            scale=alt.Scale(
                domain=["Année sélectionnée", "Autres années"],
                range=["#f97316", "#cbd5e1"],
            ),
        ),
        tooltip=[
            alt.Tooltip("year:O", title="Année"),
            alt.Tooltip("races:Q", title="Courses"),
            alt.Tooltip("results:Q", title="Résultats"),
            alt.Tooltip("runners:Q", title="Coureurs"),
            alt.Tooltip("avg_speed:Q", title="Vitesse moyenne", format=".2f"),
            alt.Tooltip("avg_pace:N", title="Allure moyenne"),
        ],
    )
)
year_event = left.altair_chart(
    participation_chart.properties(height=320),
    key="overview_year_chart",
    on_select="rerun",
    selection_mode="year_selection",
    use_container_width=True,
)

clicked_year = get_selected_value(year_event, "year_selection", "year")
if clicked_year is not None and int(clicked_year) != active_year:
    st.session_state["overview_selected_year"] = int(clicked_year)
    st.rerun()

selected_year = active_year

year_races = run_query(
    """
    SELECT
        ra.race_id,
        ra.name,
        ra.date,
        ra.distance,
        COUNT(*) AS participants,
        AVG(f.speed_kmh) AS avg_speed,
        AVG(f.time_sec / NULLIF(ra.distance, 0)) AS avg_pace_sec_km
    FROM fact_results f
    JOIN dim_race ra ON f.race_id = ra.race_id
    WHERE ra.year = :year
    GROUP BY ra.race_id, ra.name, ra.date, ra.distance
    ORDER BY ra.date, ra.name
    """,
    {"year": selected_year},
)
year_races["avg_pace"] = year_races["avg_pace_sec_km"].apply(format_pace)

right.markdown(f"**Courses en {selected_year}**")
table_box = right.container(height=320, border=True)
header = table_box.columns([3.0, 0.9, 1.1, 1.2])
header[0].caption("Course")
header[1].caption("Km")
header[2].caption("Part.")
header[3].caption("Allure")

for row in year_races.itertuples():
    cols = table_box.columns([3.0, 0.9, 1.1, 1.2])
    if cols[0].button(row.name, key=f"overview_year_race_{row.race_id}", use_container_width=True):
        open_race(row.race_id)
    cols[1].write(f"{row.distance:.1f}")
    cols[2].write(int(row.participants))
    cols[3].write(row.avg_pace)

st.subheader("Courses et distances")

race_profile = run_query(
    """
    SELECT
        ra.race_id,
        ra.name,
        ra.year,
        ra.distance,
        COUNT(*) AS participants,
        AVG(f.speed_kmh) AS avg_speed,
        AVG(f.time_sec / NULLIF(ra.distance, 0)) AS avg_pace_sec_km,
        STDDEV_SAMP(f.speed_kmh) AS speed_std
    FROM fact_results f
    JOIN dim_race ra ON f.race_id = ra.race_id
    GROUP BY ra.race_id, ra.name, ra.year, ra.distance
    """
)
race_profile["avg_pace"] = race_profile["avg_pace_sec_km"].apply(format_pace)
race_profile["year_status"] = race_profile["year"].apply(
    lambda year: "Année sélectionnée" if int(year) == selected_year else "Autres années"
)

race_selection = alt.selection_point(name="race_selection", fields=["race_id"], empty=False)
distance_chart = (
    alt.Chart(race_profile)
    .mark_circle(size=70, opacity=0.72)
    .add_params(race_selection)
    .encode(
        x=alt.X("distance:Q", title="Distance (km)"),
        y=alt.Y("participants:Q", title="Participants"),
        color=alt.condition(
            race_selection,
            alt.value("#0f766e"),
            alt.Color(
                "year_status:N",
                legend=None,
                scale=alt.Scale(
                    domain=["Année sélectionnée", "Autres années"],
                    range=["#f97316", "#94a3b8"],
                ),
            ),
        ),
        tooltip=[
            alt.Tooltip("name:N", title="Course"),
            alt.Tooltip("year:Q", title="Année"),
            alt.Tooltip("distance:Q", title="Distance", format=".2f"),
            alt.Tooltip("participants:Q", title="Participants"),
            alt.Tooltip("avg_speed:Q", title="Vitesse moyenne", format=".2f"),
            alt.Tooltip("avg_pace:N", title="Allure moyenne"),
        ],
    )
)

race_event = st.altair_chart(
    distance_chart.properties(height=320),
    key="overview_race_chart",
    on_select="rerun",
    selection_mode="race_selection",
    use_container_width=True,
)

selected_race_id = get_selected_value(race_event, "race_selection", "race_id")
if selected_race_id is not None:
    selected_race_id = int(selected_race_id)
    if st.session_state.get("last_overview_race_click") != selected_race_id:
        st.session_state["last_overview_race_click"] = selected_race_id
        open_race(selected_race_id)
