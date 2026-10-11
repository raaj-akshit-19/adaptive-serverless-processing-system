"""Read and write the adaptive configuration item in DynamoDB.

The table holds one item, addressed by the partition key ``id``:

    {"id": "config", "chunk_size": 2, "last_time": 0.1, "last_size": 4}

CONFIRMED: the record above and its attribute names. The original meanings of
the three fields are unknown; ``adaptive_decision`` documents the meanings
this implementation gives them.
"""

import os
from decimal import Decimal

import boto3

TABLE_ENV_VAR = "CONFIG_TABLE_NAME"
CONFIG_ID = "config"
CONFIG_FIELDS = ("chunk_size", "last_time", "last_size")


def _get_table():
    return boto3.resource("dynamodb").Table(os.environ[TABLE_ENV_VAR])


def _from_dynamodb(value):
    """DynamoDB returns every number as Decimal; convert to int or float."""
    if not isinstance(value, Decimal):
        return value
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _to_dynamodb(value):
    """boto3 rejects Python floats; DynamoDB numbers must be int or Decimal."""
    if isinstance(value, float):
        return Decimal(str(value))
    return value


def get_config() -> dict:
    """Return the configuration item as a plain dict of Python numbers.

    A missing item is an error. A missing individual field is left out of the
    result; ``adaptive_decision`` applies the defaults.
    """
    response = _get_table().get_item(Key={"id": CONFIG_ID})
    item = response.get("Item")
    if item is None:
        raise LookupError(
            f'No item with id "{CONFIG_ID}" in the configuration table. '
            "Seed the table before invoking the function."
        )
    config = {"id": CONFIG_ID}
    for field in CONFIG_FIELDS:
        if field in item:
            config[field] = _from_dynamodb(item[field])
    return config


def save_config(config: dict) -> None:
    """Write the configuration item back. Only the known fields are stored."""
    item = {"id": CONFIG_ID}
    for field in CONFIG_FIELDS:
        item[field] = _to_dynamodb(config[field])
    _get_table().put_item(Item=item)
