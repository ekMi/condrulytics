import streamlit as st
from db import run_query

st.title("Runners analysis")

# select runner
runners = run_query("SELECT DISTINCT name_clean FROM dim_runner ORDER BY name_clean")

runner = st.selectbox("Choose runner", runners["name_clean"])

query = f"""
SELECT
    ra.name,
    ra.year,
    f.time_sec,
    f.speed_kmh,
    f.position
FROM fact_results f
JOIN dim_runner r ON f.runner_id = r.runner_id
JOIN dim_race ra ON f.race_id = ra.race_id
WHERE r.name_clean = '{runner}'
ORDER BY ra.date;
"""

df = run_query(query)

st.line_chart(df.set_index("year")["time_sec"])
st.dataframe(df)