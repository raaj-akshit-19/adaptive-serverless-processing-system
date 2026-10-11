"""Alert Microservice: handles critical alerts independently of the primary
processing workflow.

CONFIRMED: a dedicated Alert Microservice exists and operates independently.

DERIVED: it is a Lambda function that receives an alert request from the
Controller, builds the message and publishes it to SNS.
"""

from alert.sns_alert import build_alert_message, publish_critical_alert


def lambda_handler(event, context):
    message = build_alert_message(event)
    publish_critical_alert(message)
    print("Critical alert published")
