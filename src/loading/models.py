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


class DimRace(Base):
    __tablename__ = "dim_race"

    race_id = Column(BigInteger, primary_key=True, autoincrement=True)

    racekey = Column(String, unique=True, index=True)

    name = Column(String)
    distance = Column(Float)

    date = Column(DateTime)
    year = Column(Integer)

    results = relationship("FactResult", back_populates="race")

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


def create_tables():
    logger.info("Création des tables PostgreSQL...")

    Base.metadata.create_all(engine)

    logger.info("Tables créées avec succès.")