from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    url = make_url(get_settings().database_url)
    connect_args = {"connect_timeout": 5} if url.drivername == "postgresql+psycopg" else {}
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args)


def get_db() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
