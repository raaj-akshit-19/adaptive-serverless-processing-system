"""Send work to the Worker Functions, sequentially or in parallel.

CONFIRMED: sequential processing, parallel processing, and Worker Functions
that process divided data segments.

DERIVED: the Worker is called through the Lambda Invoke API with a
synchronous (RequestResponse) invocation. Sequential mode is one invocation
with the whole workload. Parallel mode issues one invocation per segment from
a thread pool, so the number of concurrent Worker executions is decided at
runtime. The original mechanism has not been recovered; all Worker invocation
code is kept in this module so it can be replaced in one place.

NEW (reconstructed): the Worker event shape. The original was not recovered.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor

import boto3

WORKER_FUNCTION_ENV_VAR = "WORKER_FUNCTION_NAME"


def _lambda_client():
    return boto3.client("lambda")


def build_worker_event(readings: list) -> dict:
    """Return the event sent to the Worker for one unit of work.

    ``readings`` is either the whole workload (sequential) or one segment
    (parallel).
    """
    return {"readings": readings}


def invoke_worker(client, worker_event):
    """Invoke the Worker once and return its decoded result."""
    response = client.invoke(
        FunctionName=os.environ[WORKER_FUNCTION_ENV_VAR],
        InvocationType="RequestResponse",
        Payload=json.dumps(worker_event),
    )
    payload = json.loads(response["Payload"].read())
    if "FunctionError" in response:
        raise RuntimeError(f"Worker invocation failed: {payload}")
    return payload


def run_sequential(worker_event) -> list:
    """Process the whole workload in a single Worker invocation."""
    return [invoke_worker(_lambda_client(), worker_event)]


def run_parallel(worker_events: list) -> list:
    """Invoke the Worker once per event, concurrently.

    Results are returned in the same order as ``worker_events``.
    """
    if not worker_events:
        return []
    client = _lambda_client()
    with ThreadPoolExecutor(max_workers=len(worker_events)) as pool:
        return list(pool.map(lambda event: invoke_worker(client, event), worker_events))
