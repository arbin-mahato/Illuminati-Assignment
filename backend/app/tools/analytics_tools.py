"""The only approved dataset analysis tools.

Each function owns a fixed, parameterized query. The LLM may select a tool but can never generate SQL.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable

from app.analytics.periods import ThreeMonthPeriod, last_three_complete_months
from app.data.workbook import QSRDataset

AnalyticsResult = dict[str, Any]
AnalyticsTool = Callable[[QSRDataset], AnalyticsResult]


def overall_metrics(dataset: QSRDataset) -> AnalyticsResult:
    period = last_three_complete_months(dataset)
    rows = dataset.query(
        """
        SELECT ROUND(SUM(NET_REVENUE), 2) AS total_revenue,
               COUNT(DISTINCT ORDER_ID) AS total_orders,
               ROUND(SUM(NET_REVENUE) / COUNT(DISTINCT ORDER_ID), 2) AS average_order_value
        FROM Orders
        WHERE ORDER_DATETIME >= ? AND ORDER_DATETIME < ?
        """,
        [period.start, _day_after(period.end)],
    )
    monthly = dataset.query(
        """
        SELECT STRFTIME(ORDER_DATETIME, '%Y-%m') AS month,
               ROUND(SUM(NET_REVENUE), 2) AS revenue,
               COUNT(DISTINCT ORDER_ID) AS orders,
               ROUND(SUM(NET_REVENUE) / COUNT(DISTINCT ORDER_ID), 2) AS average_order_value
        FROM Orders
        WHERE ORDER_DATETIME >= ? AND ORDER_DATETIME < ?
        GROUP BY month ORDER BY month
        """,
        [period.start, _day_after(period.end)],
    )
    return {"period": _period_label(period), **rows[0], "monthly_breakdown": monthly}


def store_rankings(dataset: QSRDataset) -> AnalyticsResult:
    base_query = """
        SELECT store.STORE_ID AS store_id, store.STORE_NAME AS store_name, store.CITY AS city,
               ROUND(SUM(orders.NET_REVENUE), 2) AS revenue,
               COUNT(DISTINCT orders.ORDER_ID) AS orders,
               ROUND(SUM(orders.NET_REVENUE) / COUNT(DISTINCT orders.ORDER_ID), 2) AS average_order_value
        FROM Orders orders JOIN Store_Master store ON orders.STORE_ID = store.STORE_ID
        GROUP BY store.STORE_ID, store.STORE_NAME, store.CITY
    """
    return {
        "basis": "Full dataset revenue",
        "top_stores": dataset.query(f"{base_query} ORDER BY revenue DESC, store_id ASC LIMIT 5"),
        "bottom_stores": dataset.query(f"{base_query} ORDER BY revenue ASC, store_id ASC LIMIT 5"),
    }


def channel_performance(dataset: QSRDataset) -> AnalyticsResult:
    rows = dataset.query(
        """
        WITH channel_metrics AS (
            SELECT CHANNEL AS channel, ROUND(SUM(NET_REVENUE), 2) AS revenue,
                   COUNT(DISTINCT ORDER_ID) AS orders,
                   ROUND(SUM(NET_REVENUE) / COUNT(DISTINCT ORDER_ID), 2) AS average_order_value
            FROM Orders GROUP BY CHANNEL
        )
        SELECT *, ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS revenue_share_pct
        FROM channel_metrics ORDER BY revenue DESC, channel ASC
        """
    )
    return {"basis": "Full dataset revenue", "channels": rows}


def sku_performance(dataset: QSRDataset) -> AnalyticsResult:
    base_query = """
        SELECT product.SKU_ID AS sku_id, product.SKU_NAME AS sku_name, product.CATEGORY AS category,
               SUM(detail.QUANTITY) AS quantity_sold, ROUND(SUM(detail.LINE_NET_VALUE), 2) AS revenue
        FROM Order_Details detail JOIN Product_Master product ON detail.SKU_ID = product.SKU_ID
        GROUP BY product.SKU_ID, product.SKU_NAME, product.CATEGORY
    """
    return {
        "basis": "Full dataset sales",
        "top_by_quantity": dataset.query(f"{base_query} ORDER BY quantity_sold DESC, sku_id ASC LIMIT 5"),
        "top_by_revenue": dataset.query(f"{base_query} ORDER BY revenue DESC, sku_id ASC LIMIT 5"),
    }


def city_revenue_trends(dataset: QSRDataset) -> AnalyticsResult:
    period = last_three_complete_months(dataset)
    rows = dataset.query(
        """
        SELECT store.CITY AS city, STRFTIME(orders.ORDER_DATETIME, '%Y-%m') AS month,
               ROUND(SUM(orders.NET_REVENUE), 2) AS revenue
        FROM Orders orders JOIN Store_Master store ON orders.STORE_ID = store.STORE_ID
        WHERE orders.ORDER_DATETIME >= ? AND orders.ORDER_DATETIME < ?
        GROUP BY city, month ORDER BY city, month
        """,
        [period.start, _day_after(period.end)],
    )
    city_months: dict[str, dict[str, float]] = {}
    for row in rows:
        city_months.setdefault(str(row["city"]), {})[str(row["month"])] = float(row["revenue"])
    trends = []
    for city, months in sorted(city_months.items()):
        first, last = months[period.month_keys[0]], months[period.month_keys[-1]]
        change = round(((last - first) / first) * 100, 2) if first else 0.0
        trends.append({"city": city, "monthly_revenue": months, "pct_change": change, "declining": last < first})
    return {"period": _period_label(period), "city_trends": trends, "declining_cities": [row for row in trends if row["declining"]]}


def weekend_vs_weekday(dataset: QSRDataset) -> AnalyticsResult:
    rows = dataset.query(
        """
        SELECT calendar.DAY_TYPE AS day_type, ROUND(SUM(orders.NET_REVENUE), 2) AS revenue,
               COUNT(DISTINCT orders.ORDER_ID) AS orders,
               ROUND(SUM(orders.NET_REVENUE) / COUNT(DISTINCT orders.ORDER_ID), 2) AS average_order_value,
               COUNT(DISTINCT calendar.DATE) AS days,
               ROUND(SUM(orders.NET_REVENUE) / COUNT(DISTINCT calendar.DATE), 2) AS average_daily_revenue
        FROM Orders orders JOIN Calendar calendar ON CAST(orders.ORDER_DATETIME AS DATE) = calendar.DATE
        GROUP BY calendar.DAY_TYPE ORDER BY day_type
        """
    )
    return {"basis": "Full dataset", "segments": rows}


def festive_vs_normal(dataset: QSRDataset) -> AnalyticsResult:
    rows = dataset.query(
        """
        SELECT calendar.FESTIVE_PERIOD AS period, ROUND(SUM(orders.NET_REVENUE), 2) AS revenue,
               COUNT(DISTINCT orders.ORDER_ID) AS orders,
               ROUND(SUM(orders.NET_REVENUE) / COUNT(DISTINCT orders.ORDER_ID), 2) AS average_order_value,
               COUNT(DISTINCT calendar.DATE) AS days,
               ROUND(SUM(orders.NET_REVENUE) / COUNT(DISTINCT calendar.DATE), 2) AS average_daily_revenue
        FROM Orders orders JOIN Calendar calendar ON CAST(orders.ORDER_DATETIME AS DATE) = calendar.DATE
        GROUP BY calendar.FESTIVE_PERIOD ORDER BY period
        """
    )
    return {"basis": "Full dataset", "periods": rows}


TOOL_REGISTRY: dict[str, AnalyticsTool] = {
    "overall_metrics": overall_metrics,
    "store_rankings": store_rankings,
    "channel_performance": channel_performance,
    "sku_performance": sku_performance,
    "city_revenue_trends": city_revenue_trends,
    "weekend_vs_weekday": weekend_vs_weekday,
    "festive_vs_normal": festive_vs_normal,
}


def _day_after(value: date) -> date:
    return value + timedelta(days=1)


def _period_label(period: ThreeMonthPeriod) -> dict[str, str]:
    return {"start": str(period.start), "end": str(period.end)}
