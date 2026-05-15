from sqlalchemy import create_engine
import pandas as pd

DB_URL = "postgresql://admin:admin@localhost:5432/condrulytics"

engine = create_engine(DB_URL)


def run_query(query: str) -> pd.DataFrame:
    return pd.read_sql(query, engine)