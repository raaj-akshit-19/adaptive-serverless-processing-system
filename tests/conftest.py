import io
import json
import os
from decimal import Decimal
from unittest.mock import MagicMock

import boto3
import pytest

from alert import sns_alert
from controller import alert_activation, dispatch, dynamodb_config
from worker import lambda_function as worker_lambda

SAMPLE_EVENT_PATH = os.path.join(os.path.dirname(__file__), "..", "examples", "sample_event.json")


@pytest.fixture(autouse=True)
def block_aws(monkeypatch):
    """Fail any test that would create a real AWS client or resource."""

    def blocked(*args, **kwargs):
        raise AssertionError("Test tried to contact AWS")

    monkeypatch.setattr(boto3, "client", blocked)
    monkeypatch.setattr(boto3, "resource", blocked)


@pytest.fixture
def sample_event():
    with open(SAMPLE_EVENT_PATH) as f:
        return json.load(f)


class FakeAws:
    """In-memory stand-ins for the DynamoDB table, the Lambda client and SNS.

    Worker invocations run the real Worker handler. Alert invocations are
    recorded and not executed, matching an asynchronous invocation.
    """

    WORKER_FUNCTION = "worker-function"
    ALERT_FUNCTION = "alert-function"

    def __init__(self):
        self.table = MagicMock()
        self.table.get_item.return_value = {
            "Item": {
                "id": "config",
                "chunk_size": Decimal("2"),
                "last_time": Decimal("0.1"),
                "last_size": Decimal("4"),
            }
        }
        self.sns = MagicMock()
        self.worker_events = []
        self.alert_requests = []
        self.fail_worker = False
        self.fail_alert = False
        self.lambda_client = MagicMock()
        self.lambda_client.invoke.side_effect = self._invoke

    def _invoke(self, FunctionName, InvocationType, Payload):
        event = json.loads(Payload)
        if FunctionName == self.ALERT_FUNCTION:
            assert InvocationType == "Event"
            if self.fail_alert:
                raise RuntimeError("alert function unavailable")
            self.alert_requests.append(event)
            return {"StatusCode": 202}

        assert FunctionName == self.WORKER_FUNCTION
        assert InvocationType == "RequestResponse"
        self.worker_events.append(event)
        if self.fail_worker:
            return {
                "FunctionError": "Unhandled",
                "Payload": io.BytesIO(b'{"errorMessage": "worker crashed"}'),
            }
        result = worker_lambda.lambda_handler(event, None)
        return {"Payload": io.BytesIO(json.dumps(result).encode())}

    @property
    def saved_config(self):
        return self.table.put_item.call_args.kwargs["Item"]


@pytest.fixture
def aws(monkeypatch):
    fake = FakeAws()
    monkeypatch.setenv("CONFIG_TABLE_NAME", "config-table")
    monkeypatch.setenv("WORKER_FUNCTION_NAME", FakeAws.WORKER_FUNCTION)
    monkeypatch.setenv("ALERT_FUNCTION_NAME", FakeAws.ALERT_FUNCTION)
    monkeypatch.setenv("ALERT_TOPIC_ARN", "alert-topic")
    monkeypatch.setattr(dynamodb_config, "_get_table", lambda: fake.table)
    monkeypatch.setattr(dispatch, "_lambda_client", lambda: fake.lambda_client)
    monkeypatch.setattr(alert_activation, "_lambda_client", lambda: fake.lambda_client)
    monkeypatch.setattr(sns_alert, "_sns_client", lambda: fake.sns)
    return fake
