from pathlib import Path

import pytest

from app.analytics.periods import last_three_complete_months
from app.data.workbook import QSRDataset
from app.tools.analytics_tools import TOOL_REGISTRY


@pytest.fixture(scope="module")
def dataset() -> QSRDataset:
    return QSRDataset(Path(__file__).parents[2] / "data" / "QSR_Agentic_Insights_Dataset.xlsx")


def test_dataset_metadata_is_valid(dataset: QSRDataset) -> None:
    metadata = dataset.metadata()
    assert metadata.max_order_date == "2026-07-31"
    assert metadata.order_count == 20_000
    assert metadata.store_count == 50


def test_last_three_months_are_dataset_relative(dataset: QSRDataset) -> None:
    period = last_three_complete_months(dataset)
    assert period.month_keys == ("2026-05", "2026-06", "2026-07")


@pytest.mark.parametrize("tool_name", tuple(TOOL_REGISTRY))
def test_every_approved_tool_returns_data(dataset: QSRDataset, tool_name: str) -> None:
    result = TOOL_REGISTRY[tool_name](dataset)
    assert result


def test_overall_metrics_use_distinct_orders(dataset: QSRDataset) -> None:
    result = TOOL_REGISTRY["overall_metrics"](dataset)
    assert result["total_orders"] > 0
    assert result["total_revenue"] > 0
    assert result["average_order_value"] == round(result["total_revenue"] / result["total_orders"], 2)


def test_city_tool_only_flags_negative_first_to_last_change(dataset: QSRDataset) -> None:
    result = TOOL_REGISTRY["city_revenue_trends"](dataset)
    assert all(city["pct_change"] < 0 for city in result["declining_cities"])
