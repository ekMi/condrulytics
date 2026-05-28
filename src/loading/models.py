import logging
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    BigInteger,
)
from sqlalchemy.orm import declarative_base, relationship

from .db_config import engine

logger = logging.getLogger(__name__)

Base = declarative_base()

class DimRunner(Base):
    __tablename__ = "dim_runner"

    runner_id = Column(BigInteger, primary_key=True, autoincrement=True)

    name_origin = Column(String)
    name_clean = Column(String, index=True)
    sex = Column(String)

    results = relationship("FactResult", back_populates="runner")
    analyses = relationship("FactRunnerRaceAnalysis", back_populates="runner")


class DimRace(Base):
    __tablename__ = "dim_race"

    race_id = Column(BigInteger, primary_key=True, autoincrement=True)

    racekey = Column(String, unique=True, index=True)

    name = Column(String)
    distance = Column(Float)

    date = Column(DateTime)
    year = Column(Integer)

    results = relationship("FactResult", back_populates="race")
    analyses = relationship("FactRunnerRaceAnalysis", back_populates="race")

class FactResult(Base):
    __tablename__ = "fact_results"

    result_id = Column(BigInteger, primary_key=True, autoincrement=True)

    runner_id = Column(BigInteger, ForeignKey("dim_runner.runner_id"))
    race_id = Column(BigInteger, ForeignKey("dim_race.race_id"))

    position = Column(Integer)
    position_category = Column(Integer)

    time_sec = Column(Integer)
    speed_kmh = Column(Float)

    category_seen = Column(String)
    category_clean = Column(String)

    source_file = Column(String)

    runner = relationship("DimRunner", back_populates="results")
    race = relationship("DimRace", back_populates="results")


class FactRunnerRaceAnalysis(Base):
    __tablename__ = "fact_runner_race_analysis"

    analysis_id = Column(BigInteger, primary_key=True, autoincrement=True)

    source_result_id = Column(BigInteger, unique=True, index=True)
    runner_id = Column(BigInteger, ForeignKey("dim_runner.runner_id"), index=True)
    race_id = Column(BigInteger, ForeignKey("dim_race.race_id"), index=True)

    actual_position = Column(Integer)
    actual_position_category = Column(Integer)
    actual_time_sec = Column(Float)
    actual_speed_kmh = Column(Float)

    race_month = Column(Integer)
    race_dayofyear = Column(Integer)
    race_participants = Column(Integer)
    race_mean_speed = Column(Float)
    race_std_speed = Column(Float)
    race_median_speed = Column(Float)

    prior_race_count = Column(Integer)
    prior_avg_speed = Column(Float)
    prior_std_speed = Column(Float)
    prior_best_speed = Column(Float)
    prior_avg_z = Column(Float)
    prior_std_z = Column(Float)
    prior_best_z = Column(Float)
    recent_speed_roll3 = Column(Float)
    recent_z_roll3 = Column(Float)
    days_since_last_race = Column(Float)
    runner_history_years = Column(Float)

    speed_z_race = Column(Float)
    performance_index = Column(Float)
    target_z = Column(Float)

    predicted_z = Column(Float)
    predicted_performance_index = Column(Float)
    predicted_speed_kmh = Column(Float)
    predicted_time_sec = Column(Float)
    abs_error_time_sec = Column(Float)
    split = Column(String)

    runner = relationship("DimRunner", back_populates="analyses")
    race = relationship("DimRace", back_populates="analyses")


def create_tables():
    logger.info("Création des tables PostgreSQL...")

    Base.metadata.create_all(engine)

    logger.info("Tables créées avec succès.")
