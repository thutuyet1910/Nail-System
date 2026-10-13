import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from . import nailsystem_runtime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nail_system.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

if DATABASE_URL.startswith("sqlite"):
    # busy timeout, foreign keys ON, WAL and full durability on every connection (nailsystem_runtime.py)
    nailsystem_runtime.install_sqlite_pragmas(engine)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()