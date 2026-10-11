import pytest

from controller.consolidation import consolidate_results
from controller.segmentation import segment_workload
from worker import lambda_function as worker_lambda

TWO_READINGS = [
    {"spo2": 97, "heart_rate": 72, "hrv": 45, "respiratory_rate": 16},
    {"spo2": 93, "heart_rate": 105, "hrv": 30, "respiratory_rate": 22},
]

SAMPLE_RESULT = {
    "count": 6,
    "spo2": {"mean": 93.33, "min": 88, "max": 97},
    "heart_rate": {"mean": 99.67, "min": 72, "max": 125},
    "hrv": {"mean": 31.17, "min": 15, "max": 45},
    "respiratory_rate": {"mean": 20.83, "min": 16, "max": 26},
}


# --- Worker ------------------------------------------------------------------

def test_worker_summarises_a_segment():
    result = worker_lambda.lambda_handler({"readings": TWO_READINGS}, None)

    assert result == {
        "count": 2,
        "spo2": {"sum": 190, "min": 93, "max": 97},
        "heart_rate": {"sum": 177, "min": 72, "max": 105},
        "hrv": {"sum": 75, "min": 30, "max": 45},
        "respiratory_rate": {"sum": 38, "min": 16, "max": 22},
    }


def test_worker_handles_a_single_reading():
    result = worker_lambda.lambda_handler({"readings": TWO_READINGS[:1]}, None)

    assert result["count"] == 1
    assert result["spo2"] == {"sum": 97, "min": 97, "max": 97}


def test_worker_is_deterministic():
    event = {"readings": TWO_READINGS}

    assert worker_lambda.lambda_handler(event, None) == worker_lambda.lambda_handler(event, None)


def test_worker_processes_each_segment_independently(sample_event):
    segments = segment_workload(sample_event["readings"], 2)

    results = [worker_lambda.lambda_handler({"readings": segment}, None) for segment in segments]

    assert [result["count"] for result in results] == [2, 2, 2]
    assert [result["spo2"]["sum"] for result in results] == [193, 181, 186]


def test_worker_rejects_an_empty_segment():
    with pytest.raises(ValueError):
        worker_lambda.lambda_handler({"readings": []}, None)


# --- Consolidation -----------------------------------------------------------

def test_consolidating_a_single_result(sample_event):
    whole = worker_lambda.process_work(sample_event)

    assert consolidate_results([whole]) == SAMPLE_RESULT


def test_consolidating_multiple_results(sample_event):
    segments = segment_workload(sample_event["readings"], 2)
    results = [worker_lambda.process_work({"readings": segment}) for segment in segments]

    assert consolidate_results(results) == SAMPLE_RESULT


@pytest.mark.parametrize("segment_size", [1, 2, 3, 4, 5, 6])
def test_segmented_processing_matches_processing_the_whole_workload(sample_event, segment_size):
    readings = sample_event["readings"]
    whole = consolidate_results([worker_lambda.process_work({"readings": readings})])

    segments = segment_workload(readings, segment_size)
    segmented = consolidate_results(
        [worker_lambda.process_work({"readings": segment}) for segment in segments]
    )

    assert segmented == whole


def test_mean_min_and_max_are_correct():
    results = [
        {"count": 1, "spo2": {"sum": 90, "min": 90, "max": 90},
         "heart_rate": {"sum": 60, "min": 60, "max": 60},
         "hrv": {"sum": 20, "min": 20, "max": 20},
         "respiratory_rate": {"sum": 12, "min": 12, "max": 12}},
        {"count": 2, "spo2": {"sum": 195, "min": 96, "max": 99},
         "heart_rate": {"sum": 181, "min": 80, "max": 101},
         "hrv": {"sum": 91, "min": 41, "max": 50},
         "respiratory_rate": {"sum": 35, "min": 15, "max": 20}},
    ]

    final = consolidate_results(results)

    assert final == {
        "count": 3,
        "spo2": {"mean": 95.0, "min": 90, "max": 99},
        "heart_rate": {"mean": 80.33, "min": 60, "max": 101},
        "hrv": {"mean": 37.0, "min": 20, "max": 50},
        "respiratory_rate": {"mean": 15.67, "min": 12, "max": 20},
    }


def test_consolidating_no_results_is_an_error():
    with pytest.raises(ValueError):
        consolidate_results([])
