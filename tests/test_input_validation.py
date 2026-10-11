import pytest

from controller.lambda_function import extract_input

VALID = {"spo2": 97, "heart_rate": 72, "hrv": 45, "respiratory_rate": 16}


def reading(**changes):
    return {**VALID, **changes}


def test_valid_event_returns_its_readings(sample_event):
    assert extract_input(sample_event) == sample_event["readings"]


def test_boundary_values_are_accepted():
    event = {"readings": [reading(spo2=100, hrv=0)]}
    assert extract_input(event) == event["readings"]


def test_fields_outside_the_schema_are_dropped():
    event = {"readings": [reading(patient="x")]}
    assert extract_input(event) == [VALID]


@pytest.mark.parametrize("event", [{}, None, [], {"data": [VALID]}])
def test_missing_readings_is_rejected(event):
    with pytest.raises(ValueError, match="readings"):
        extract_input(event)


@pytest.mark.parametrize("readings", [[], None, "x", VALID])
def test_empty_or_non_list_readings_is_rejected(readings):
    with pytest.raises(ValueError, match="non-empty list"):
        extract_input({"readings": readings})


def test_reading_that_is_not_an_object_is_rejected():
    with pytest.raises(ValueError, match="Reading 0"):
        extract_input({"readings": [97]})


@pytest.mark.parametrize("field", ["spo2", "heart_rate", "hrv", "respiratory_rate"])
def test_missing_parameter_is_rejected(field):
    incomplete = {key: value for key, value in VALID.items() if key != field}
    with pytest.raises(ValueError, match=field):
        extract_input({"readings": [incomplete]})


@pytest.mark.parametrize("field", ["spo2", "heart_rate", "hrv", "respiratory_rate"])
@pytest.mark.parametrize("value", ["97", None, True])
def test_non_numeric_parameter_is_rejected(field, value):
    with pytest.raises(ValueError, match=field):
        extract_input({"readings": [reading(**{field: value})]})


@pytest.mark.parametrize("value", [0, -1, 100.1, 150])
def test_invalid_spo2_is_rejected(value):
    with pytest.raises(ValueError, match="spo2"):
        extract_input({"readings": [reading(spo2=value)]})


@pytest.mark.parametrize("value", [0, -60])
def test_invalid_heart_rate_is_rejected(value):
    with pytest.raises(ValueError, match="heart_rate"):
        extract_input({"readings": [reading(heart_rate=value)]})


def test_invalid_hrv_is_rejected():
    with pytest.raises(ValueError, match="hrv"):
        extract_input({"readings": [reading(hrv=-1)]})


@pytest.mark.parametrize("value", [0, -12])
def test_invalid_respiratory_rate_is_rejected(value):
    with pytest.raises(ValueError, match="respiratory_rate"):
        extract_input({"readings": [reading(respiratory_rate=value)]})


def test_error_names_the_position_of_the_invalid_reading():
    with pytest.raises(ValueError, match="Reading 1"):
        extract_input({"readings": [VALID, reading(spo2=0)]})
