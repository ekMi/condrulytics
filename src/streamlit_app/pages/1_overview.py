import streamlit as st
from db import run_query
from queries import TOP_RUNNERS, TOP_RACES

st.title("Overview")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Top runners")
    df = run_query(TOP_RUNNERS)
    st.dataframe(df)

with col2:
    st.subheader("Top races")
    df = run_query(TOP_RACES)
    st.dataframe(df)