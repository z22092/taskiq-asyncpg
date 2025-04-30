import asyncio
import json
import uuid
from typing import Union

import asyncpg
import pytest
from taskiq import AckableMessage, BrokerMessage
from taskiq.utils import maybe_awaitable

from taskiq_asyncpg import AsyncpgBroker
from taskiq_asyncpg.queries import INSERT_MESSAGE_QUERY
from taskiq_asyncpg.exceptions import DatabaseConnectionError

pytestmark = pytest.mark.anyio


async def get_first_task(asyncpg_broker: AsyncpgBroker) -> Union[AckableMessage, bytes]:
    """
    Get the first message from the broker's listen method.

    :param asyncpg_broker: Instance of AsyncpgBroker.
    :return: The first AckableMessage received.
    """
    async for message in asyncpg_broker.listen():
        return message
    return b''


async def test_failure_connection_database() -> None:
    """Test exception raising in connection database."""
    with pytest.raises(expected_exception=DatabaseConnectionError):
        await AsyncpgBroker(
            dsn="postgresql://postgres:postgres@localhost:5432/aaaaaaaaa",
            table_name="postgres_table",
        ).startup()


async def test_when_broker_deliver_message__then_worker_receive_message(asyncpg_broker: AsyncpgBroker) -> None:
    """
    Test that messages are published and read correctly.

    We kick the message, listen to the queue, and check that
    the received message matches what was sent.
    """
    valid_broker_message = BrokerMessage(
        task_id=uuid.uuid4().hex,
        task_name=uuid.uuid4().hex,
        message=b"my_msg",
        labels={
            "label1": "val1",
        },
    )

    worker_task = asyncio.create_task(get_first_task(asyncpg_broker))
    await asyncio.sleep(0.2)

    # Send the message
    await asyncpg_broker.kick(valid_broker_message)
    await asyncio.sleep(0.2)

    message = worker_task.result()
    assert message == valid_broker_message.message


@pytest.mark.parametrize(
    "table_already_exists",
    [
        pytest.param(True, id="table_already_exists"),
        pytest.param(False, id="table_does_not_exist"),
    ],
)
async def test_when_startup__then_table_should_be_created(
    asyncpg_broker: AsyncpgBroker,
    connection: asyncpg.Connection,
    table_already_exists: bool,
) -> None:
    """
    Test the startup process of the broker.

    We drop the messages table, restart the broker, and ensure
    that the table is recreated.
    """
    await asyncpg_broker.shutdown()

    if not table_already_exists:
        await connection.execute(f"DROP TABLE IF EXISTS {asyncpg_broker.table_name}")

    await asyncpg_broker.startup()

    # Verify that the table exists
    table_exists = await connection.fetch(
        f"SELECT * FROM {asyncpg_broker.table_name}"
    )
    assert table_exists == []  # Table should be empty


async def test_listen(asyncpg_broker: AsyncpgBroker, connection: asyncpg.Connection) -> None:
    """
    Test listen.

    Test that the broker can listen to messages inserted directly into the database
    and notified via the channel.
    """
    # Insert a message directly into the database
    message_content = b"test_message"
    task_id = uuid.uuid4().hex
    task_name = "test_task"
    labels = {"label1": "label_val"}
    message_id = await connection.fetchval(
        INSERT_MESSAGE_QUERY.format(asyncpg_broker.table_name),
        task_id,
        task_name,
        message_content.decode(),
        json.dumps(labels),
    )
    # Send a NOTIFY with the message ID
    await connection.execute(f"NOTIFY {asyncpg_broker.channel_name}, '{message_id}'")

    # Listen for the message
    message = await asyncio.wait_for(get_first_task(asyncpg_broker), timeout=1.0)
    assert message.data == message_content

    # Acknowledge the message
    await maybe_awaitable(message.ack())


async def test_wrong_format(asyncpg_broker: AsyncpgBroker, connection: asyncpg.Connection) -> None:
    """Test that messages with incorrect formats are still received."""
    # Insert a message with missing task_id and task_name
    message_id = await connection.fetchval(
        INSERT_MESSAGE_QUERY.format(asyncpg_broker.table_name),
        "",  # Missing task_id
        "",  # Missing task_name
        "wrong",  # Message content
        json.dumps({}),  # Empty labels
    )
    # Send a NOTIFY with the message ID
    await connection.execute(f"NOTIFY {asyncpg_broker.channel_name}, '{message_id}'")

    # Listen for the message
    message = await asyncio.wait_for(get_first_task(asyncpg_broker), timeout=1.0)
    assert message.data == b"wrong"  # noqa: PLR2004

    # Acknowledge the message
    await maybe_awaitable(message.ack())


async def test_delayed_message(asyncpg_broker: AsyncpgBroker) -> None:
    """Test that delayed messages are delivered correctly after the specified delay."""
    # Send a message with a delay
    task_id = uuid.uuid4().hex
    task_name = "test_task"
    sent = BrokerMessage(
        task_id=task_id,
        task_name=task_name,
        message=b"delayed_message",
        labels={
            "delay": "2",  # Delay in seconds
        },
    )
    await asyncpg_broker.kick(sent)

    # Try to get the message immediately (should not be available yet)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(get_first_task(asyncpg_broker), timeout=1.0)

    # Wait for the delay to pass and receive the message
    message = await asyncio.wait_for(get_first_task(asyncpg_broker), timeout=3.0)
    assert message.data == sent.message

    # Acknowledge the message
    await maybe_awaitable(message.ack())