from pathlib import Path

import pytest

from app.data.workbook import QSRDataset
from app.investigations.declining_stores import (
    consistently_declining_stores,
    investigate_all_declining_stores,
    investigate_declining_store,
)


@pytest.fixture(scope="module")
def dataset() -> QSRDataset:
    return QSRDataset(Path(__file__).parents[2] / "data" / "QSR_Agentic_Insights_Dataset.xlsx")


def test_finds_only_strictly_declining_stores(dataset: QSRDataset) -> None:
    result = consistently_declining_stores(dataset)
    assert result["declining_store_count"] == 9
    assert {store["store_id"] for store in result["stores"]} == {
        "ST002", "ST007", "ST010", "ST011", "ST015", "ST016", "ST030", "ST039", "ST042"
    }


def test_store_investigation_has_observed_evidence(dataset: QSRDataset) -> None:
    result = investigate_declining_store(dataset, "ST039")
    assert result["store"]["revenue_change_pct"] < 0
    assert result["store"]["order_change_pct"] < 0
    assert result["channel_changes"]
    assert result["top_declining_skus"]
    assert len(result["promotion_activity"]) == 3
    assert "not proof of causation" in result["interpretation_note"]


def test_investigation_covers_every_declining_store(dataset: QSRDataset) -> None:
    result = investigate_all_declining_stores(dataset)
    assert len(result["investigations"]) == result["declining_store_count"]


def test_unknown_store_is_rejected(dataset: QSRDataset) -> None:
    with pytest.raises(ValueError, match="Unknown store ID"):
        investigate_declining_store(dataset, "ST999")
