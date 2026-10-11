"""Merge Worker results into the final result.

CONFIRMED: processed outputs from the Workers are merged to form the final
result.

NEW (reconstructed): the merge rule and the result structure. The original
ones were not recovered.
"""

from controller.risk_assessment import FIELDS


def consolidate_results(results: list) -> dict:
    """Return overall count and per-parameter mean, min and max.

    Counts and sums are added; the smallest minimum and largest maximum are
    kept. One result covering the whole workload and several results covering
    its segments give the same output.
    """
    if not results:
        raise ValueError("No Worker results to consolidate")

    count = sum(result["count"] for result in results)
    final = {"count": count}
    for field in FIELDS:
        total = sum(result[field]["sum"] for result in results)
        final[field] = {
            "mean": round(total / count, 2),
            "min": min(result[field]["min"] for result in results),
            "max": max(result[field]["max"] for result in results),
        }
    return final
