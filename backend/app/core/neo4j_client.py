from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from neo4j import Driver, GraphDatabase, Session

from .config import Settings, get_settings


def _create_driver(settings: Settings) -> Driver:
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


@lru_cache
def get_neo4j_driver() -> Driver:
    return _create_driver(get_settings())


def verify_neo4j_connectivity() -> None:
    get_neo4j_driver().verify_connectivity()


@contextmanager
def neo4j_session(default_access_mode: str = "READ") -> Iterator[Session]:
    settings = get_settings()
    session_kwargs = {"default_access_mode": default_access_mode}
    if settings.neo4j_database:
        session_kwargs["database"] = settings.neo4j_database

    with get_neo4j_driver().session(**session_kwargs) as session:
        yield session


def close_neo4j_driver() -> None:
    if get_neo4j_driver.cache_info().currsize:
        get_neo4j_driver().close()
        get_neo4j_driver.cache_clear()
