from app.api.schemas.reports import RawMetric
from app.graph.nodes.quant_analysis import calculate_percentage_growth, calculate_margin
from app.graph.nodes.validator import run_deterministic_validation


def test_growth_and_margin_calculations():
    # Margin test
    assert calculate_margin(20.0, 100.0) == 20.0
    assert calculate_margin(10.0, 0.0) == 0.0

    # Growth test
    assert calculate_percentage_growth(110.0, 100.0) == 10.0
    assert calculate_percentage_growth(90.0, 100.0) == -10.0
    assert calculate_percentage_growth(50.0, 0.0) == 0.0


def test_validator_detects_missing_metric():
    sample_metrics = [
        RawMetric(name="Revenue", period="2025Q1", value=1000.0, source_filing="10-Q"),
        RawMetric(name="GrossProfit", period="2025Q1", value=400.0, source_filing="10-Q"),
    ]
    required = ["Revenue", "GrossProfit", "OperatingIncome", "NetIncome"]
    issues = run_deterministic_validation(sample_metrics, required)

    missing_fields = [i.field for i in issues if i.issue_type == "MISSING_METRIC"]
    assert "OperatingIncome" in missing_fields
    assert "NetIncome" in missing_fields


def test_validator_detects_arithmetic_anomaly():
    # Gross Profit > Revenue is an invalid financial state
    corrupted_metrics = [
        RawMetric(name="Revenue", period="2025Q1", value=500.0, source_filing="10-Q"),
        RawMetric(name="GrossProfit", period="2025Q1", value=750.0, source_filing="10-Q"),
    ]
    issues = run_deterministic_validation(corrupted_metrics, ["Revenue", "GrossProfit"])

    anomaly = next((i for i in issues if i.issue_type == "ARITHMETIC_INCONSISTENCY"), None)
    assert anomaly is not None
    assert anomaly.severity == "CRITICAL"
