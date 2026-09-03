from typing import Any, Dict, List
from app.api.schemas.reports import RawMetric, CalculatedMetric
from app.graph.state import ResearchState


def calculate_percentage_growth(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round(((current - previous) / abs(previous)) * 100, 2)


def calculate_margin(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


async def quant_analysis_node(state: ResearchState) -> Dict[str, Any]:
    """
    Deterministic Quantitative Analysis Node.
    Extracts validated raw financial values and computes canonical ratios.
    """
    raw_metrics: List[RawMetric] = state.get("raw_financial_data", [])
    metric_map: Dict[str, Dict[str, float]] = {}

    for metric in raw_metrics:
        if metric.name not in metric_map:
            metric_map[metric.name] = {}
        metric_map[metric.name][metric.period] = metric.value

    calculated: Dict[str, CalculatedMetric] = {}

    # Example: Compute Margins if Revenue and Profit exist for periods
    periods = sorted(list({m.period for m in raw_metrics}))

    for period in periods:
        rev = metric_map.get("Revenue", {}).get(period)
        gross_profit = metric_map.get("GrossProfit", {}).get(period)
        op_inc = metric_map.get("OperatingIncome", {}).get(period)
        net_inc = metric_map.get("NetIncome", {}).get(period)

        if rev and gross_profit:
            gm = calculate_margin(gross_profit, rev)
            calculated[f"GrossMargin_{period}"] = CalculatedMetric(
                name=f"Gross Margin ({period})",
                formula="(Gross Profit / Revenue) * 100",
                current_value=gm,
                unit="%",
            )

        if rev and op_inc:
            om = calculate_margin(op_inc, rev)
            calculated[f"OperatingMargin_{period}"] = CalculatedMetric(
                name=f"Operating Margin ({period})",
                formula="(Operating Income / Revenue) * 100",
                current_value=om,
                unit="%",
            )

        if rev and net_inc:
            nm = calculate_margin(net_inc, rev)
            calculated[f"NetMargin_{period}"] = CalculatedMetric(
                name=f"Net Margin ({period})",
                formula="(Net Income / Revenue) * 100",
                current_value=nm,
                unit="%",
            )

    # Compute QoQ Revenue Growth if we have consecutive periods
    if len(periods) >= 2 and "Revenue" in metric_map:
        for i in range(1, len(periods)):
            curr_p = periods[i]
            prev_p = periods[i - 1]
            curr_val = metric_map["Revenue"].get(curr_p)
            prev_val = metric_map["Revenue"].get(prev_p)

            if curr_val and prev_val:
                growth = calculate_percentage_growth(curr_val, prev_val)
                calculated[f"RevenueGrowth_QoQ_{curr_p}"] = CalculatedMetric(
                    name=f"QoQ Revenue Growth ({curr_p})",
                    formula="((Current Rev - Previous Rev) / Previous Rev) * 100",
                    current_value=growth,
                    previous_value=prev_val,
                    change_percentage=growth,
                    unit="%",
                )

    return {"calculated_metrics": calculated}
