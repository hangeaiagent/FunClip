"""Token usage database models (SQLite + SQLAlchemy)."""

import os
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.getenv("TOKEN_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "token_usage.db"))
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class TokenUsage(Base):
    __tablename__ = "apbase_token_usage"

    id = Column(String, primary_key=True)
    agent_id = Column(String, nullable=False, index=True)
    application_id = Column(String, nullable=False, default="")
    user_id = Column(String, nullable=False, default="")
    tokens_used = Column(Integer, nullable=False)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=False)
    model_name = Column(String, nullable=True)
    request_id = Column(String, nullable=True)
    metadata_json = Column(String, nullable=True)  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Create tables on import
Base.metadata.create_all(engine)
