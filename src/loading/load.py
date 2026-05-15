import logging
import pandas as pd

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db_config import engine
from .models import DimRunner, DimRace, FactResult

logger = logging.getLogger(__name__)

def load_parquet_to_postgres(parquet_path: str, batch_size: int = 5000):
    logger.info("Chargement du fichier parquet : %s", parquet_path)

    df = pd.read_parquet(parquet_path)

    logger.info("Dataset chargé : %s lignes", len(df))

    session = Session(engine)

    try:
        runner_cache = {}
        race_cache = {}

        logger.info("Indexation des dimensions existantes...")

        _load_runner_cache(session, runner_cache)
        _load_race_cache(session, race_cache)

        logger.info("Caches prêts : %s runners / %s races",
                    len(runner_cache), len(race_cache))

        _process_dataframe(df, session, runner_cache, race_cache, batch_size)

        session.commit()
        logger.info("ETL terminé avec succès")

    except Exception as e:
        session.rollback()
        logger.exception("Erreur ETL : %s", e)
        raise

    finally:
        session.close()

def _load_runner_cache(session, cache: dict):
    runners = session.execute(select(DimRunner)).scalars().all()

    for r in runners:
        cache[r.name_clean] = r.runner_id


def _load_race_cache(session, cache: dict):
    races = session.execute(select(DimRace)).scalars().all()

    for r in races:
        cache[r.racekey] = r.race_id

def _get_or_create_runner(session, row, runner_cache):
    name_clean = row["Nom_clean"]

    if name_clean in runner_cache:
        return runner_cache[name_clean]

    runner = DimRunner(
        name_origin=row["Nom"],
        name_clean=name_clean,
        sex=row["Sexe"]
    )

    session.add(runner)
    session.flush()

    runner_cache[name_clean] = runner.runner_id

    return runner.runner_id

def _get_or_create_race(session, row, race_cache):
    racekey = row["racekey"]

    if racekey in race_cache:
        return race_cache[racekey]

    race = DimRace(
        racekey=racekey,
        name=row["NomCourse"],
        distance=row["Distance"],
        date=row["Date"],
        year=row["year"]
    )

    session.add(race)
    session.flush()

    race_cache[racekey] = race.race_id

    return race.race_id

def _process_dataframe(df, session, runner_cache, race_cache, batch_size):
    logger.info("Insertion fact_results...")

    batch = []

    for i, row in df.iterrows():

        runner_id = _get_or_create_runner(session, row, runner_cache)
        race_id = _get_or_create_race(session, row, race_cache)

        fact = FactResult(
            runner_id=runner_id,
            race_id=race_id,

            position=row["Position"],
            position_category=row["Position Catégorie"],

            time_sec=row["temps_sec"],
            speed_kmh=row["speed_kmh"],

            category_seen=row["Categorie"],
            category_clean=row["categorie_cleaned"],

            source_file=row["source_file"]
        )

        batch.append(fact)

        if len(batch) >= batch_size:
            session.bulk_save_objects(batch)
            session.flush()
            batch.clear()

            logger.info("Batch inséré")

    if batch:
        session.bulk_save_objects(batch)
        session.flush()

    logger.info("Fact table insérée")


if __name__ == "__main__":
    load_parquet_to_postgres("data.parquet")