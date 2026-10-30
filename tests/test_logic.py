from backend.forecasting import classify_reliability
from backend.inventory import calculate_reorder_quantity


def test_reorder_formula_exact_match():
    assert calculate_reorder_quantity(392, 30, 150, 50) == 222


def test_reorder_never_negative():
    assert calculate_reorder_quantity(10, 5, 100, 0) == 0


def test_reliability_thresholds_are_error_based():
    assert classify_reliability(1.5, 10)[0] == "Reliable"
    assert classify_reliability(2.5, 10)[0] == "Moderate"
    assert classify_reliability(4.0, 10)[0] == "Low Reliability"
