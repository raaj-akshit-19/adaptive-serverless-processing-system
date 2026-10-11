from decimal import Decimal
from unittest.mock import MagicMock

import boto3
import pytest

from controller import dynamodb_config

KNOWN_CONFIG = {"id": "config", "chunk_size": 2, "last_time": 0.1, "last_size": 4}


@pytest.fixture
def table(monkeypatch):
    table = MagicMock()
    monkeypatch.setattr(dynamodb_config, "_get_table", lambda: table)
    return table


def test_get_config_reads_the_config_item(table):
    table.get_item.return_value = {
        "Item": {
            "id": "config",
            "chunk_size": Decimal("2"),
            "last_time": Decimal("0.1"),
            "last_size": Decimal("4"),
        }
    }

    config = dynamodb_config.get_config()

    table.get_item.assert_called_once_with(Key={"id": "config"})
    assert config == KNOWN_CONFIG


def test_get_config_returns_plain_python_numbers(table):
    table.get_item.return_value = {
        "Item": {
            "id": "config",
            "chunk_size": Decimal("2"),
            "last_time": Decimal("0.1"),
            "last_size": Decimal("4"),
        }
    }

    config = dynamodb_config.get_config()

    assert type(config["chunk_size"]) is int
    assert type(config["last_time"]) is float
    assert type(config["last_size"]) is int


def test_get_config_fails_when_item_is_missing(table):
    table.get_item.return_value = {}

    with pytest.raises(LookupError, match="Seed the table"):
        dynamodb_config.get_config()

    table.put_item.assert_not_called()


def test_get_config_tolerates_missing_individual_fields(table):
    table.get_item.return_value = {"Item": {"id": "config", "last_time": Decimal("0.1")}}

    assert dynamodb_config.get_config() == {"id": "config", "last_time": 0.1}


def test_get_config_with_only_the_key_returns_no_fields(table):
    table.get_item.return_value = {"Item": {"id": "config"}}

    assert dynamodb_config.get_config() == {"id": "config"}


def test_save_config_writes_the_known_item(table):
    dynamodb_config.save_config(KNOWN_CONFIG)

    table.put_item.assert_called_once_with(
        Item={
            "id": "config",
            "chunk_size": 2,
            "last_time": Decimal("0.1"),
            "last_size": 4,
        }
    )


def test_save_config_does_not_store_extra_fields(table):
    dynamodb_config.save_config({**KNOWN_CONFIG, "extra": 1})

    item = table.put_item.call_args.kwargs["Item"]
    assert set(item) == {"id", "chunk_size", "last_time", "last_size"}


def test_save_config_requires_every_known_field(table):
    with pytest.raises(KeyError):
        dynamodb_config.save_config({"chunk_size": 2, "last_time": 0.1})

    table.put_item.assert_not_called()


def test_table_name_comes_from_environment(monkeypatch):
    resource = MagicMock()
    monkeypatch.setattr(boto3, "resource", lambda service: resource)
    monkeypatch.setenv("CONFIG_TABLE_NAME", "table-from-env")

    dynamodb_config._get_table()

    resource.Table.assert_called_once_with("table-from-env")
