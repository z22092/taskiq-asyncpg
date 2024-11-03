from typing import Any, Final, Literal, Optional, TypeVar, cast

from asyncpg import Pool, create_pool
from taskiq import AsyncResultBackend, TaskiqResult

from taskiq_asyncpg.abc.serializer import TaskiqAsyncpgSerializer
from taskiq_asyncpg.exceptions import DatabaseConnectionError, ResultIsMissingError
from taskiq_asyncpg.queries import (
    CREATE_INDEX_QUERY,
    CREATE_TABLE_QUERY,
    DELETE_RESULT_QUERY,
    INSERT_RESULT_QUERY,
    IS_RESULT_EXISTS_QUERY,
    SELECT_RESULT_QUERY,
)
from taskiq_asyncpg.serializers import PickleSerializer

_ReturnType = TypeVar("_ReturnType")


class AsyncpgResultBackend(AsyncResultBackend[_ReturnType]):
    """Result backend for TaskIQ based on Asyncpg."""

    _database_pool: Pool  # type: ignore[type-arg]

    def __init__(
        self,
        dsn: Optional[str] = "postgres://postgres:postgres@localhost:5432/postgres",
        keep_results: bool = True,
        table_name: str = "taskiq_results",
        field_for_task_id: Literal["VarChar", "Text", "Uuid"] = "Uuid",
        serializer: Optional[TaskiqAsyncpgSerializer] = None,
        **connect_kwargs: Any,
    ) -> None:
        """
        Construct new result backend.

        :param dsn: connection string to PostgreSQL.
        :param keep_results: flag to not remove results from Redis after reading.
        :param connect_kwargs: additional arguments for nats `ConnectionPool` class.
        """
        self.dsn: Final = dsn
        self.keep_results: Final = keep_results
        self.table_name: Final = table_name
        self.field_for_task_id: Final = field_for_task_id
        self.serializer: Final = serializer or PickleSerializer()
        self.connect_kwargs: Final = connect_kwargs

    async def startup(self) -> None:
        """
        Initialize the result backend.

        Construct new connection pool
        and create new table for results if not exists.
        """
        try:
            self._database_pool = await create_pool(
                self.dsn,
                **self.connect_kwargs,
            )  # type: ignore

            async with self._database_pool.acquire() as connection:
                await connection.execute(
                    CREATE_TABLE_QUERY.format(
                        self.table_name,
                        self.field_for_task_id,
                        self.serializer.database_type,
                    ),
                )
                await connection.execute(
                    CREATE_INDEX_QUERY.format(
                        self.table_name,
                        self.table_name,
                    ),
                )
        except Exception as error:
            raise DatabaseConnectionError(str(error)) from error

    async def shutdown(self) -> None:
        """Close the connection pool."""
        async with self._database_pool.acquire() as connection:
            await connection.close()

    async def set_result(
        self,
        task_id: Any,
        result: TaskiqResult[_ReturnType],
    ) -> None:
        """
        Set result to the PostgreSQL table.

        Args:
            task_id (Any): ID of the task.
            result (TaskiqResult[_ReturnType]):  result of the task.

        """
        async with self._database_pool.acquire() as connection:
            await connection.execute(
                INSERT_RESULT_QUERY.format(
                    self.table_name,
                ),
                task_id,
                self.serializer.dumpb(result),
            )

    async def is_result_ready(self, task_id: Any) -> bool:
        """
        Returns whether the result is ready.

        Args:
            task_id (Any): ID of the task.

        Returns:
            bool: True if the result is ready else False.

        """
        async with self._database_pool.acquire() as connection:
            return cast(
                bool,
                await connection.fetchval(
                    IS_RESULT_EXISTS_QUERY.format(
                        self.table_name,
                    ),
                    task_id,
                ),
            )

    async def get_result(
        self,
        task_id: Any,
        with_logs: bool = False,
    ) -> TaskiqResult[_ReturnType]:
        """
        Retrieve result from the task.

        :param task_id: task's id.
        :param with_logs: if True it will download task's logs.
        :raises ResultIsMissingError: if there is no result when trying to get it.
        :return: TaskiqResult.
        """
        async with self._database_pool.acquire() as connection:
            result_in_bytes: bytes = await connection.fetchval(
                SELECT_RESULT_QUERY.format(
                    self.table_name,
                ),
                task_id,
            )

            if result_in_bytes is None:
                raise ResultIsMissingError(
                    f"Cannot find record with task_id = {task_id} in PostgreSQL",
                )

            if not self.keep_results:
                await connection.execute(
                    DELETE_RESULT_QUERY.format(
                        self.table_name,
                    ),
                    task_id,
                )

            taskiq_result: TaskiqResult[_ReturnType] = self.serializer.loadb(
                result_in_bytes,
            )

            if not with_logs:
                taskiq_result.log = None

            return taskiq_result
