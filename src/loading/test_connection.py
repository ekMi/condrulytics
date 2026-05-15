import pandas as pd

from src.loading.db_config import engine

df = pd.read_parquet(
    "data/cleaned/results.parquet"
)

# Envoyer vers PostgreSQL
df.to_sql(
    name="matches",
    con=engine,
    if_exists="replace",
    index=False
)

print("Data loaded successfully")