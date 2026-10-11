"""Controller Function: accepts physiological input, evaluates risk, selects
the execution mode, dispatches work to the Worker Functions, consolidates the
results and feeds execution performance back into the stored configuration.

CONFIRMED: the Controller Function and the responsibilities above.

DERIVED: the order of the steps in the code below.

NEW (reconstructed): the event schema, its validation rules and the response
structure. The original ones were not recovered.
"""

import time

from controller.adaptive_decision import PARALLEL, choose_processing_mode, update_adaptive_config
from controller.alert_activation import activate_alert, build_alert_request
from controller.consolidation import consolidate_results
from controller.dispatch import build_worker_event, run_parallel, run_sequential
from controller.dynamodb_config import get_config, save_config
from controller.risk_assessment import CRITICAL, FIELDS, assess_readings
from controller.segmentation import segment_workload


def _validate_reading(reading, index) -> dict:
    if not isinstance(reading, dict):
        raise ValueError(f"Reading {index} must be an object")
    for field in FIELDS:
        if field not in reading:
            raise ValueError(f'Reading {index} is missing "{field}"')
        value = reading[field]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'Reading {index}: "{field}" must be a number')
    if not 0 < reading["spo2"] <= 100:
        raise ValueError(f'Reading {index}: "spo2" must be above 0 and at most 100')
    if not reading["heart_rate"] > 0:
        raise ValueError(f'Reading {index}: "heart_rate" must be above 0')
    if not reading["hrv"] >= 0:
        raise ValueError(f'Reading {index}: "hrv" must be 0 or above')
    if not reading["respiratory_rate"] > 0:
        raise ValueError(f'Reading {index}: "respiratory_rate" must be above 0')
    return {field: reading[field] for field in FIELDS}


def extract_input(event) -> list:
    """Return the validated list of readings from the event.

    Raises ValueError if the event or any reading is invalid.
    """
    if not isinstance(event, dict) or "readings" not in event:
        raise ValueError('Event must contain "readings"')
    readings = event["readings"]
    if not isinstance(readings, list) or not readings:
        raise ValueError('"readings" must be a non-empty list')
    return [_validate_reading(reading, index) for index, reading in enumerate(readings)]


def lambda_handler(event, context):
    readings = extract_input(event)
    workload_size = len(readings)

    score, risk_level, highest_risk_reading = assess_readings(readings)
    print(f"Risk level: {risk_level}, score: {score}")

    # Independent alert pathway: the Alert Microservice is activated
    # asynchronously and does not depend on completion of the processing
    # below. A failed activation is logged and must not stop processing.
    alert_activated = False
    if risk_level == CRITICAL:
        try:
            activate_alert(build_alert_request(score, risk_level, highest_risk_reading))
            alert_activated = True
            print("Alert Microservice activated")
        except Exception as error:
            print(f"Alert activation failed: {error}")

    # The configuration read here holds the previous run's values. It is not
    # modified; the feedback update below is calculated from it.
    config = get_config()
    mode, segment_size = choose_processing_mode(risk_level, workload_size, config)
    print(f"Processing mode: {mode}, segment size: {segment_size}")

    start = time.time()
    if mode == PARALLEL:
        segments = segment_workload(readings, segment_size)
        results = run_parallel([build_worker_event(segment) for segment in segments])
    else:
        results = run_sequential(build_worker_event(readings))
    result = consolidate_results(results)
    execution_time = time.time() - start
    print(f"Execution time: {execution_time:.3f} s")

    save_config(update_adaptive_config(config, workload_size, execution_time, mode))

    return {
        "risk_level": risk_level,
        "risk_score": score,
        "mode": mode,
        "execution_time": round(execution_time, 3),
        "alert_activated": alert_activated,
        "result": result,
    }
