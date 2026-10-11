"""Build and publish the critical-risk alert through SNS.

CONFIRMED: critical alerts are handled by a dedicated Alert Microservice, and
SNS is the notification mechanism.

DERIVED: the Alert Microservice publishes to SNS itself.

NEW (reconstructed): the alert subject and message text. The original message
was not recovered.
"""

import os

import boto3

TOPIC_ENV_VAR = "ALERT_TOPIC_ARN"
ALERT_SUBJECT = "Critical physiological risk alert"


def _sns_client():
    return boto3.client("sns")


def build_alert_message(alert_request) -> str:
    """Return the text of the critical-risk alert for one alert request."""
    reading = alert_request["reading"]
    return "\n".join([
        "Critical physiological risk detected.",
        f"Risk score: {alert_request['risk_score']}",
        f"SpO2: {reading['spo2']} %",
        f"Heart rate: {reading['heart_rate']} bpm",
        f"HRV: {reading['hrv']} ms",
        f"Respiratory rate: {reading['respiratory_rate']} breaths/min",
    ])


def publish_critical_alert(message: str) -> None:
    """Publish ``message`` to the alert topic."""
    _sns_client().publish(
        TopicArn=os.environ[TOPIC_ENV_VAR],
        Subject=ALERT_SUBJECT,
        Message=message,
    )
