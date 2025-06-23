import os
import random
import string
from typing import AsyncGenerator, TypeVar

import asyncpg
import pytest

from taskiq_asyncpg.broker import AsyncpgBroker
from taskiq_asyncpg.result_backend import AsyncpgResultBackend

_ReturnType = TypeVar("_ReturnType")


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """
    Anyio backend.

    Backend for anyio pytest plugin.
    :return: backend name.
    """
    return "asyncio"


@pytest.fixture
def postgres_table() -> str:
    """
    Name of a postgresql table for current test.

    :return: random string.
    """
    return "".join(
        random.choice(
            string.ascii_lowercase,
        )
        for _ in range(10)
    )


@pytest.fixture
def postgresql_dsn() -> str:
    """
    DSN to PostgreSQL.

    :return: dsn to PostgreSQL.
    """
    return (
        os.environ.get("POSTGRESQL_URL")
        or "postgresql://postgres:postgres@localhost:5432/taskiqasyncpg"
    )

@pytest.fixture
async def connection(postgresql_dsn: str) -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Fixture to create a connection to PostgreSQL.

    :param postgresql_dsn: DSN to PostgreSQL.
    :return: connection to PostgreSQL.
    """
    conn = await asyncpg.connect(postgresql_dsn)
    yield conn
    await conn.close()


@pytest.fixture()
async def asyncpg_result_backend(
    postgresql_dsn: str,
    postgres_table: str,
) -> AsyncGenerator[AsyncpgResultBackend[_ReturnType], None]:
    backend: AsyncpgResultBackend[_ReturnType] = AsyncpgResultBackend(
        dsn=postgresql_dsn,
        table_name=postgres_table,
    )
    await backend.startup()
    yield backend
    await backend._database_pool.execute(f"DROP TABLE {postgres_table}")
    await backend.shutdown()


@pytest.fixture()
async def asyncpg_broker(
    postgresql_dsn: str,
    postgres_table: str,
) -> AsyncGenerator[AsyncpgBroker, None]:
    """
    Fixture to set up and tear down the broker.

    Initializes the broker with test parameters.
    """
    broker = AsyncpgBroker(
        dsn=postgresql_dsn,
        channel_name=f"{postgres_table}_channel",
        table_name=postgres_table,
    )
    await broker.startup()
    yield broker
    assert broker.write_pool
    await broker.write_pool.execute(
        f"DROP TABLE {postgres_table}",
    )
    await broker.shutdown()
