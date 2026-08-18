"""
Database schema.

Design choice: store RAW per-game features (not just the final computed
index) so both FPI and FII can be recomputed / reweighted later without
re-fetching from the NHL API. Re-running FIIConfig with different weights
is then a cheap DB read + recompute, not a re-scrape.
"""

import os
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint, JSON, Text
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/nhl_fatigue.db")

# sqlite won't create the parent directory itself -- ensure it exists before
# the engine tries to open the file (relevant for the default local/CI path;
# a no-op when DATABASE_URL points at a real Postgres server instead).
if DATABASE_URL.startswith("sqlite:///"):
    _db_path = DATABASE_URL.replace("sqlite:///", "", 1)
    _db_dir = os.path.dirname(_db_path)
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)

# Railway/Heroku-style URLs sometimes come as postgres:// -- SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)  # NHL player id
    name = Column(String, nullable=False)
    team_abbrev = Column(String, nullable=True)  # most-recently-seen team


class GameFPI(Base):
    """Raw per-game fatigue-pressure features for one player. FPI's decayed
    score is computed at read time from the ordered history of these rows."""
    __tablename__ = "game_fpi"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True, nullable=False)
    game_id = Column(Integer, index=True, nullable=False)
    date = Column(String, nullable=False)  # 'YYYY-MM-DD'
    venue_team = Column(String, nullable=False)
    toi_minutes = Column(Float, nullable=False)

    __table_args__ = (UniqueConstraint("player_id", "game_id", name="uq_fpi_player_game"),)


class GameFII(Base):
    """Aggregate FII result for one player in one game."""
    __tablename__ = "game_fii"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"), index=True, nullable=False)
    game_id = Column(Integer, index=True, nullable=False)
    date = Column(String, nullable=False)
    fii_per_60 = Column(Float, nullable=False)
    total_weighted_toll = Column(Float, nullable=False)
    total_shared_toi_min = Column(Float, nullable=False)

    matchups = relationship("FIIMatchup", back_populates="game_fii", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("player_id", "game_id", name="uq_fii_player_game"),)


class FIIMatchup(Base):
    """Per-opponent toll breakdown, for drill-down on a player's game."""
    __tablename__ = "fii_matchups"
    id = Column(Integer, primary_key=True)
    game_fii_id = Column(Integer, ForeignKey("game_fii.id"), nullable=False)
    opponent_player_id = Column(Integer, nullable=False)
    raw_toll = Column(Float, nullable=False)
    role_weight = Column(Float, nullable=False)
    weighted_toll = Column(Float, nullable=False)
    components_json = Column(JSON, nullable=False)

    game_fii = relationship("GameFII", back_populates="matchups")


class IngestLog(Base):
    """Tracks which games have been processed, for idempotent daily runs and
    for surfacing pipeline health on the dashboard (this is what makes the
    system trustworthy to leave alone -- you can see if it's silently failing)."""
    __tablename__ = "ingest_log"
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, unique=True, nullable=False)
    status = Column(String, nullable=False)  # 'ok' | 'error' | 'skipped'
    error_message = Column(Text, nullable=True)
    ingested_at = Column(DateTime, nullable=False)


def init_db():
    Base.metadata.create_all(engine)


def get_session():
    return SessionLocal()
