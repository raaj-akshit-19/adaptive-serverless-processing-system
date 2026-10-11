import pytest

from controller.segmentation import segment_workload


def test_splits_evenly():
    assert segment_workload([1, 2, 3, 4], 2) == [[1, 2], [3, 4]]


def test_last_segment_holds_the_remainder():
    assert segment_workload([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunk_size_larger_than_workload_gives_one_segment():
    assert segment_workload([1, 2, 3], 10) == [[1, 2, 3]]


def test_empty_workload_gives_no_segments():
    assert segment_workload([], 2) == []


def test_segments_preserve_order_and_content():
    workload = list(range(24))
    segments = segment_workload(workload, 5)
    assert [item for segment in segments for item in segment] == workload


@pytest.mark.parametrize("chunk_size", [0, -1])
def test_non_positive_chunk_size_is_rejected(chunk_size):
    with pytest.raises(ValueError):
        segment_workload([1, 2, 3], chunk_size)
