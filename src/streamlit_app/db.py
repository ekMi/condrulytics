import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, inspect, text

DB_URL = "postgresql://admin:admin@localhost:5432/condrulytics"

engine = create_engine(DB_URL)


@st.cache_data(ttl=120, show_spinner=False)
def run_query(query: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params=params)


def table_exists(table_name: str) -> bool:
    return inspect(engine).has_table(table_name)
