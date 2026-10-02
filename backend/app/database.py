import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


# Allow local and test databases to be selected without changing application code.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://ticket_assignment:ticket_assignment@localhost:5433/ticket_assignment",
)


class Base(DeclarativeBase):
    # Shared declarative metadata is used by models and Alembic migrations.
    pass


# The engine owns the pooled connections; each request gets its own short-lived Session.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    # Yield one request-scoped session and close it after the API handler finishes.
    with SessionLocal() as session:
        yield session
