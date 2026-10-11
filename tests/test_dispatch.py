import io
import json
from unittest.mock import MagicMock

import pytest

from controller import dispatch


def fake_lambda_client(handler):
    """A stand-in Lambda client whose invoke() runs ``handler`` on the payload."""
    client = MagicMock()

    def invoke(FunctionName, InvocationType, Payload):
        result = handler(json.loads(Payload))
        return {"Payload": io.BytesIO(json.dumps(result).encode())}

    client.invoke.side_effect = invoke
    return client


@pytest.fixture(autouse=True)
def worker_name(monkeypatch):
    monkeypatch.setenv("WORKER_FUNCTION_NAME", "worker-from-env")


def test_worker_event_wraps_the_readings():
    readings = [{"spo2": 97, "heart_rate": 72, "hrv": 45, "respiratory_rate": 16}]

    assert dispatch.build_worker_event(readings) == {"readings": readings}


def test_invoke_worker_calls_the_worker_synchronously():
    client = fake_lambda_client(lambda event: {"echo": event})

    result = dispatch.invoke_worker(client, {"a": 1})

    client.invoke.assert_called_once_with(
        FunctionName="worker-from-env",
        InvocationType="RequestResponse",
        Payload=json.dumps({"a": 1}),
    )
    assert result == {"echo": {"a": 1}}


def test_invoke_worker_raises_when_the_worker_fails():
    client = MagicMock()
    client.invoke.return_value = {
        "FunctionError": "Unhandled",
        "Payload": io.BytesIO(b'{"errorMessage": "boom"}'),
    }

    with pytest.raises(RuntimeError, match="boom"):
        dispatch.invoke_worker(client, {})


def test_run_sequential_makes_one_invocation(monkeypatch):
    client = fake_lambda_client(lambda event: {"echo": event})
    monkeypatch.setattr(dispatch, "_lambda_client", lambda: client)

    results = dispatch.run_sequential({"a": 1})

    assert client.invoke.call_count == 1
    assert results == [{"echo": {"a": 1}}]


def test_run_parallel_makes_one_invocation_per_event(monkeypatch):
    client = fake_lambda_client(lambda event: {"echo": event})
    monkeypatch.setattr(dispatch, "_lambda_client", lambda: client)
    events = [{"n": n} for n in range(5)]

    results = dispatch.run_parallel(events)

    assert client.invoke.call_count == 5
    assert results == [{"echo": event} for event in events]


def test_run_parallel_with_no_events_invokes_nothing(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(dispatch, "_lambda_client", lambda: client)

    assert dispatch.run_parallel([]) == []
    client.invoke.assert_not_called()
