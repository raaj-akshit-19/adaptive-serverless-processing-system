"""Adaptive execution decision and performance feedback.

CONFIRMED: normal conditions are processed sequentially and elevated
conditions in parallel; the decision considers risk severity, workload
characteristics and historical execution performance; execution duration is
recorded and used to adjust segmentation for later runs.

NEW (reconstructed): the rules and every number in this module, and the
meanings given to the stored fields:

    chunk_size  readings per segment
    last_time   total execution time of the previous run, in seconds
    last_size   workload size of the previous run, in readings

The original meanings of those fields and the original rules were not
recovered. The feedback policy decreases or increases the segment size based
on whether normalized execution time has worsened or improved relative to the
previous run. It is a heuristic and is not claimed to be optimal.

The original disclosure mentions predictive execution-time estimation, but
the original prediction mechanism was not recovered. This module uses
historical execution performance as feedback; it does not predict execution
time.
"""

import math

from controller.risk_assessment import CRITICAL, NORMAL

SEQUENTIAL = "sequential"
PARALLEL = "parallel"

DEFAULT_CHUNK_SIZE = 2
MIN_CHUNK_SIZE = 1
MAX_CHUNK_SIZE = 10
MAX_SEGMENTS = 10
FEEDBACK_TOLERANCE = 0.10


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def bounded_chunk_size(config) -> int:
    """Return the stored chunk size, defaulted if missing and kept within bounds."""
    chunk_size = config.get("chunk_size")
    if not _is_number(chunk_size):
        return DEFAULT_CHUNK_SIZE
    return max(MIN_CHUNK_SIZE, min(MAX_CHUNK_SIZE, int(chunk_size)))


def choose_processing_mode(risk_level, workload_size, config):
    """Return ``(mode, segment_size)`` for this run.

    In sequential mode the whole workload is one segment, so ``segment_size``
    equals ``workload_size``.
    """
    if risk_level == NORMAL:
        return SEQUENTIAL, workload_size

    segment_size = bounded_chunk_size(config)
    if risk_level == CRITICAL:
        segment_size = max(1, segment_size // 2)
    segment_size = max(segment_size, math.ceil(workload_size / MAX_SEGMENTS))

    if workload_size > segment_size:
        return PARALLEL, segment_size
    return SEQUENTIAL, workload_size


def update_adaptive_config(config, workload_size, execution_time, mode):
    """Return the configuration to store after a run.

    ``config`` is the configuration read before the run and is not modified:
    the adjustment is calculated from those previous values. The chunk size
    changes only after a parallel run with valid previous timing.
    """
    previous_chunk_size = bounded_chunk_size(config)
    previous_last_time = config.get("last_time")
    previous_last_size = config.get("last_size")
    previous_timing_valid = (
        _is_number(previous_last_time) and previous_last_time > 0
        and _is_number(previous_last_size) and previous_last_size > 0
    )

    new_chunk_size = previous_chunk_size
    if mode == PARALLEL and workload_size > 0 and previous_timing_valid:
        # Normalized execution-time feedback metric: seconds per reading.
        current_metric = execution_time / workload_size
        previous_metric = previous_last_time / previous_last_size
        if current_metric > previous_metric * (1 + FEEDBACK_TOLERANCE):
            new_chunk_size = previous_chunk_size - 1
        elif current_metric < previous_metric * (1 - FEEDBACK_TOLERANCE):
            new_chunk_size = previous_chunk_size + 1
    new_chunk_size = max(MIN_CHUNK_SIZE, min(MAX_CHUNK_SIZE, new_chunk_size))

    return {
        "id": "config",
        "chunk_size": new_chunk_size,
        "last_time": round(execution_time, 3),
        "last_size": int(workload_size),
    }
