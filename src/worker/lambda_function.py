"""Worker Function: processes one segment of readings and returns a result.

CONFIRMED: Worker Functions process divided data segments, and the original
file begins with ``import time`` followed by this handler signature.

NEW (reconstructed): the computation, the event shape and the result shape.
The original Worker computation was not recovered. This Worker computes
summary statistics that can be merged exactly across segments.
"""

import time

FIELDS = ("spo2", "heart_rate", "hrv", "respiratory_rate")


def process_work(event) -> dict:
    """Return the count and per-parameter sum, min and max for one segment."""
    readings = event["readings"]
    if not readings:
        raise ValueError("Worker received an empty segment")

    result = {"count": len(readings)}
    for field in FIELDS:
        values = [reading[field] for reading in readings]
        result[field] = {"sum": sum(values), "min": min(values), "max": max(values)}
    return result


def lambda_handler(event, context):
    start = time.time()
    result = process_work(event)
    print(f"Processed {result['count']} readings in {time.time() - start:.4f} s")
    return result
