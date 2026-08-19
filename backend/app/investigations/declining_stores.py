"""Q8 investigation: find and explain consistent store revenue decline.

The results distinguish observed contributors from causal claims. All values originate in
the workbook and no language model is involved in calculating or selecting evidence.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.analytics.periods import ThreeMonthPeriod, last_three_complete_months
from app.data.workbook import QSRDataset


def consistently_declining_stores(dataset: QSRDataset) -> dict[str, Any]:
    """Return stores whose revenue strictly declines in each of the latest three months."""
    period = last_three_complete_months(dataset)
    first_month, second_month, final_month = period.month_keys
    rows = dataset.query(
        """
        SELECT orders.STORE_ID AS store_id, store.STORE_NAME AS store_name, store.CITY AS city,
               ROUND(SUM(CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN orders.NET_REVENUE ELSE 0 END), 2) AS first_month_revenue,
               ROUND(SUM(CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN orders.NET_REVENUE ELSE 0 END), 2) AS second_month_revenue,
               ROUND(SUM(CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN orders.NET_REVENUE ELSE 0 END), 2) AS final_month_revenue
        FROM Orders orders JOIN Store_Master store ON orders.STORE_ID = store.STORE_ID
        WHERE orders.ORDER_DATETIME >= ? AND orders.ORDER_DATETIME < ?
        GROUP BY orders.STORE_ID, store.STORE_NAME, store.CITY
        HAVING first_month_revenue > second_month_revenue
           AND second_month_revenue > final_month_revenue
        ORDER BY (final_month_revenue - first_month_revenue) / NULLIF(first_month_revenue, 0), store_id
        """,
        [first_month, second_month, final_month, period.start, _day_after(period.end)],
    )
    stores = []
    for row in rows:
        first_revenue = float(row["first_month_revenue"])
        final_revenue = float(row["final_month_revenue"])
        stores.append(
            {
                **row,
                "revenue_change_pct": _percent_change(first_revenue, final_revenue),
            }
        )
    return {
        "period": _period_payload(period),
        "definition": f"Strict monthly revenue decline: {first_month} > {second_month} > {final_month}",
        "declining_store_count": len(stores),
        "stores": stores,
    }


def investigate_declining_store(dataset: QSRDataset, store_id: str) -> dict[str, Any]:
    """Measure observed revenue drivers for one store with a verified three-month decline."""
    period = last_three_complete_months(dataset)
    summary = _store_summary(dataset, store_id, period)
    if summary is None:
        raise ValueError(f"Unknown store ID: {store_id}")

    first_month, _, final_month = period.month_keys
    channel_changes = dataset.query(
        """
        SELECT CHANNEL AS channel,
               ROUND(SUM(CASE WHEN STRFTIME(ORDER_DATETIME, '%Y-%m') = ? THEN NET_REVENUE ELSE 0 END), 2) AS first_month_revenue,
               ROUND(SUM(CASE WHEN STRFTIME(ORDER_DATETIME, '%Y-%m') = ? THEN NET_REVENUE ELSE 0 END), 2) AS final_month_revenue
        FROM Orders WHERE STORE_ID = ? AND ORDER_DATETIME >= ? AND ORDER_DATETIME < ?
        GROUP BY CHANNEL ORDER BY first_month_revenue - final_month_revenue DESC, channel
        """,
        [first_month, final_month, store_id, period.start, _day_after(period.end)],
    )
    for channel in channel_changes:
        channel["revenue_change_pct"] = _percent_change(
            float(channel["first_month_revenue"]), float(channel["final_month_revenue"])
        )

    sku_changes = dataset.query(
        """
        SELECT detail.SKU_ID AS sku_id, product.SKU_NAME AS sku_name, product.CATEGORY AS category,
               SUM(CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN detail.QUANTITY ELSE 0 END) AS first_month_quantity,
               SUM(CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN detail.QUANTITY ELSE 0 END) AS final_month_quantity,
               ROUND(SUM(CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN detail.LINE_NET_VALUE ELSE 0 END), 2) AS first_month_revenue,
               ROUND(SUM(CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN detail.LINE_NET_VALUE ELSE 0 END), 2) AS final_month_revenue
        FROM Order_Details detail
        JOIN Orders orders ON detail.ORDER_ID = orders.ORDER_ID
        JOIN Product_Master product ON detail.SKU_ID = product.SKU_ID
        WHERE orders.STORE_ID = ? AND orders.ORDER_DATETIME >= ? AND orders.ORDER_DATETIME < ?
        GROUP BY detail.SKU_ID, product.SKU_NAME, product.CATEGORY
        HAVING first_month_revenue > final_month_revenue
        ORDER BY first_month_revenue - final_month_revenue DESC, sku_id LIMIT 5
        """,
        [first_month, final_month, first_month, final_month, store_id, period.start, _day_after(period.end)],
    )
    for sku in sku_changes:
        sku["quantity_change"] = int(sku["final_month_quantity"]) - int(sku["first_month_quantity"])
        sku["revenue_change_pct"] = _percent_change(float(sku["first_month_revenue"]), float(sku["final_month_revenue"]))

    promotions = dataset.query(
        """
        SELECT STRFTIME(ORDER_DATETIME, '%Y-%m') AS month,
               COUNT(DISTINCT CASE WHEN PROMO_ID IS NOT NULL THEN ORDER_ID END) AS promoted_orders,
               COUNT(DISTINCT ORDER_ID) AS total_orders,
               ROUND(SUM(CASE WHEN PROMO_ID IS NOT NULL THEN DISCOUNT_AMOUNT ELSE 0 END), 2) AS promotion_discount
        FROM Orders WHERE STORE_ID = ? AND ORDER_DATETIME >= ? AND ORDER_DATETIME < ?
        GROUP BY month ORDER BY month
        """,
        [store_id, period.start, _day_after(period.end)],
    )
    for promotion in promotions:
        total_orders = int(promotion["total_orders"])
        promotion["promoted_order_share_pct"] = round(100 * int(promotion["promoted_orders"]) / total_orders, 2) if total_orders else 0.0

    return {
        "period": _period_payload(period),
        "store": summary,
        "observed_driver": _primary_observed_driver(summary, channel_changes),
        "channel_changes": channel_changes,
        "top_declining_skus": sku_changes,
        "promotion_activity": promotions,
        "interpretation_note": "These are observed contributors, not proof of causation.",
    }


def investigate_all_declining_stores(dataset: QSRDataset) -> dict[str, Any]:
    """Run Q8's store-level evidence collection for every consistently declining store."""
    decline_result = consistently_declining_stores(dataset)
    investigations = [investigate_declining_store(dataset, str(store["store_id"])) for store in decline_result["stores"]]
    return {**decline_result, "investigations": investigations}


def _store_summary(dataset: QSRDataset, store_id: str, period: ThreeMonthPeriod) -> dict[str, Any] | None:
    first_month, _, final_month = period.month_keys
    rows = dataset.query(
        """
        SELECT orders.STORE_ID AS store_id, store.STORE_NAME AS store_name, store.CITY AS city,
               ROUND(SUM(CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN orders.NET_REVENUE ELSE 0 END), 2) AS first_month_revenue,
               ROUND(SUM(CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN orders.NET_REVENUE ELSE 0 END), 2) AS final_month_revenue,
               COUNT(DISTINCT CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN orders.ORDER_ID END) AS first_month_orders,
               COUNT(DISTINCT CASE WHEN STRFTIME(orders.ORDER_DATETIME, '%Y-%m') = ? THEN orders.ORDER_ID END) AS final_month_orders
        FROM Orders orders JOIN Store_Master store ON orders.STORE_ID = store.STORE_ID
        WHERE orders.STORE_ID = ? AND orders.ORDER_DATETIME >= ? AND orders.ORDER_DATETIME < ?
        GROUP BY orders.STORE_ID, store.STORE_NAME, store.CITY
        """,
        [first_month, final_month, first_month, final_month, store_id, period.start, _day_after(period.end)],
    )
    if not rows:
        return None
    summary = rows[0]
    first_revenue, final_revenue = float(summary["first_month_revenue"]), float(summary["final_month_revenue"])
    first_orders, final_orders = int(summary["first_month_orders"]), int(summary["final_month_orders"])
    summary.update(
        {
            "revenue_change_pct": _percent_change(first_revenue, final_revenue),
            "order_change_pct": _percent_change(first_orders, final_orders),
            "first_month_average_order_value": round(first_revenue / first_orders, 2) if first_orders else 0.0,
            "final_month_average_order_value": round(final_revenue / final_orders, 2) if final_orders else 0.0,
        }
    )
    summary["average_order_value_change_pct"] = _percent_change(
        float(summary["first_month_average_order_value"]), float(summary["final_month_average_order_value"])
    )
    return summary


def _primary_observed_driver(summary: dict[str, Any], channels: list[dict[str, Any]]) -> str:
    order_change = float(summary["order_change_pct"])
    aov_change = float(summary["average_order_value_change_pct"])
    largest_channel = channels[0] if channels else None
    if order_change < 0 and abs(order_change) >= abs(aov_change):
        driver = f"Order volume declined {abs(order_change):.2f}% from the first to final month."
    elif aov_change < 0:
        driver = f"Average order value declined {abs(aov_change):.2f}% from the first to final month."
    else:
        driver = "Revenue declined despite stable or improving order volume and average order value; review mix changes."
    if largest_channel and float(largest_channel["final_month_revenue"]) < float(largest_channel["first_month_revenue"]):
        driver += f" The largest observed channel revenue decrease was {largest_channel['channel']}."
    return driver


def _percent_change(first_value: float | int, final_value: float | int) -> float:
    return round(100 * (final_value - first_value) / first_value, 2) if first_value else 0.0


def _day_after(value: date) -> date:
    return value + timedelta(days=1)


def _period_payload(period: ThreeMonthPeriod) -> dict[str, object]:
    return {"start": str(period.start), "end": str(period.end), "months": period.month_keys}
