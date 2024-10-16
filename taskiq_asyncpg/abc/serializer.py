from abc import ABC, abstractmethod
from typing import Any, Optional


class TaskiqAsyncpgSerializer(ABC):
    """Custom serializer for taskiq asyncpg."""

    def __init__(self, database_type: Optional[str] = None) -> None:
        self.__database_type = database_type or "BYTEA"

    @property
    def database_type(self) -> str:
        """
        Return a database type to create a table.

        Returns:
            str: Type of table
        """
        return self.__database_type

    @abstractmethod
    def dumpb(self, value: Any) -> bytes:
        """
        Dump value to bytes for saving in database.

        Args:
            value (Any): value to encode.

        Returns:
            bytes: encoded value.

        """

    @abstractmethod
    def loadb(self, value: bytes) -> Any:
        """
        Parse byte-encoded value received from database.

        Args:
            value (bytes): value to parse.

        Returns:
            Any: decoded value.

        """
