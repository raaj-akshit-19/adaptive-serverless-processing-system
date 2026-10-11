"""Split a workload into segments for parallel processing.

DERIVED: plain slicing into consecutive segments of ``chunk_size`` items.
The original segmentation code has not been recovered. The segment size for
a run is chosen in ``adaptive_decision``.
"""


def segment_workload(workload, chunk_size: int) -> list:
    """Return consecutive slices of ``workload``, each at most ``chunk_size`` long."""
    if chunk_size <= 0:
        raise ValueError(f"chunk_size must be positive, got {chunk_size}")
    return [workload[i:i + chunk_size] for i in range(0, len(workload), chunk_size)]
