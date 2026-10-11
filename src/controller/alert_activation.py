"""Activate the dedicated Alert Microservice from the Controller.

CONFIRMED: critical risk activates an independent alert pathway that does not
depend on completion of the primary processing workflow.

DERIVED: the Alert Microservice is a Lambda function, activated through the
Lambda Invoke API with an asynchronous (Event) invocation so the Controller
does not wait for it. This is an implementation choice, not a recovered
historical detail.

NEW (reconstructed): the fields of the alert request. The original request
was not recovered.
"""

import json
import os

import boto3

ALERT_FUNCTION_ENV_VAR = "ALERT_FUNCTION_NAME"


def _lambda_client():
    return boto3.client("lambda")


def build_alert_request(score, risk_level, reading) -> dict:
    """Return the event sent to the Alert Microservice."""
    return {
        "risk_level": risk_level,
        "risk_score": score,
        "reading": reading,
    }


def activate_alert(alert_request) -> None:
    """Invoke the Alert Microservice without waiting for it to finish."""
    _lambda_client().invoke(
        FunctionName=os.environ[ALERT_FUNCTION_ENV_VAR],
        InvocationType="Event",
        Payload=json.dumps(alert_request),
    )
