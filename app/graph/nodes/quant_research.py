"""Backward-compatible re-export; prefer app.graph.nodes.quant_analysis. """
from app.graph.nodes.quant_analysis import (  # noqa: F401
    calculate_margin,
    calculate_percentage_growth,
    quant_analysis_node,
)
