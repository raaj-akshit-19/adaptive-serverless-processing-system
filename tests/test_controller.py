"""Controller handler tests, run against in-memory stand-ins for AWS.

Worker invocations execute the real Worker handler, so these tests cover the
whole pipeline: validation, risk, decision, dispatch, consolidation, feedback
and alert activation.
"""

from decimal import Decimal

import pytest

from controller import lambda_function as controller_lambda
from controller.consolidation import consolidate_results
from worker import lambda_function as worker_lambda

NORMAL_READINGS = [
    {"spo2": 97, "heart_rate": 72, "hrv": 45, "respiratory_rate": 16},
    {"spo2": 96, "heart_rate": 80, "hrv": 40, "respiratory_rate": 18},
    {"spo2": 95, "heart_rate": 98, "hrv": 35, "respiratory_rate": 19},
]
MODERATE_READING = {"spo2": 93, "heart_rate": 105, "hrv": 30, "respiratory_rate": 22}
CRITICAL_READING = {"spo2": 88, "heart_rate": 125, "hrv": 15, "respiratory_rate": 26}


def test_normal_event_is_processed_sequentially(aws):
    response = controller_lambda.lambda_handler({"readings": NORMAL_READINGS}, None)

    assert response["risk_level"] == "Normal"
    assert response["risk_score"] == 0.0
    assert response["mode"] == "sequential"
    assert response["alert_activated"] is False
    assert response["result"]["count"] == 3
    assert aws.worker_events == [{"readings": NORMAL_READINGS}]
    assert aws.alert_requests == []


def test_moderate_event_is_processed_in_parallel_segments(aws):
    readings = NORMAL_READINGS + [MODERATE_READING, MODERATE_READING]

    response = controller_lambda.lambda_handler({"readings": readings}, None)

    assert response["risk_level"] == "Moderate"
    assert response["mode"] == "parallel"
    assert response["result"]["count"] == 5
    # chunk_size 2 -> segments of 2, 2 and 1 readings
    assert sorted(len(event["readings"]) for event in aws.worker_events) == [1, 2, 2]
    assert aws.alert_requests == []
    assert response["alert_activated"] is False


def test_critical_sample_event_end_to_end(aws, sample_event):
    response = controller_lambda.lambda_handler(sample_event, None)

    assert response["risk_level"] == "Critical"
    assert response["risk_score"] == 0.601
    assert response["mode"] == "parallel"
    assert response["alert_activated"] is True
    assert response["result"] == {
        "count": 6,
        "spo2": {"mean": 93.33, "min": 88, "max": 97},
        "heart_rate": {"mean": 99.67, "min": 72, "max": 125},
        "hrv": {"mean": 31.17, "min": 15, "max": 45},
        "respiratory_rate": {"mean": 20.83, "min": 16, "max": 26},
    }
    # chunk_size 2 halved for Critical -> six segments of one reading
    assert [len(event["readings"]) for event in aws.worker_events] == [1] * 6
    assert aws.alert_requests == [
        {"risk_level": "Critical", "risk_score": 0.601, "reading": CRITICAL_READING}
    ]


def test_result_does_not_depend_on_how_the_workload_is_segmented(aws, sample_event):
    six_segments = controller_lambda.lambda_handler(sample_event, None)

    # chunk_size 10 halved for Critical -> segments of 5 and 1 readings
    aws.worker_events.clear()
    aws.table.get_item.return_value["Item"]["chunk_size"] = Decimal("10")
    two_segments = controller_lambda.lambda_handler(sample_event, None)

    whole = consolidate_results([worker_lambda.process_work(sample_event)])

    assert sorted(len(event["readings"]) for event in aws.worker_events) == [1, 5]
    assert six_segments["result"] == two_segments["result"] == whole


def test_critical_reading_with_lower_score_than_a_moderate_reading(aws):
    critical_low_score = {"spo2": 97, "heart_rate": 72, "hrv": 5, "respiratory_rate": 16}    # 0.15
    moderate_high_score = {"spo2": 90, "heart_rate": 120, "hrv": 45, "respiratory_rate": 24}  # 0.40

    response = controller_lambda.lambda_handler(
        {"readings": [moderate_high_score, critical_low_score]}, None
    )

    assert response["risk_level"] == "Critical"
    assert response["risk_score"] == 0.4
    assert response["alert_activated"] is True
    assert aws.alert_requests == [
        {"risk_level": "Critical", "risk_score": 0.4, "reading": critical_low_score}
    ]
    # Critical halves chunk_size 2 -> two segments of one reading
    assert response["mode"] == "parallel"
    assert [len(event["readings"]) for event in aws.worker_events] == [1, 1]


def test_single_critical_reading_is_sequential_and_still_alerts(aws):
    response = controller_lambda.lambda_handler({"readings": [CRITICAL_READING]}, None)

    assert response["risk_level"] == "Critical"
    assert response["mode"] == "sequential"
    assert response["alert_activated"] is True
    assert len(aws.alert_requests) == 1
    assert len(aws.worker_events) == 1


def test_feedback_is_stored_in_one_write_with_all_three_fields(aws, sample_event):
    response = controller_lambda.lambda_handler(sample_event, None)

    assert aws.table.put_item.call_count == 1
    saved = aws.saved_config
    assert set(saved) == {"id", "chunk_size", "last_time", "last_size"}
    assert saved["id"] == "config"
    assert saved["last_size"] == 6
    assert float(saved["last_time"]) == response["execution_time"]
    assert 1 <= saved["chunk_size"] <= 10


def test_sequential_run_leaves_chunk_size_unchanged(aws):
    controller_lambda.lambda_handler({"readings": NORMAL_READINGS}, None)

    assert aws.saved_config["chunk_size"] == 2
    assert aws.saved_config["last_size"] == 3


def test_missing_config_fields_use_the_defaults(aws):
    aws.table.get_item.return_value = {"Item": {"id": "config"}}
    readings = NORMAL_READINGS + [MODERATE_READING, MODERATE_READING]

    response = controller_lambda.lambda_handler({"readings": readings}, None)

    assert response["mode"] == "parallel"
    assert sorted(len(event["readings"]) for event in aws.worker_events) == [1, 2, 2]
    # No valid previous timing, so the default chunk size is stored unchanged.
    assert aws.saved_config["chunk_size"] == 2
    assert aws.saved_config["last_size"] == 5


def test_alert_failure_does_not_stop_processing(aws, sample_event):
    aws.fail_alert = True

    response = controller_lambda.lambda_handler(sample_event, None)

    assert response["risk_level"] == "Critical"
    assert response["alert_activated"] is False
    assert response["result"]["count"] == 6
    assert aws.table.put_item.call_count == 1


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"readings": []},
        {"readings": [{"spo2": 0, "heart_rate": 72, "hrv": 45, "respiratory_rate": 16}]},
        {"readings": [CRITICAL_READING, {"spo2": 97, "heart_rate": 72, "hrv": 45}]},
    ],
)
def test_invalid_input_does_nothing_but_fail(aws, event):
    with pytest.raises(ValueError):
        controller_lambda.lambda_handler(event, None)

    aws.lambda_client.invoke.assert_not_called()
    aws.table.get_item.assert_not_called()
    aws.table.put_item.assert_not_called()


def test_worker_failure_fails_the_run_without_updating_feedback(aws, sample_event):
    aws.fail_worker = True

    with pytest.raises(RuntimeError, match="worker crashed"):
        controller_lambda.lambda_handler(sample_event, None)

    aws.table.put_item.assert_not_called()
    # The alert was activated independently of the failed processing.
    assert len(aws.alert_requests) == 1


def test_missing_config_item_fails_with_a_seed_error(aws, sample_event):
    aws.table.get_item.return_value = {}

    with pytest.raises(LookupError, match="Seed the table"):
        controller_lambda.lambda_handler(sample_event, None)

    assert aws.worker_events == []
    aws.table.put_item.assert_not_called()
    assert len(aws.alert_requests) == 1
