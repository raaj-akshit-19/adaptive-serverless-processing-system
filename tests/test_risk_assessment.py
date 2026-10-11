import pytest

from controller.risk_assessment import (
    CRITICAL,
    MODERATE,
    NORMAL,
    PARAMETERS,
    assess_readings,
    assess_risk,
    deviation,
)

NORMAL_READING = {"spo2": 97, "heart_rate": 72, "hrv": 45, "respiratory_rate": 16}
MODERATE_READING = {"spo2": 93, "heart_rate": 105, "hrv": 30, "respiratory_rate": 22}
CRITICAL_READING = {"spo2": 88, "heart_rate": 125, "hrv": 15, "respiratory_rate": 26}


def test_weights_sum_to_one():
    assert sum(limits["weight"] for limits in PARAMETERS.values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    "value, expected",
    [
        (60, 0.0),    # lower normal bound
        (100, 0.0),   # upper normal bound
        (80, 0.0),    # inside the range
        (50, 0.5),    # halfway to the low critical limit
        (120, 0.5),   # halfway to the high critical limit
        (40, 1.0),    # at the low critical limit
        (140, 1.0),   # at the high critical limit
        (10, 1.0),    # beyond the limit is capped
        (300, 1.0),
    ],
)
def test_deviation_for_heart_rate_limits(value, expected):
    assert deviation(value, 60, 100, 40, 140) == pytest.approx(expected)


def test_deviation_is_zero_on_a_side_with_no_critical_limit():
    assert deviation(101, 95, 100, 85, None) == 0.0


def test_normal_reading():
    score, level, details = assess_risk(**NORMAL_READING)

    assert score == 0.0
    assert level == NORMAL
    assert details == {"spo2": 0.0, "heart_rate": 0.0, "respiratory_rate": 0.0, "hrv": 0.0}


def test_moderate_reading():
    score, level, details = assess_risk(**MODERATE_READING)

    # 0.35*0.2 + 0.25*0.125 + 0.25*0.2 + 0.15*0
    assert score == 0.151
    assert level == MODERATE
    assert details["spo2"] == pytest.approx(0.2)
    assert details["heart_rate"] == pytest.approx(0.125)
    assert details["respiratory_rate"] == pytest.approx(0.2)
    assert details["hrv"] == 0.0


def test_critical_reading():
    score, level, _ = assess_risk(**CRITICAL_READING)

    # 0.35*0.7 + 0.25*0.625 + 0.25*0.6 + 0.15*(5/15)
    assert score == 0.601
    assert level == CRITICAL


def test_score_at_the_moderate_cutoff_is_moderate():
    score, level, _ = assess_risk(spo2=97, heart_rate=116, hrv=45, respiratory_rate=16)

    assert score == 0.1
    assert level == MODERATE


def test_score_just_below_the_moderate_cutoff_is_normal():
    score, level, _ = assess_risk(spo2=97, heart_rate=115, hrv=45, respiratory_rate=16)

    assert score == 0.094
    assert level == NORMAL


@pytest.mark.parametrize(
    "reading, expected_score",
    [
        ({**NORMAL_READING, "hrv": 5}, 0.15),
        ({**NORMAL_READING, "spo2": 85}, 0.35),
        ({**NORMAL_READING, "heart_rate": 140}, 0.25),
        ({**NORMAL_READING, "respiratory_rate": 6}, 0.25),
    ],
)
def test_one_parameter_at_its_critical_limit_is_critical(reading, expected_score):
    score, level, _ = assess_risk(**reading)

    assert score == expected_score
    assert score < 0.50
    assert level == CRITICAL


def test_all_parameters_at_their_limits_score_one():
    score, level, _ = assess_risk(spo2=80, heart_rate=150, hrv=2, respiratory_rate=35)

    assert score == 1.0
    assert level == CRITICAL


def test_highest_risk_reading_determines_event_risk():
    readings = [NORMAL_READING, MODERATE_READING, CRITICAL_READING, NORMAL_READING]

    score, level, reading = assess_readings(readings)

    assert (score, level, reading) == (0.601, CRITICAL, CRITICAL_READING)


def test_event_of_normal_readings_is_normal():
    score, level, reading = assess_readings([NORMAL_READING, NORMAL_READING])

    assert (score, level) == (0.0, NORMAL)
    assert reading == NORMAL_READING


@pytest.mark.parametrize("order", ["critical_first", "moderate_first"])
def test_event_level_and_event_score_are_separate(order):
    # Critical through the critical-limit rule, with a low numerical score.
    critical_low_score = {**NORMAL_READING, "hrv": 5}
    # Moderate, with a higher numerical score.
    moderate_high_score = {"spo2": 90, "heart_rate": 120, "hrv": 45, "respiratory_rate": 24}
    assert assess_risk(**critical_low_score)[:2] == (0.15, CRITICAL)
    assert assess_risk(**moderate_high_score)[:2] == (0.4, MODERATE)

    readings = [critical_low_score, moderate_high_score]
    if order == "moderate_first":
        readings.reverse()
    score, level, reading = assess_readings(readings)

    assert level == CRITICAL               # highest severity among the readings
    assert score == 0.4                    # highest numerical score among the readings
    assert reading == critical_low_score   # the reading responsible for Critical
