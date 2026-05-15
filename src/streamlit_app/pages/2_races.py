import streamlit as st
from db import run_query

st.title("Races analysis")

race = st.selectbox(
    "Select race",
    run_query("SELECT DISTINCT name FROM dim_race")["name"]
)

query = f"""
SELECT
    r.name_clean,
    f.time_sec,
    f.position,
    f.speed_kmh
FROM fact_results f
JOIN dim_runner r ON f.runner_id = r.runner_id
JOIN dim_race ra ON f.race_id = ra.race_id
WHERE ra.name = '{race}'
ORDER BY f.position;
"""

df = run_query(query)

st.bar_chart(df.head(30).set_index("name_clean")["time_sec"])
st.dataframe(df)