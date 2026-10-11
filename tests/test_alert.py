from unittest.mock import MagicMock

from alert import lambda_function as alert_lambda
from alert import sns_alert

ALERT_REQUEST = {
    "risk_level": "Critical",
    "risk_score": 0.601,
    "reading": {"spo2": 88, "heart_rate": 125, "hrv": 15, "respiratory_rate": 26},
}

ALERT_MESSAGE = (
    "Critical physiological risk detected.\n"
    "Risk score: 0.601\n"
    "SpO2: 88 %\n"
    "Heart rate: 125 bpm\n"
    "HRV: 15 ms\n"
    "Respiratory rate: 26 breaths/min"
)


def test_message_reports_the_score_and_the_reading():
    assert sns_alert.build_alert_message(ALERT_REQUEST) == ALERT_MESSAGE


def test_publish_sends_subject_and_message_to_the_topic_from_environment(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(sns_alert, "_sns_client", lambda: client)
    monkeypatch.setenv("ALERT_TOPIC_ARN", "topic-arn-from-env")

    sns_alert.publish_critical_alert("alert text")

    client.publish.assert_called_once_with(
        TopicArn="topic-arn-from-env",
        Subject="Critical physiological risk alert",
        Message="alert text",
    )


def test_handler_publishes_the_alert_for_a_request(aws):
    alert_lambda.lambda_handler(ALERT_REQUEST, None)

    aws.sns.publish.assert_called_once_with(
        TopicArn="alert-topic",
        Subject="Critical physiological risk alert",
        Message=ALERT_MESSAGE,
    )


def test_alert_microservice_touches_only_sns(aws):
    alert_lambda.lambda_handler(ALERT_REQUEST, None)

    aws.lambda_client.invoke.assert_not_called()
    aws.table.get_item.assert_not_called()
    aws.table.put_item.assert_not_called()
