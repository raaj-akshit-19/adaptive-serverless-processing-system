import json
from unittest.mock import MagicMock

from controller import alert_activation
from controller import lambda_function as controller_lambda

READING = {"spo2": 88, "heart_rate": 125, "hrv": 15, "respiratory_rate": 26}


def test_alert_request_carries_level_score_and_reading():
    request = alert_activation.build_alert_request(0.601, "Critical", READING)

    assert request == {"risk_level": "Critical", "risk_score": 0.601, "reading": READING}


def test_activate_alert_invokes_the_alert_function_asynchronously(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(alert_activation, "_lambda_client", lambda: client)
    monkeypatch.setenv("ALERT_FUNCTION_NAME", "alert-from-env")

    alert_activation.activate_alert({"a": 1})

    client.invoke.assert_called_once_with(
        FunctionName="alert-from-env",
        InvocationType="Event",
        Payload=json.dumps({"a": 1}),
    )


def test_controller_uses_the_alert_activation_boundary():
    assert controller_lambda.activate_alert is alert_activation.activate_alert
    assert controller_lambda.build_alert_request is alert_activation.build_alert_request


def test_controller_does_not_publish_to_sns_itself(aws):
    controller_lambda.lambda_handler({"readings": [READING]}, None)

    assert not hasattr(controller_lambda, "publish_critical_alert")
    aws.sns.publish.assert_not_called()
    assert len(aws.alert_requests) == 1
