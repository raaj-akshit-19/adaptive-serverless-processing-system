import math

import pytest

from controller.adaptive_decision import (
    PARALLEL,
    SEQUENTIAL,
    bounded_chunk_size,
    choose_processing_mode,
    update_adaptive_config,
)
from controller.risk_assessment import CRITICAL, MODERATE, NORMAL

# The known record: previous normalized metric is 0.1 / 4 = 0.025 s per reading.
CONFIG = {"id": "config", "chunk_size": 2, "last_time": 0.1, "last_size": 4}


def config(**changes):
    return {**CONFIG, **changes}


# --- chunk size bounds -------------------------------------------------------

@pytest.mark.parametrize(
    "stored, expected",
    [(2, 2), (1, 1), (10, 10), (0, 1), (-3, 1), (11, 10), (50, 10), (3.7, 3), ("4", 2), (None, 2)],
)
def test_chunk_size_is_bounded(stored, expected):
    assert bounded_chunk_size({"chunk_size": stored}) == expected


def test_missing_chunk_size_uses_the_default():
    assert bounded_chunk_size({}) == 2


# --- execution mode and segment size -----------------------------------------

@pytest.mark.parametrize("workload_size", [1, 6, 100])
def test_normal_risk_is_sequential(workload_size):
    assert choose_processing_mode(NORMAL, workload_size, CONFIG) == (SEQUENTIAL, workload_size)


def test_moderate_risk_uses_the_chunk_size():
    assert choose_processing_mode(MODERATE, 6, CONFIG) == (PARALLEL, 2)


def test_critical_risk_halves_the_chunk_size():
    assert choose_processing_mode(CRITICAL, 6, CONFIG) == (PARALLEL, 1)
    assert choose_processing_mode(CRITICAL, 20, config(chunk_size=5)) == (PARALLEL, 2)


def test_critical_segment_size_is_never_below_one():
    assert choose_processing_mode(CRITICAL, 6, config(chunk_size=1)) == (PARALLEL, 1)


@pytest.mark.parametrize(
    "risk_level, workload_size",
    [(MODERATE, 1), (MODERATE, 2), (CRITICAL, 1)],
)
def test_workload_within_one_segment_is_sequential(risk_level, workload_size):
    assert choose_processing_mode(risk_level, workload_size, CONFIG) == (SEQUENTIAL, workload_size)


@pytest.mark.parametrize(
    "risk_level, workload_size, expected_segment_size",
    [(MODERATE, 45, 5), (CRITICAL, 100, 10), (MODERATE, 21, 3), (CRITICAL, 11, 2)],
)
def test_never_more_than_ten_segments(risk_level, workload_size, expected_segment_size):
    mode, segment_size = choose_processing_mode(risk_level, workload_size, CONFIG)

    assert (mode, segment_size) == (PARALLEL, expected_segment_size)
    assert math.ceil(workload_size / segment_size) <= 10


def test_out_of_range_chunk_size_is_bounded_before_use():
    assert choose_processing_mode(MODERATE, 5, config(chunk_size=0)) == (PARALLEL, 1)
    assert choose_processing_mode(MODERATE, 25, config(chunk_size=50)) == (PARALLEL, 10)


def test_missing_chunk_size_falls_back_to_the_default():
    assert choose_processing_mode(MODERATE, 6, {"id": "config"}) == (PARALLEL, 2)


# --- feedback update ---------------------------------------------------------

def test_valid_previous_timing_records_the_current_run():
    new = update_adaptive_config(CONFIG, 10, 0.25, PARALLEL)

    assert new == {"id": "config", "chunk_size": 2, "last_time": 0.25, "last_size": 10}


def test_parallel_run_decreases_chunk_size_when_metric_worsens():
    # 0.5 / 10 = 0.05 s per reading, more than 10% above 0.025
    new = update_adaptive_config(CONFIG, 10, 0.5, PARALLEL)

    assert new["chunk_size"] == 1


def test_parallel_run_increases_chunk_size_when_metric_improves():
    # 0.2 / 10 = 0.02 s per reading, more than 10% below 0.025
    new = update_adaptive_config(CONFIG, 10, 0.2, PARALLEL)

    assert new["chunk_size"] == 3


@pytest.mark.parametrize("execution_time", [0.25, 0.27, 0.23])
def test_no_adjustment_inside_the_tolerance(execution_time):
    new = update_adaptive_config(CONFIG, 10, execution_time, PARALLEL)

    assert new["chunk_size"] == 2


@pytest.mark.parametrize("execution_time", [0.001, 0.25, 50.0])
def test_sequential_run_does_not_adjust_chunk_size(execution_time):
    new = update_adaptive_config(CONFIG, 10, execution_time, SEQUENTIAL)

    assert new["chunk_size"] == 2
    assert new["last_time"] == execution_time
    assert new["last_size"] == 10


@pytest.mark.parametrize(
    "previous",
    [
        {"chunk_size": 2, "last_size": 4},                     # missing previous time
        {"chunk_size": 2, "last_time": 0, "last_size": 4},     # zero previous time
        {"chunk_size": 2, "last_time": -1, "last_size": 4},
        {"chunk_size": 2, "last_time": 0.1},                   # missing previous size
        {"chunk_size": 2, "last_time": 0.1, "last_size": 0},   # zero previous size
        {"chunk_size": 2, "last_time": 0.1, "last_size": -4},
    ],
)
def test_invalid_previous_timing_skips_the_comparison(previous):
    new = update_adaptive_config(previous, 10, 50.0, PARALLEL)

    assert new == {"id": "config", "chunk_size": 2, "last_time": 50.0, "last_size": 10}


def test_chunk_size_does_not_go_below_one():
    new = update_adaptive_config(config(chunk_size=1), 10, 0.5, PARALLEL)

    assert new["chunk_size"] == 1


def test_chunk_size_does_not_go_above_ten():
    new = update_adaptive_config(config(chunk_size=10), 10, 0.2, PARALLEL)

    assert new["chunk_size"] == 10


def test_out_of_range_stored_chunk_size_is_corrected_on_write():
    assert update_adaptive_config(config(chunk_size=50), 10, 0.25, SEQUENTIAL)["chunk_size"] == 10
    assert update_adaptive_config(config(chunk_size=0), 10, 0.25, SEQUENTIAL)["chunk_size"] == 1
    assert update_adaptive_config({"last_time": 0.1, "last_size": 4}, 10, 0.25, SEQUENTIAL)["chunk_size"] == 2


def test_adjustment_uses_previous_values_and_leaves_them_untouched():
    previous = dict(CONFIG)

    new = update_adaptive_config(previous, 10, 0.5, PARALLEL)

    # The decision compared against the previous 0.1 s / 4 readings ...
    assert new["chunk_size"] == 1
    # ... which are still intact, and the new record holds the current run.
    assert previous == CONFIG
    assert new is not previous
    assert (new["last_time"], new["last_size"]) == (0.5, 10)


def test_stored_values_have_the_expected_precision_and_types():
    new = update_adaptive_config(CONFIG, 7, 0.123456, PARALLEL)

    assert new["last_time"] == 0.123
    assert type(new["last_size"]) is int
    assert type(new["chunk_size"]) is int
    assert set(new) == {"id", "chunk_size", "last_time", "last_size"}
