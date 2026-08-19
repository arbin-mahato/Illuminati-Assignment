"""Dataset-relative reporting periods.

Never derive business reporting windows from the machine clock: the workbook is the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.data.workbook import QSRDataset


@dataclass(frozen=True)
class ThreeMonthPeriod:
    start: date
    end: date
    month_keys: tuple[str, str, str]


def last_three_complete_months(dataset: QSRDataset) -> ThreeMonthPeriod:
    """Resolve the three calendar months ending in the dataset's latest order month."""
    max_date = date.fromisoformat(dataset.metadata().max_order_date)
    month_start = max_date.replace(day=1)
    end = max_date
    start_month = _shift_month(month_start, -2)
    month_keys = tuple(_shift_month(start_month, offset).strftime("%Y-%m") for offset in range(3))
    return ThreeMonthPeriod(
        start=start_month,
        end=end,
        month_keys=(month_keys[0], month_keys[1], month_keys[2]),
    )


def _shift_month(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)
