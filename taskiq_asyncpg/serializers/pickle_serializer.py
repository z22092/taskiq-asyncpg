from pickle import dumps, loads
from typing import Any

from taskiq_asyncpg.abc.serializer import TaskiqAsyncpgSerializer


class PickleSerializer(TaskiqAsyncpgSerializer):
    """Custom pickle for taskiq asyncpg."""

    def __init__(self) -> None:
        super().__init__(database_type="BYTEA")

    def dumpb(self, value: Any) -> bytes:
        """
        Dump value to bytes for saving in database.

        Args:
            value (Any): value to encode.

        Returns:
            bytes: encoded value.

        """
        return dumps(value)

    def loadb(self, value: bytes) -> Any:
        """
        Parse byte-encoded value received from database.

        Args:
            value (bytes): value to parse.

        Returns:
            Any: decoded value.

        """
        return loads(value)  # noqa: S301
