"""Load the supplied QSR workbook into a read-only, in-memory DuckDB database."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Final

import duckdb
import pandas as pd


REQUIRED_SHEETS: Final[tuple[str, ...]] = (
    "Store_Master",
    "Product_Master",
    "Promotions",
    "Calendar",
    "Orders",
    "Order_Details",
)
DATE_COLUMNS: Final[dict[str, tuple[str, ...]]] = {
    "Store_Master": ("OPENING_DATE",),
    "Promotions": ("START_DATE", "END_DATE"),
    "Calendar": ("DATE",),
    "Orders": ("ORDER_DATETIME",),
}


class WorkbookValidationError(ValueError):
    """Raised when the workbook cannot safely support the approved analyses."""


@dataclass(frozen=True)
class DatasetMetadata:
    """Dataset facts exposed to callers without leaking the underlying connection."""

    max_order_date: str
    order_count: int
    store_count: int


class QSRDataset:
    """A thread-safe, lazily loaded DuckDB representation of the assignment workbook."""

    def __init__(self, workbook_path: Path) -> None:
        self._workbook_path = workbook_path
        self._connection: duckdb.DuckDBPyConnection | None = None
        self._lock = Lock()

    def connection(self) -> duckdb.DuckDBPyConnection:
        """Return the initialized read-only analytics connection."""
        if self._connection is None:
            with self._lock:
                if self._connection is None:
                    self._connection = self._load()
        return self._connection

    def query(self, sql: str, parameters: list[object] | None = None) -> list[dict[str, object]]:
        """Execute a parameterized, internal SQL query and return JSON-safe records."""
        result = self.connection().execute(sql, parameters or []).fetchdf()
        return result.where(pd.notnull(result), None).to_dict(orient="records")

    def metadata(self) -> DatasetMetadata:
        row = self.query(
            """
            SELECT CAST(MAX(ORDER_DATETIME) AS DATE) AS max_order_date,
                   COUNT(DISTINCT ORDER_ID) AS order_count
            FROM Orders
            """
        )[0]
        stores = self.query("SELECT COUNT(DISTINCT STORE_ID) AS store_count FROM Store_Master")[0]
        return DatasetMetadata(
            max_order_date=pd.Timestamp(row["max_order_date"]).date().isoformat(),
            order_count=int(row["order_count"]),
            store_count=int(stores["store_count"]),
        )

    def _load(self) -> duckdb.DuckDBPyConnection:
        if not self._workbook_path.is_file():
            raise WorkbookValidationError(f"Dataset not found: {self._workbook_path}")

        workbook = pd.ExcelFile(self._workbook_path)
        missing = set(REQUIRED_SHEETS).difference(workbook.sheet_names)
        if missing:
            raise WorkbookValidationError(f"Workbook is missing required sheets: {', '.join(sorted(missing))}")

        connection = duckdb.connect(database=":memory:")
        for sheet in REQUIRED_SHEETS:
            frame = pd.read_excel(self._workbook_path, sheet_name=sheet)
            if frame.empty:
                raise WorkbookValidationError(f"Required sheet is empty: {sheet}")
            for column in DATE_COLUMNS.get(sheet, ()):
                if column not in frame.columns:
                    raise WorkbookValidationError(f"Missing expected column {sheet}.{column}")
                frame[column] = pd.to_datetime(frame[column], errors="raise")
            connection.register("source_frame", frame)
            connection.execute(f'CREATE TABLE "{sheet}" AS SELECT * FROM source_frame')
            connection.unregister("source_frame")

        self._validate(connection)
        return connection

    @staticmethod
    def _validate(connection: duckdb.DuckDBPyConnection) -> None:
        """Run the minimal integrity checks needed for trustworthy calculations."""
        checks = {
            "duplicate order IDs": "SELECT COUNT(*) = COUNT(DISTINCT ORDER_ID) FROM Orders",
            "negative net revenue": "SELECT COUNT(*) = 0 FROM Orders WHERE NET_REVENUE < 0",
            "orphan order details": """
                SELECT COUNT(*) = 0 FROM Order_Details detail
                LEFT JOIN Orders orders ON detail.ORDER_ID = orders.ORDER_ID
                WHERE orders.ORDER_ID IS NULL
            """,
        }
        failed = [name for name, sql in checks.items() if not connection.execute(sql).fetchone()[0]]
        if failed:
            raise WorkbookValidationError(f"Workbook failed validation: {', '.join(failed)}")
