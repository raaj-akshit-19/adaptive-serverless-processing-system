"""Composite physiological risk assessment.

CONFIRMED: four parameters are evaluated; each contributes to one composite
score through a weighted deviation from its normal range; thresholds are also
evaluated; the result is a risk level of Normal, Moderate or Critical.

NEW (reconstructed): every number in this module, the deviation formula, the
weighted sum and the level cut-offs. The original values were not recovered.
These are implementation assumptions and are not clinical thresholds.
"""

NORMAL = "Normal"
MODERATE = "Moderate"
CRITICAL = "Critical"
SEVERITY = {NORMAL: 0, MODERATE: 1, CRITICAL: 2}

FIELDS = ("spo2", "heart_rate", "hrv", "respiratory_rate")

# A critical limit of None means the value cannot leave the normal range on that side.
PARAMETERS = {
    "spo2": {
        "normal_low": 95, "normal_high": 100,
        "critical_low": 85, "critical_high": None,
        "weight": 0.35,
    },
    "heart_rate": {
        "normal_low": 60, "normal_high": 100,
        "critical_low": 40, "critical_high": 140,
        "weight": 0.25,
    },
    "respiratory_rate": {
        "normal_low": 12, "normal_high": 20,
        "critical_low": 6, "critical_high": 30,
        "weight": 0.25,
    },
    "hrv": {
        "normal_low": 20, "normal_high": 100,
        "critical_low": 5, "critical_high": 200,
        "weight": 0.15,
    },
}

MODERATE_SCORE = 0.10
CRITICAL_SCORE = 0.50


def deviation(value, normal_low, normal_high, critical_low, critical_high) -> float:
    """Return how far ``value`` lies outside its normal range, from 0 to 1.

    0 inside the normal range, rising linearly to 1 at the critical limit.
    """
    if value < normal_low and critical_low is not None:
        result = (normal_low - value) / (normal_low - critical_low)
    elif value > normal_high and critical_high is not None:
        result = (value - normal_high) / (critical_high - normal_high)
    else:
        result = 0.0
    return min(result, 1.0)


def assess_risk(spo2, heart_rate, hrv, respiratory_rate):
    """Return ``(score, risk_level, details)`` for one reading.

    ``score`` is the weighted sum of the four deviations, from 0 to 1.
    ``details`` maps each parameter to its deviation.
    """
    values = {
        "spo2": spo2,
        "heart_rate": heart_rate,
        "hrv": hrv,
        "respiratory_rate": respiratory_rate,
    }
    details = {}
    score = 0.0
    for name, limits in PARAMETERS.items():
        details[name] = deviation(
            values[name],
            limits["normal_low"], limits["normal_high"],
            limits["critical_low"], limits["critical_high"],
        )
        score += limits["weight"] * details[name]
    score = round(score, 3)

    at_critical_limit = any(value >= 1.0 for value in details.values())
    if score >= CRITICAL_SCORE or at_critical_limit:
        risk_level = CRITICAL
    elif score >= MODERATE_SCORE:
        risk_level = MODERATE
    else:
        risk_level = NORMAL
    return score, risk_level, details


def assess_readings(readings):
    """Return ``(score, risk_level, reading)`` for an event of several readings.

    These are three separate results:

    ``score``       the highest numerical score among all readings
    ``risk_level``  the highest severity among all readings
    ``reading``     the reading responsible for that severity (the
                    highest-scoring one, if several share it)

    The score and the reading can come from different readings: a reading
    that is Critical through the critical-limit rule may score lower than a
    Moderate reading in the same event.
    """
    highest_score = None
    highest_severity = None
    for reading in readings:
        score, risk_level, _ = assess_risk(**reading)
        if highest_score is None or score > highest_score:
            highest_score = score
        rank = (SEVERITY[risk_level], score)
        if highest_severity is None or rank > highest_severity[0]:
            highest_severity = (rank, risk_level, reading)
    _, risk_level, reading = highest_severity
    return highest_score, risk_level, reading
